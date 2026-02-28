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
    def __init__(self, app_id: int, path: Path, mtime: float) -> None:
        self.app_id = app_id
        self.path = path
        self.mtime = mtime

    @property
    def is_mirror(self) -> bool:
        return "mirror" in self.path.name.lower()


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
        source = self._find_source_template(app_id if app_id > 0 else None)
        if source is None:
            return {
                "ok": False,
                "error": "Could not find a controller template for the current game.",
            }

        original = source.path.read_text(encoding="utf-8", errors="ignore")
        mirrored, swaps = self._build_mirrored_template(
            original,
            mirror_dpad=mirror_dpad,
            mirror_touchpads=mirror_touchpads,
            mirror_sticks=mirror_sticks,
        )
        mirrored = self._append_title_suffix(mirrored)

        output_path = self._build_output_path(source.path)
        output_path.write_text(mirrored, encoding="utf-8")

        self._log(
            f"Created mirror template app_id={source.app_id} source={source.path} output={output_path}"
        )
        return {
            "ok": True,
            "app_id": source.app_id,
            "source_path": str(source.path),
            "output_path": str(output_path),
            "swapped_tokens": swaps,
        }

    def _find_source_template(self, app_id: int | None) -> TemplateCandidate | None:
        candidates: list[TemplateCandidate] = []
        for root in self._controller_config_roots():
            if app_id is not None:
                app_dir = root / str(app_id)
                if app_dir.is_dir():
                    candidates.extend(self._collect_candidates_for_app_dir(app_dir))
                continue

            for maybe_app_dir in self._safe_iterdir(root):
                if not maybe_app_dir.is_dir() or not maybe_app_dir.name.isdigit():
                    continue
                candidates.extend(self._collect_candidates_for_app_dir(maybe_app_dir))

        if not candidates:
            return None

        non_mirror = [c for c in candidates if not c.is_mirror]
        source_pool = non_mirror if non_mirror else candidates
        return max(source_pool, key=lambda c: c.mtime)

    def _collect_candidates_for_app_dir(self, app_dir: Path) -> list[TemplateCandidate]:
        app_id = int(app_dir.name)
        out: list[TemplateCandidate] = []
        for root, _, files in os.walk(app_dir, topdown=True, followlinks=False, onerror=lambda _: None):
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
                out.append(TemplateCandidate(app_id=app_id, path=file_path, mtime=mtime))
        return out

    def _controller_config_roots(self) -> Iterable[Path]:
        home = Path.home()
        userdata_roots = [
            home / ".local" / "share" / "Steam" / "userdata",
            home / ".steam" / "steam" / "userdata",
            home / ".steam" / "root" / "userdata",
        ]
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

    def _safe_iterdir(self, path: Path) -> list[Path]:
        try:
            return list(path.iterdir())
        except OSError:
            return []

    def _build_output_path(self, source_path: Path) -> Path:
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = source_path.stem
        suffix = source_path.suffix or ".vdf"
        candidate = source_path.with_name(f"{stem}_mirror_{now}{suffix}")
        index = 1
        while candidate.exists():
            candidate = source_path.with_name(f"{stem}_mirror_{now}_{index}{suffix}")
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
