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

    @property
    def is_workshop(self) -> bool:
        return "/steamapps/workshop/content/241100/" in str(self.path).lower().replace("\\", "/")


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
        mirror_menu_position: bool = True,
        mirror_gyro_buttons: bool = True,
    ) -> dict:
        # Compatibility: handle both positional args and dict payload calls.
        if isinstance(app_id, dict):
            payload = app_id
            app_id = int(payload.get("app_id", 0) or 0)
            mirror_dpad = bool(payload.get("mirror_dpad", mirror_dpad))
            mirror_touchpads = bool(payload.get("mirror_touchpads", mirror_touchpads))
            mirror_sticks = bool(payload.get("mirror_sticks", mirror_sticks))
            mirror_menu_position = bool(
                payload.get("mirror_menu_position", mirror_menu_position)
            )
            mirror_gyro_buttons = bool(
                payload.get("mirror_gyro_buttons", mirror_gyro_buttons)
            )

        if (
            not mirror_dpad
            and not mirror_touchpads
            and not mirror_sticks
            and not mirror_menu_position
            and not mirror_gyro_buttons
        ):
            return {
                "ok": False,
                "error": "Nothing selected to mirror. Enable at least one option.",
            }
        try:
            self._log(
                "create_mirror_template called "
                f"app_id={app_id} dpad={mirror_dpad} touchpads={mirror_touchpads} "
                f"sticks={mirror_sticks} menu_position={mirror_menu_position} "
                f"gyro_buttons={mirror_gyro_buttons}"
            )
            return await asyncio.to_thread(
                self._create_mirror_template_sync,
                int(app_id),
                bool(mirror_dpad),
                bool(mirror_touchpads),
                bool(mirror_sticks),
                bool(mirror_menu_position),
                bool(mirror_gyro_buttons),
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
        mirror_menu_position: bool,
        mirror_gyro_buttons: bool,
    ) -> dict:
        self._log(
            "[mirror] begin "
            f"app_id={app_id} mirror_dpad={mirror_dpad} "
            f"mirror_touchpads={mirror_touchpads} mirror_sticks={mirror_sticks} "
            f"mirror_menu_position={mirror_menu_position} "
            f"mirror_gyro_buttons={mirror_gyro_buttons}"
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
        self._log_source_layout_metadata(original, source.path)
        mirrored, swaps = self._build_mirrored_template(
            original,
            mirror_dpad=mirror_dpad,
            mirror_touchpads=mirror_touchpads,
            mirror_sticks=mirror_sticks,
            mirror_menu_position=mirror_menu_position,
            mirror_gyro_buttons=mirror_gyro_buttons,
        )
        mirrored = self._append_title_suffix(mirrored)
        self._log(f"[mirror] transformed chars={len(mirrored)} swaps={swaps}")

        output_dir = self._resolve_game_layout_output_dir(source, target_app_id)
        self._log(f"[mirror] output_dir={output_dir} {self._path_state(output_dir)}")
        output_path = self._build_game_output_path(
            output_dir=output_dir,
            source_path=source.path,
            app_id=target_app_id,
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
        console_candidate = self._find_recent_loaded_layout_from_console(app_id)

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

        if console_candidate is not None and console_candidate.source_kind != "workshop":
            self._log(
                "[mirror] selected from console log (non-workshop) "
                f"app_id={console_candidate.app_id} kind={console_candidate.source_kind} "
                f"path={console_candidate.path}"
            )
            return console_candidate

        if not fallback_candidates:
            if console_candidate is not None:
                self._log(
                    "[mirror] no scanned candidates; selected from console log "
                    f"app_id={console_candidate.app_id} kind={console_candidate.source_kind} "
                    f"path={console_candidate.path}"
                )
                return console_candidate
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
        if console_candidate is not None and console_candidate.source_kind == "workshop":
            self._log(
                "[mirror] workshop console candidate exists but scanned fallback was preferred "
                f"console={console_candidate.path}"
            )
        return chosen_fb

    def _find_recent_loaded_layout_from_console(self, requested_app_id: int) -> TemplateCandidate | None:
        candidates: list[TemplateCandidate] = []
        seen_paths: set[Path] = set()

        for log_path in self._steam_console_log_paths():
            tail = self._read_text_tail(log_path, max_bytes=2 * 1024 * 1024)
            if not tail:
                continue
            for line in reversed(tail.splitlines()):
                parsed = self._parse_console_loaded_config_line(line)
                if parsed is None:
                    continue
                app_id, config_path, ts = parsed
                if config_path in seen_paths or not config_path.is_file():
                    continue
                source_kind, controller_root = self._infer_source_from_path(config_path)
                inferred_app_id = app_id if app_id > 0 else self._infer_app_id_from_path(controller_root, config_path)
                mtime = ts if ts > 0 else self._safe_mtime(config_path)
                candidates.append(
                    TemplateCandidate(
                        app_id=inferred_app_id,
                        path=config_path,
                        mtime=mtime,
                        controller_root=controller_root,
                        source_kind=source_kind,
                    )
                )
                seen_paths.add(config_path)
                if len(candidates) >= 16:
                    break
            if len(candidates) >= 16:
                break

        if not candidates:
            return None

        candidates.sort(key=lambda candidate: candidate.mtime, reverse=True)
        fresh_candidates = [candidate for candidate in candidates if self._is_recent(candidate.mtime, max_hours=12)]
        if not fresh_candidates:
            self._log("[mirror] console candidates found but none are recent enough; ignoring console source")
            return None

        self._log_candidate_preview("console", fresh_candidates, limit=6)

        preferred_kinds = ("steam_controller_configs", "userdata", "workshop", "unknown")
        prioritized = sorted(
            fresh_candidates,
            key=lambda candidate: preferred_kinds.index(candidate.source_kind)
            if candidate.source_kind in preferred_kinds
            else len(preferred_kinds),
        )

        for candidate in prioritized:
            if candidate.app_id == requested_app_id:
                return candidate

        for candidate in prioritized:
            if candidate.app_id > 0:
                self._log(
                    "[mirror] console fallback app_id mismatch "
                    f"requested={requested_app_id} selected={candidate.app_id}"
                )
                return candidate

        return prioritized[0]

    def _steam_console_log_paths(self) -> Iterable[Path]:
        homes = self._steam_home_candidates()
        candidates: list[Path] = []
        for home in homes:
            candidates.extend(
                [
                    home / ".local" / "share" / "Steam" / "logs" / "console_log.txt",
                    home / ".steam" / "steam" / "logs" / "console_log.txt",
                    home / ".steam" / "root" / "logs" / "console_log.txt",
                    home
                    / ".var"
                    / "app"
                    / "com.valvesoftware.Steam"
                    / ".local"
                    / "share"
                    / "Steam"
                    / "logs"
                    / "console_log.txt",
                ]
            )
        seen: set[Path] = set()
        for path in candidates:
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            yield path

    def _read_text_tail(self, path: Path, max_bytes: int = 1_000_000) -> str:
        try:
            with open(path, "rb") as file:
                file.seek(0, os.SEEK_END)
                size = file.tell()
                file.seek(max(size - max_bytes, 0), os.SEEK_SET)
                data = file.read()
            return data.decode("utf-8", errors="ignore")
        except OSError:
            return ""

    def _parse_console_loaded_config_line(self, line: str) -> tuple[int, Path, float] | None:
        if "Loaded Config" not in line or ".vdf" not in line:
            return None
        match = re.search(
            r"Loaded Config.*App ID\s+(\d+).*?:\s*(/.*?\.vdf)\s*$",
            line,
            flags=re.IGNORECASE,
        )
        if not match:
            return None
        app_id = int(match.group(1))
        path = Path(match.group(2).strip())
        ts_match = re.match(r"^\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]", line)
        if ts_match:
            try:
                timestamp = datetime.strptime(ts_match.group(1), "%Y-%m-%d %H:%M:%S").timestamp()
            except ValueError:
                timestamp = 0.0
        else:
            timestamp = 0.0
        return app_id, path, timestamp

    def _infer_source_from_path(self, file_path: Path) -> tuple[str, Path]:
        normalized = str(file_path).lower().replace("\\", "/")
        if "/steamapps/workshop/content/241100/" in normalized:
            return "workshop", file_path.parent
        for parent in file_path.parents:
            if parent.name == "controller_configs":
                return "userdata", parent
            if (
                parent.name == "config"
                and parent.parent.name.isdigit()
                and parent.parent.parent.name == "Steam Controller Configs"
            ):
                return "steam_controller_configs", parent
        return "unknown", file_path.parent

    def _safe_mtime(self, path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    def _is_recent(self, timestamp: float, max_hours: int) -> bool:
        if timestamp <= 0:
            return False
        age_seconds = datetime.now().timestamp() - timestamp
        return age_seconds <= max_hours * 3600

    def _log_source_layout_metadata(self, layout_text: str, source_path: Path) -> None:
        title = self._extract_vdf_value(layout_text, "title")
        export_type = self._extract_vdf_value(layout_text, "export_type")
        progenitor = self._extract_vdf_value(layout_text, "progenitor")
        url = self._extract_vdf_value(layout_text, "url")
        publishedfileid = self._extract_vdf_value(layout_text, "publishedfileid")
        steam_url = self._extract_steam_controller_url(layout_text)
        workshop_id = self._extract_workshop_id(layout_text, source_path)
        self._log(
            "[mirror] source meta "
            f"title={title or '-'} export_type={export_type or '-'} "
            f"progenitor={progenitor or '-'} publishedfileid={publishedfileid or '-'} "
            f"url={url or '-'} steam_url={steam_url or '-'} workshop_id={workshop_id or '-'}"
        )

    def _extract_vdf_value(self, text: str, key: str) -> str | None:
        match = re.search(rf'"{re.escape(key)}"\s*"([^"]*)"', text, flags=re.IGNORECASE)
        if not match:
            return None
        value = match.group(1).strip()
        return value or None

    def _extract_steam_controller_url(self, text: str) -> str | None:
        match = re.search(r"(steam://controllerconfig/\d+/\d+)", text, flags=re.IGNORECASE)
        if not match:
            return None
        return match.group(1)

    def _extract_workshop_id(self, text: str, source_path: Path) -> str | None:
        for sample in (text, str(source_path)):
            match = re.search(r"/steamapps/workshop/content/241100/(\d+)/", sample, flags=re.IGNORECASE)
            if match:
                return match.group(1)
        return None

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

    def _resolve_game_layout_output_dir(self, source: TemplateCandidate, app_id: int) -> Path:
        candidates = self._game_layout_output_dir_candidates(source, app_id)
        self._log(
            "[mirror] output_dir_candidates="
            + "[" + ", ".join(str(path) for path in candidates) + "]"
        )

        for path in candidates:
            if path.is_dir():
                return path

        for path in candidates:
            try:
                path.mkdir(parents=True, exist_ok=True)
                return path
            except OSError:
                continue

        fallback = source.path.parent
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

    def _game_layout_output_dir_candidates(self, source: TemplateCandidate, app_id: int) -> list[Path]:
        out: list[Path] = []

        # Primary target: Steam Controller Configs game layout directory.
        for config_root in self._steam_controller_configs_roots():
            out.append(config_root / str(app_id))

        # Keep near source as next best options.
        if source.source_kind in ("steam_controller_configs", "userdata"):
            out.append(source.controller_root / str(app_id))
        out.append(source.path.parent / str(app_id))
        out.append(source.path.parent)

        seen: set[Path] = set()
        deduped: list[Path] = []
        for path in out:
            if path in seen:
                continue
            seen.add(path)
            deduped.append(path)
        return deduped

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

    def _build_game_output_path(self, output_dir: Path, source_path: Path, app_id: int) -> Path:
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = source_path.stem
        suffix = source_path.suffix or ".vdf"
        candidate = output_dir / f"{stem}_app_{app_id}_mirror_{now}{suffix}"
        index = 1
        while candidate.exists():
            candidate = output_dir / f"{stem}_app_{app_id}_mirror_{now}_{index}{suffix}"
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
        mirror_menu_position: bool,
        mirror_gyro_buttons: bool,
    ) -> tuple[str, int]:
        transformed = template_text
        total_swaps = 0

        if mirror_dpad:
            transformed, swaps = self._swap_source_binding_pairs(
                transformed,
                [
                    ("button_diamond", "dpad"),
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
            stick_pairs = self._stick_pairs_for_text(transformed)
            transformed, swaps = self._swap_token_pairs(
                transformed,
                stick_pairs,
            )
            total_swaps += swaps

        if mirror_menu_position:
            transformed, swaps = self._mirror_touch_menu_position_x(transformed)
            total_swaps += swaps

        if mirror_gyro_buttons:
            transformed, swaps = self._mirror_gyro_button_tokens(transformed)
            total_swaps += swaps

        return transformed, total_swaps

    def _swap_token_pairs(self, text: str, pairs: list[tuple[str, str]]) -> tuple[str, int]:
        transformed = text
        total_replacements = 0

        expanded_pairs = self._expand_case_pairs(pairs)
        for idx, (left, right) in enumerate(expanded_pairs):
            token_boundary = r"[A-Za-z0-9_]"
            left_pattern = re.compile(
                rf"(?<!{token_boundary}){re.escape(left)}(?!{token_boundary})"
            )
            right_pattern = re.compile(
                rf"(?<!{token_boundary}){re.escape(right)}(?!{token_boundary})"
            )

            marker_left = f"__mirror_left_{idx}_{secrets.token_hex(6)}__"
            marker_right = f"__mirror_right_{idx}_{secrets.token_hex(6)}__"

            transformed, left_hits = left_pattern.subn(marker_left, transformed)
            transformed, right_hits = right_pattern.subn(marker_right, transformed)
            if left_hits == 0 and right_hits == 0:
                continue

            transformed = transformed.replace(marker_left, right)
            transformed = transformed.replace(marker_right, left)

            total_replacements += left_hits + right_hits

        return transformed, total_replacements

    def _swap_source_binding_pairs(
        self,
        text: str,
        pairs: list[tuple[str, str]],
    ) -> tuple[str, int]:
        lines = text.splitlines(keepends=True)
        out_lines: list[str] = []
        total_replacements = 0
        in_group_source_bindings = False
        pending_group_source_bindings = False
        group_source_depth = 0

        for line in lines:
            if not in_group_source_bindings and '"group_source_bindings"' in line.lower():
                pending_group_source_bindings = True
                out_lines.append(line)
                continue

            if pending_group_source_bindings:
                out_lines.append(line)
                group_source_depth += line.count("{")
                group_source_depth -= line.count("}")
                if "{" in line:
                    in_group_source_bindings = True
                    pending_group_source_bindings = False
                continue

            if in_group_source_bindings:
                swapped_line, replacements = self._swap_group_source_binding_line(line, pairs)
                total_replacements += replacements
                out_lines.append(swapped_line)
                group_source_depth += line.count("{")
                group_source_depth -= line.count("}")
                if group_source_depth <= 0:
                    in_group_source_bindings = False
                    group_source_depth = 0
                continue

            out_lines.append(line)

        return "".join(out_lines), total_replacements

    def _swap_group_source_binding_line(
        self, line: str, pairs: list[tuple[str, str]]
    ) -> tuple[str, int]:
        has_newline = line.endswith("\n")
        body = line[:-1] if has_newline else line
        match = re.match(r'^(\s*"[^"]+"\s*")([^"]*)(".*)$', body)
        if not match:
            return line, 0

        value = match.group(2)
        value_parts = re.match(r"^(\s*)(\S+)(.*)$", value)
        if not value_parts:
            return line, 0

        leading_ws = value_parts.group(1)
        token = value_parts.group(2)
        trailing = value_parts.group(3)
        swapped_token = self._swap_token_value(token, pairs)
        if swapped_token == token:
            return line, 0

        swapped_value = f"{leading_ws}{swapped_token}{trailing}"
        rebuilt = f"{match.group(1)}{swapped_value}{match.group(3)}"
        if has_newline:
            rebuilt += "\n"
        return rebuilt, 1

    def _swap_literal_pair(self, text: str, left: str, right: str) -> tuple[str, int]:
        marker_left = f"__mirror_lit_left_{secrets.token_hex(6)}__"
        marker_right = f"__mirror_lit_right_{secrets.token_hex(6)}__"
        transformed = text
        left_hits = transformed.count(left)
        right_hits = transformed.count(right)
        if left_hits == 0 and right_hits == 0:
            return text, 0

        transformed = transformed.replace(left, marker_left)
        transformed = transformed.replace(right, marker_right)
        transformed = transformed.replace(marker_left, right)
        transformed = transformed.replace(marker_right, left)
        return transformed, left_hits + right_hits

    def _swap_token_value(self, token: str, pairs: list[tuple[str, str]]) -> str:
        for left, right in pairs:
            if token == left:
                return right
            if token == right:
                return left
            if token.lower() == left.lower():
                return right.lower() if token.islower() else right
            if token.lower() == right.lower():
                return left.lower() if token.islower() else left
        return token

    def _stick_pairs_for_text(self, text: str) -> list[tuple[str, str]]:
        has_left_joystick = self._token_hits(text, "left_joystick") > 0
        has_right_joystick = self._token_hits(text, "right_joystick") > 0
        joystick_pair = ("joystick", "left_joystick") if has_left_joystick and not has_right_joystick else (
            "joystick",
            "right_joystick",
        )
        return [
            joystick_pair,
            ("left_stick", "right_stick"),
            ("stick_left", "stick_right"),
            ("joystick_left", "joystick_right"),
            ("left_analog", "right_analog"),
            ("analog_left", "analog_right"),
        ]

    def _token_hits(self, text: str, token: str) -> int:
        token_boundary = r"[A-Za-z0-9_]"
        pattern = re.compile(
            rf"(?<!{token_boundary}){re.escape(token)}(?!{token_boundary})",
            flags=re.IGNORECASE,
        )
        return len(pattern.findall(text))

    def _mirror_touch_menu_position_x(self, text: str) -> tuple[str, int]:
        pattern = re.compile(
            r'("touch_menu_position_x"\s*")([^"]*)(")',
            flags=re.IGNORECASE,
        )
        replacements = 0

        def repl(match: re.Match[str]) -> str:
            nonlocal replacements
            current_value = match.group(2).strip()
            mirrored = self._mirror_position_value(current_value)
            if mirrored is None or mirrored == current_value:
                return match.group(0)
            replacements += 1
            return f'{match.group(1)}{mirrored}{match.group(3)}'

        return pattern.sub(repl, text), replacements

    def _mirror_position_value(self, value: str) -> str | None:
        try:
            numeric = float(value)
        except ValueError:
            return None

        if numeric < 0:
            return None
        if numeric <= 1.0:
            scale = 1.0
        elif numeric <= 100.0:
            scale = 100.0
        else:
            return None

        mirrored = max(0.0, min(scale, scale - numeric))
        if "." in value:
            decimals = max(len(value.split(".", 1)[1]), 1)
            return f"{mirrored:.{decimals}f}"
        return str(int(round(mirrored)))

    def _mirror_gyro_button_tokens(self, text: str) -> tuple[str, int]:
        lines = text.splitlines(keepends=True)
        total_replacements = 0
        out_lines: list[str] = []
        gyro_pairs = [
            ("left_trigger", "right_trigger"),
            ("left_bumper", "right_bumper"),
            ("left_trackpad", "right_trackpad"),
            ("left_touchpad", "right_touchpad"),
            ("left_pad", "right_pad"),
            ("left_stick", "right_stick"),
            ("left_joystick", "right_joystick"),
            ("joystick_left", "joystick_right"),
            ("stick_left", "stick_right"),
            ("button_back_left", "button_back_right"),
            ("back_left", "back_right"),
            ("button_l4", "button_r4"),
            ("l4", "r4"),
        ]

        for line in lines:
            if "gyro" not in line.lower():
                out_lines.append(line)
                continue
            transformed_line, replacements = self._swap_token_pairs(line, gyro_pairs)
            total_replacements += replacements
            out_lines.append(transformed_line)

        return "".join(out_lines), total_replacements

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
