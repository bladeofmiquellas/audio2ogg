import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .constants import AUDIO_EXTENSIONS, QUALITY_BITRATE_BPS

ConflictResolver = Callable[[Path, Path], str]


def format_byte_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    if size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{size / (1024 * 1024 * 1024):.2f} GB"


@dataclass(frozen=True)
class ConversionOptions:
    quality: int = 5
    channels: str = "original"
    sample_rate: str = "48000"


def resolve_ffmpeg_path() -> Path | None:
    return _resolve_tool("ffmpeg.exe")


def resolve_ffprobe_path(ffmpeg_path: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    if ffmpeg_path is not None:
        candidates.append(ffmpeg_path.parent / "ffprobe.exe")
    candidates.extend(_tool_search_paths("ffprobe.exe"))
    return _first_existing(candidates)


def resolve_ffplay_path(ffmpeg_path: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    if ffmpeg_path is not None:
        candidates.append(ffmpeg_path.parent / "ffplay.exe")
    candidates.extend(_tool_search_paths("ffplay.exe"))
    return _first_existing(candidates)


def _tool_search_paths(filename: str) -> list[Path]:
    paths: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        paths.append(Path(meipass) / "ffmpeg" / filename)
    paths.append(Path(__file__).resolve().parent.parent / "vendor" / filename)
    in_path = shutil.which(filename.removesuffix(".exe") if filename.endswith(".exe") else filename)
    if in_path:
        paths.append(Path(in_path))
    return paths


def _first_existing(candidates: list[Path]) -> Path | None:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _resolve_tool(filename: str) -> Path | None:
    return _first_existing(_tool_search_paths(filename))


def probe_audio_duration(
    src: Path,
    *,
    ffmpeg_path: Path,
    ffprobe_path: Path | None = None,
) -> float | None:
    if ffprobe_path is not None:
        duration = _probe_with_ffprobe(ffprobe_path, src)
        if duration is not None:
            return duration
    return _probe_with_ffmpeg(ffmpeg_path, src)


def _probe_with_ffprobe(ffprobe_path: Path, src: Path) -> float | None:
    cmd = [
        str(ffprobe_path),
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(src),
    ]
    extra = _subprocess_extra()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, **extra)
        if proc.returncode != 0:
            return None
        value = (proc.stdout or "").strip()
        return float(value) if value else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


def _probe_with_ffmpeg(ffmpeg_path: Path, src: Path) -> float | None:
    cmd = [str(ffmpeg_path), "-hide_banner", "-i", str(src)]
    extra = _subprocess_extra()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, **extra)
    except (OSError, subprocess.TimeoutExpired):
        return None

    match = re.search(
        r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",
        proc.stderr or "",
    )
    if not match:
        return None

    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _subprocess_extra() -> dict:
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def build_output_path(src: Path, out_dir: Path) -> Path:
    candidate = out_dir / f"{src.stem}.ogg"
    idx = 1
    while candidate.exists():
        candidate = out_dir / f"{src.stem}_{idx}.ogg"
        idx += 1
    return candidate


def output_target_path(src: Path, out_dir: Path) -> Path:
    return out_dir / f"{src.stem}.ogg"


def apply_conflict_policy(src: Path, out_dir: Path, policy: str) -> Path | None:
    if policy == "overwrite":
        return output_target_path(src, out_dir)
    if policy == "skip":
        return None
    return build_output_path(src, out_dir)


def expand_input_paths(paths: list[Path]) -> list[Path]:
    expanded: list[Path] = []
    seen_dirs: set[Path] = set()

    for path in paths:
        if not path.exists():
            continue
        if path.is_file():
            expanded.append(path)
            continue
        if not path.is_dir():
            continue

        resolved_dir = path.resolve()
        if resolved_dir in seen_dirs:
            continue
        seen_dirs.add(resolved_dir)

        for child in sorted(path.rglob("*")):
            if child.is_file() and child.suffix.lower() in AUDIO_EXTENSIONS:
                expanded.append(child)

    return expanded


def filter_audio_files(paths: list[Path], existing: set[Path]) -> tuple[list[Path], int]:
    accepted: list[Path] = []
    skipped = 0
    for p in paths:
        if not p.exists() or not p.is_file():
            skipped += 1
            continue
        if p.suffix.lower() not in AUDIO_EXTENSIONS:
            skipped += 1
            continue
        resolved = p.resolve()
        if resolved in existing:
            skipped += 1
            continue
        accepted.append(p)
        existing.add(resolved)
    return accepted, skipped


def build_ffmpeg_cmd(
    ffmpeg_path: Path,
    src: Path,
    dst: Path,
    options: ConversionOptions,
) -> list[str]:
    cmd = [
        str(ffmpeg_path),
        "-hide_banner",
        "-y",
        "-i", str(src),
        "-vn",
        "-c:a", "libvorbis",
        "-q:a", str(options.quality),
    ]
    if options.channels != "original":
        cmd.extend(["-ac", options.channels])
    cmd.extend(["-ar", options.sample_rate])
    cmd.append(str(dst))
    return cmd


def _estimate_output_channels(options: ConversionOptions, source_channels: int = 2) -> int:
    if options.channels == "original":
        return max(1, source_channels)
    return int(options.channels)


def estimate_output_bytes(
    duration: float | None,
    source_size: int,
    options: ConversionOptions,
    *,
    source_channels: int = 2,
) -> int:
    if duration and duration > 0:
        base_bps = QUALITY_BITRATE_BPS.get(options.quality, 160_000)
        out_channels = _estimate_output_channels(options, source_channels)
        out_rate = int(options.sample_rate)
        effective_bps = base_bps * (out_channels / 2) * (out_rate / 48_000)
        return max(1, int(duration * effective_bps / 8))

    if source_size > 0:
        fallback_ratio = {3: 0.35, 5: 0.5, 7: 0.7}.get(options.quality, 0.5)
        return max(1, int(source_size * fallback_ratio))

    return 0


def estimate_conversion_sizes(
    files: list[Path],
    durations: dict[Path, float],
    options: ConversionOptions,
) -> tuple[int, int]:
    input_bytes = 0
    output_bytes = 0

    for path in files:
        try:
            source_size = path.stat().st_size
        except OSError:
            continue
        input_bytes += source_size
        duration = durations.get(path.resolve())
        output_bytes += estimate_output_bytes(duration, source_size, options)

    return input_bytes, output_bytes


def _run_ffmpeg(
    cmd: list[str],
    cancel_event: threading.Event | None,
    extra: dict,
) -> subprocess.CompletedProcess[str] | None:
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        **extra,
    )
    while proc.poll() is None:
        if cancel_event and cancel_event.is_set():
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            return None
        time.sleep(0.1)
    stdout, stderr = proc.communicate()
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)


def run_conversion(
    ffmpeg_path: Path,
    files: list[Path],
    out_dir: Path,
    options: ConversionOptions,
    result_queue: "queue.Queue[str]",
    t: "callable",
    conflict_resolver: ConflictResolver | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    ok = 0
    failed = 0
    skipped = 0
    input_bytes = 0
    output_bytes = 0
    total = len(files)

    for idx, src in enumerate(files, 1):
        if cancel_event and cancel_event.is_set():
            break

        result_queue.put(f"PROGRESS::{idx - 1}::{total}::{src.name}")

        target = output_target_path(src, out_dir)
        if target.exists():
            policy = conflict_resolver(src, target) if conflict_resolver else "rename"
            dst = apply_conflict_policy(src, out_dir, policy)
        else:
            dst = target

        if dst is None:
            skipped += 1
            result_queue.put(t("log_skipped_exists", name=src.name))
            result_queue.put(f"PROGRESS::{idx}::{total}::{src.name}")
            continue

        cmd = build_ffmpeg_cmd(ffmpeg_path, src, dst, options)

        result_queue.put(t("log_converting", src=src.name, dst=dst.name))
        extra = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
        proc = _run_ffmpeg(cmd, cancel_event, extra)

        if proc is None:
            break

        if proc.returncode == 0:
            ok += 1
            result_queue.put(t("log_ok", name=dst.name))
            try:
                input_bytes += src.stat().st_size
                output_bytes += dst.stat().st_size
            except OSError:
                pass
        else:
            failed += 1
            err = (proc.stderr or proc.stdout or "").strip()
            short_err = err[-240:] if err else t("log_error_unknown")
            result_queue.put(t("log_error", name=src.name, err=short_err))

        result_queue.put(f"PROGRESS::{idx}::{total}::{src.name}")

    if cancel_event and cancel_event.is_set():
        result_queue.put(f"CANCELLED::{ok}::{failed}::{skipped}::{input_bytes}::{output_bytes}")
    else:
        result_queue.put(f"DONE::{ok}::{failed}::{skipped}::{input_bytes}::{output_bytes}")
