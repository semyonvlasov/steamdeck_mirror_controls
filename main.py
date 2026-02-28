import asyncio
import os
import re
import secrets
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

try:
    import decky  # type: ignore
except ImportError:  # pragma: no cover
    decky = None


class TemplateCandidate:
    def __init__(
        self,
        app_id: int,
        path: Path,
        mtime: float,
        controller_root: Path,
        source_kind: str,
    ) -> None:
        self.app_id = app_id
        self.path = path
        self.mtime = mtime
        self.controller_root = controller_root
        self.source_kind = source_kind

    @property
    def is_mirror(self) -> bool:
        return "mirror" in self.path.name.lower()

    @property
    def is_template_like(self) -> bool:
        return "template" in self.path.name.lower()

    @property
    def is_current_layout_like(self) -> bool:
        lower = self.path.name.lower()
        return lower == f"app_{self.app_id}.vdf" or lower == f"{self.app_id}.vdf"


class Plugin:
    def __init__(self) -> None:
        self.logger = getattr(decky, "logger", None)

    async def _main(self) -> None:
        self._log("Mirror Controls backend started")

    async def _unload(self) -> None:
        self._log("Mirror Controls backend unloaded")

    async def create_mirror_template(
        self,
        app_id: int | dict[str, Any] = 0,
        mirror_dpad: bool = True,
        mirror_touchpads: bool = True,
        mirror_sticks: bool = True,
    ) -> dict:
        # Compatibility: handle both positional args and dict payload calls.
        if isinstance(app_id, dict):
            payload = app_id
            app_id = int(payload.get("app_id", 0) or 0)
            mirror_dpad = bool(payload.get("mirror_dpad", mirror_dpad))
            mirror_touchpads = bool(payload.get("mirror_touchpads", mirror_touchpads))
            mirror_sticks = bool(payload.get("mirror_sticks", mirror_sticks))

        if not mirror_dpad and not mirror_touchpads and not mirror_sticks:
            return {
                "ok": False,
                "error": "Nothing selected to mirror. Enable at least one option.",
            }
        try:
            self._log(
                "create_mirror_template called "
                f"app_id={app_id} dpad={mirror_dpad} touchpads={mirror_touchpads} sticks={mirror_sticks}"
            )
            return await asyncio.to_thread(
                self._create_mirror_template_sync,
                int(app_id),
                bool(mirror_dpad),
                bool(mirror_touchpads),
                bool(mirror_sticks),
            )
        except Exception as exc:
            self._log(
                "create_mirror_template failed:\n"
                f"{traceback.format_exc()}"
            )
            return {
                "ok": False,
                "error": f"Python exception: {type(exc).__name__}: {exc}",
            }

    def _create_mirror_template_sync(
        self,
        app_id: int,
        mirror_dpad: bool,
        mirror_touchpads: bool,
        mirror_sticks: bool,
    ) -> dict:
        self._log(
            "[mirror] begin "
            f"app_id={app_id} mirror_dpad={mirror_dpad} "
            f"mirror_touchpads={mirror_touchpads} mirror_sticks={mirror_sticks}"
        )
        if app_id <= 0:
            return {
                "ok": False,
                "error": "Could not detect current game App ID. Open this plugin while a game is running.",
            }

        source = self._find_current_layout_for_app(app_id)
        if source is None:
            return {
                "ok": False,
                "error": (
                    f"Could not find current controller layout for App {app_id}. "
                    "Ensure the game has at least one saved game layout."
                ),
            }

        target_app_id = app_id
        if source.app_id > 0 and source.app_id != app_id:
            target_app_id = source.app_id
            self._log(
                "[mirror] requested app_id does not match selected source; "
                f"requested={app_id} selected={source.app_id}. "
                f"Using selected app_id for output target."
            )

        self._log(
            "[mirror] source selected "
            f"kind={source.source_kind} inferred_app_id={source.app_id} "
            f"path={source.path} {self._path_state(source.path)}"
        )
        original = source.path.read_text(encoding="utf-8", errors="ignore")
        self._log(f"[mirror] source bytes={len(original.encode('utf-8', errors='ignore'))} chars={len(original)}")
        mirrored, swaps = self._build_mirrored_template(
            original,
            mirror_dpad=mirror_dpad,
            mirror_touchpads=mirror_touchpads,
            mirror_sticks=mirror_sticks,
        )
        mirrored = self._append_title_suffix(mirrored)
        self._log(f"[mirror] transformed chars={len(mirrored)} swaps={swaps}")

        output_dir = self._resolve_output_dir(source, target_app_id)
        self._log(f"[mirror] output_dir={output_dir} {self._path_state(output_dir)}")
        output_path = self._build_output_path(
            output_dir=output_dir,
            source_path=source.path,
            source_kind=source.source_kind,
        )
        self._log(f"[mirror] output_path chosen={output_path}")
        if output_path == source.path:
            backup_path = self._build_backup_path(output_dir, source.path)
            self._write_text_verified(backup_path, original)
            self._log(f"[mirror] source equals output; backup written to {backup_path}")
        self._write_text_verified(output_path, mirrored)
        self._log(f"[mirror] output_path written {self._path_state(output_path)}")
        self._log(f"[mirror] output_dir latest_vdf={self._latest_vdf_paths(output_dir, limit=8)}")

        self._log(
            f"Created mirror template app_id={app_id} source={source.path} output={output_path}"
        )
        return {
            "ok": True,
            "app_id": target_app_id,
            "requested_app_id": app_id,
            "source_path": str(source.path),
            "output_path": str(output_path),
            "swapped_tokens": swaps,
        }

    def _find_current_layout_for_app(self, app_id: int) -> TemplateCandidate | None:
        candidates: list[TemplateCandidate] = []
        fallback_candidates: list[TemplateCandidate] = []
        userdata_roots = list(self._controller_config_roots())
        sc_config_roots = list(self._steam_controller_configs_roots())
        self._log(
            "[mirror] scan roots "
            f"userdata={len(userdata_roots)} "
            f"steam_controller_configs={len(sc_config_roots)}"
        )

        for controller_root in userdata_roots:
            all_candidates = self._collect_all_candidates(controller_root, source_kind="userdata")
            if not all_candidates:
                self._log(f"[mirror] root={controller_root} kind=userdata candidates=0")
                continue
            self._log(f"[mirror] root={controller_root} kind=userdata candidates={len(all_candidates)}")
            fallback_candidates.extend(all_candidates)
            matched = self._filter_candidates_for_app(all_candidates, app_id)
            self._log(f"[mirror] root={controller_root} kind=userdata matched_app={len(matched)}")
            candidates.extend(matched)

        for config_root in sc_config_roots:
            all_candidates = self._collect_all_candidates(
                config_root, source_kind="steam_controller_configs"
            )
            if not all_candidates:
                self._log(f"[mirror] root={config_root} kind=steam_controller_configs candidates=0")
                continue
            self._log(
                f"[mirror] root={config_root} kind=steam_controller_configs candidates={len(all_candidates)}"
            )
            fallback_candidates.extend(all_candidates)
            matched = self._filter_candidates_for_app(all_candidates, app_id)
            self._log(
                f"[mirror] root={config_root} kind=steam_controller_configs matched_app={len(matched)}"
            )
            candidates.extend(matched)

        if candidates:
            non_mirror = [candidate for candidate in candidates if not candidate.is_mirror]
            current_layout_like = [candidate for candidate in non_mirror if candidate.is_current_layout_like]
            non_template = [candidate for candidate in non_mirror if not candidate.is_template_like]
            source_pool = current_layout_like or non_template or non_mirror or candidates
            self._log_candidate_preview("app-matched", source_pool)
            chosen = max(source_pool, key=lambda candidate: candidate.mtime)
            self._log(
                f"Found {len(candidates)} app-matched layouts for app_id={app_id}; selected {chosen.path}"
            )
            return chosen

        if not fallback_candidates:
            return None

        non_mirror_fb = [candidate for candidate in fallback_candidates if not candidate.is_mirror]
        app_specific_fb = [candidate for candidate in non_mirror_fb if candidate.app_id > 0]
        app_specific_non_template_fb = [
            candidate
            for candidate in app_specific_fb
            if not candidate.is_template_like
        ]
        controller_neptune_fb = [
            candidate
            for candidate in non_mirror_fb
            if candidate.path.name.lower() == "controller_neptune.vdf"
        ]
        non_template_fb = [candidate for candidate in non_mirror_fb if not candidate.is_template_like]
        source_pool_fb = (
            app_specific_non_template_fb
            or app_specific_fb
            or controller_neptune_fb
            or non_template_fb
            or non_mirror_fb
            or fallback_candidates
        )
        self._log_candidate_preview("fallback", source_pool_fb)
        chosen_fb = max(source_pool_fb, key=lambda candidate: candidate.mtime)
        self._log(
            f"No app-matched layout found for app_id={app_id}; "
            f"fallback to latest layout {chosen_fb.path}"
        )
        return chosen_fb

    def _collect_all_candidates(self, controller_root: Path, source_kind: str) -> list[TemplateCandidate]:
        out: list[TemplateCandidate] = []
        for root, _, files in os.walk(controller_root, topdown=True, followlinks=False, onerror=lambda _: None):
            for filename in files:
                if not filename.lower().endswith(".vdf"):
                    continue
                file_path = Path(root) / filename
                if not file_path.is_file():
                    continue
                try:
                    mtime = file_path.stat().st_mtime
                except OSError:
                    continue
                out.append(
                    TemplateCandidate(
                        app_id=self._infer_app_id_from_path(controller_root, file_path),
                        path=file_path,
                        mtime=mtime,
                        controller_root=controller_root,
                        source_kind=source_kind,
                    )
                )
        return out

    def _filter_candidates_for_app(
        self, candidates: list[TemplateCandidate], app_id: int
    ) -> list[TemplateCandidate]:
        app_key = str(app_id)
        app_key_token = f"app_{app_key}"
        out: list[TemplateCandidate] = []
        for candidate in candidates:
            if candidate.app_id == app_id:
                out.append(candidate)
                continue
            try:
                rel = candidate.path.relative_to(candidate.controller_root).as_posix().lower()
            except ValueError:
                rel = str(candidate.path).lower()
            name = candidate.path.name.lower()
            if (
                f"/{app_key}/" in f"/{rel}/"
                or app_key_token in rel
                or app_key_token in name
                or name == f"{app_key}.vdf"
            ):
                out.append(candidate)
        return out

    def _infer_app_id_from_path(self, controller_root: Path, file_path: Path) -> int:
        name = file_path.stem.lower()
        for pattern in (r"^app_(\d+)$", r"^(\d+)$"):
            match = re.match(pattern, name)
            if match:
                return int(match.group(1))

        try:
            parts = list(file_path.relative_to(controller_root).parts)
        except ValueError:
            parts = list(file_path.parts)
        for part in reversed(parts):
            lower = part.lower()
            if lower.isdigit():
                return int(lower)
            if lower.startswith("app_") and lower[4:].isdigit():
                return int(lower[4:])
        return 0

    def _controller_config_roots(self) -> Iterable[Path]:
        homes = self._steam_home_candidates()
        userdata_roots: list[Path] = []
        for home in homes:
            userdata_roots.extend(
                [
                    home / ".local" / "share" / "Steam" / "userdata",
                    home / ".steam" / "steam" / "userdata",
                    home / ".steam" / "root" / "userdata",
                    home / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam" / "userdata",
                ]
            )
        seen: set[Path] = set()
        for userdata_root in userdata_roots:
            if not userdata_root.is_dir():
                continue
            for user_dir in self._safe_iterdir(userdata_root):
                if not user_dir.is_dir() or not user_dir.name.isdigit():
                    continue
                controller_configs = user_dir / "config" / "controller_configs"
                if controller_configs.is_dir() and controller_configs not in seen:
                    seen.add(controller_configs)
                    yield controller_configs

    def _steam_controller_configs_roots(self) -> Iterable[Path]:
        homes = self._steam_home_candidates()
        base_roots: list[Path] = []
        for home in homes:
            base_roots.extend(
                [
                    home / ".local" / "share" / "Steam" / "steamapps" / "common" / "Steam Controller Configs",
                    home
                    / ".var"
                    / "app"
                    / "com.valvesoftware.Steam"
                    / ".local"
                    / "share"
                    / "Steam"
                    / "steamapps"
                    / "common"
                    / "Steam Controller Configs",
                ]
            )

        seen: set[Path] = set()
        for base_root in base_roots:
            if not base_root.is_dir():
                continue
            for maybe_user_dir in self._safe_iterdir(base_root):
                if not maybe_user_dir.is_dir():
                    continue
                config_root = maybe_user_dir / "config"
                if config_root.is_dir() and config_root not in seen:
                    seen.add(config_root)
                    yield config_root

    def _steam_home_candidates(self) -> list[Path]:
        candidates = [
            os.getenv("DECKY_USER_HOME", "").strip(),
            str(Path.home()),
            "/home/deck",
        ]
        out: list[Path] = []
        seen: set[str] = set()
        for raw_path in candidates:
            if not raw_path:
                continue
            normalized = str(Path(raw_path).expanduser())
            if normalized in seen:
                continue
            seen.add(normalized)
            out.append(Path(normalized))
        return out

    def _safe_iterdir(self, path: Path) -> list[Path]:
        try:
            return list(path.iterdir())
        except OSError:
            return []

    def _resolve_output_dir(self, source: TemplateCandidate, app_id: int) -> Path:
        if source.source_kind == "steam_controller_configs":
            app_dir = source.controller_root / str(app_id)
            if app_dir.is_dir():
                return app_dir
            try:
                app_dir.mkdir(parents=True, exist_ok=True)
                return app_dir
            except OSError:
                return source.path.parent

        controller_root = source.controller_root
        fallback_dir = source.path.parent
        app_dir = controller_root / str(app_id)
        if app_dir.is_dir():
            return app_dir
        try:
            app_dir.mkdir(parents=True, exist_ok=True)
            return app_dir
        except OSError:
            return fallback_dir

    def _write_text_verified(self, output_path: Path, content: str) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())

    def _path_state(self, path: Path) -> str:
        try:
            if not path.exists():
                return "exists=0"
            stat = path.stat()
            kind = "dir" if path.is_dir() else "file"
            mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            return f"exists=1 kind={kind} size={stat.st_size} mtime={mtime}"
        except OSError as exc:
            return f"state_error={type(exc).__name__}:{exc}"

    def _latest_vdf_paths(self, directory: Path, limit: int = 8) -> str:
        try:
            vdf_files = [path for path in directory.glob("*.vdf") if path.is_file()]
            if not vdf_files:
                return "[]"
            vdf_files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
            return "[" + ", ".join(str(path) for path in vdf_files[:limit]) + "]"
        except OSError as exc:
            return f"[error:{type(exc).__name__}:{exc}]"

    def _log_candidate_preview(
        self, label: str, candidates: list[TemplateCandidate], limit: int = 6
    ) -> None:
        if not candidates:
            self._log(f"[mirror] {label}: no candidates")
            return
        preview = sorted(candidates, key=lambda candidate: candidate.mtime, reverse=True)[:limit]
        for idx, candidate in enumerate(preview, start=1):
            mtime = datetime.fromtimestamp(candidate.mtime).strftime("%Y-%m-%d %H:%M:%S")
            self._log(
                f"[mirror] {label}[{idx}] kind={candidate.source_kind} app={candidate.app_id} "
                f"mtime={mtime} path={candidate.path}"
            )

    def _build_output_path(self, output_dir: Path, source_path: Path, source_kind: str) -> Path:
        if source_kind == "steam_controller_configs":
            # Steam reliably picks up per-game layouts here when using canonical file names.
            return output_dir / source_path.name

        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = source_path.stem
        suffix = source_path.suffix or ".vdf"
        candidate = output_dir / f"{stem}_mirror_{now}{suffix}"
        index = 1
        while candidate.exists():
            candidate = output_dir / f"{stem}_mirror_{now}_{index}{suffix}"
            index += 1
        return candidate

    def _build_backup_path(self, output_dir: Path, source_path: Path) -> Path:
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = source_path.stem
        suffix = source_path.suffix or ".vdf"
        candidate = output_dir / f"{stem}_pre_mirror_{now}{suffix}"
        index = 1
        while candidate.exists():
            candidate = output_dir / f"{stem}_pre_mirror_{now}_{index}{suffix}"
            index += 1
        return candidate

    def _build_mirrored_template(
        self,
        template_text: str,
        mirror_dpad: bool,
        mirror_touchpads: bool,
        mirror_sticks: bool,
    ) -> tuple[str, int]:
        transformed = template_text
        total_swaps = 0

        if mirror_dpad:
            transformed, swaps = self._swap_token_pairs(
                transformed,
                [
                    ("button_a", "dpad_down"),
                    ("button_b", "dpad_right"),
                    ("button_x", "dpad_left"),
                    ("button_y", "dpad_up"),
                ],
            )
            total_swaps += swaps

        if mirror_touchpads:
            transformed, swaps = self._swap_token_pairs(
                transformed,
                [
                    ("left_trackpad", "right_trackpad"),
                    ("left_touchpad", "right_touchpad"),
                    ("trackpad_left", "trackpad_right"),
                    ("touchpad_left", "touchpad_right"),
                    ("left_pad", "right_pad"),
                ],
            )
            total_swaps += swaps

        if mirror_sticks:
            transformed, swaps = self._swap_token_pairs(
                transformed,
                [
                    ("left_stick", "right_stick"),
                    ("stick_left", "stick_right"),
                    ("left_joystick", "right_joystick"),
                    ("joystick_left", "joystick_right"),
                    ("left_analog", "right_analog"),
                    ("analog_left", "analog_right"),
                ],
            )
            total_swaps += swaps

        return transformed, total_swaps

    def _swap_token_pairs(self, text: str, pairs: list[tuple[str, str]]) -> tuple[str, int]:
        transformed = text
        total_replacements = 0

        expanded_pairs = self._expand_case_pairs(pairs)
        for idx, (left, right) in enumerate(expanded_pairs):
            left_hits = transformed.count(left)
            right_hits = transformed.count(right)
            if left_hits == 0 and right_hits == 0:
                continue

            marker_left = f"__mirror_left_{idx}_{secrets.token_hex(6)}__"
            marker_right = f"__mirror_right_{idx}_{secrets.token_hex(6)}__"

            transformed = transformed.replace(left, marker_left)
            transformed = transformed.replace(right, marker_right)
            transformed = transformed.replace(marker_left, right)
            transformed = transformed.replace(marker_right, left)

            total_replacements += left_hits + right_hits

        return transformed, total_replacements

    def _expand_case_pairs(self, pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for left, right in pairs:
            variants = [
                (left, right),
                (left.upper(), right.upper()),
            ]
            for variant in variants:
                if variant in seen:
                    continue
                seen.add(variant)
                out.append(variant)
        return out

    def _append_title_suffix(self, text: str) -> str:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        title_re = re.compile(r'("title"\s*")([^"]*)(")', flags=re.IGNORECASE)

        def repl(match: re.Match[str]) -> str:
            current = match.group(2).strip()
            if "mirror" in current.lower():
                return match.group(0)
            return f'{match.group(1)}{current} (Mirror {stamp}){match.group(3)}'

        updated, count = title_re.subn(repl, text, count=1)
        if count > 0:
            return updated
        return f'"title" "Mirror {stamp}"\n{updated}'

    def _log(self, message: str) -> None:
        if self.logger is not None:
            self.logger.info(message)
