import queue
import shutil
import subprocess
import sys
from pathlib import Path

from .constants import AUDIO_EXTENSIONS


def resolve_ffmpeg_path() -> Path | None:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bundled = Path(meipass) / "ffmpeg" / "ffmpeg.exe"
        if bundled.exists():
            return bundled

    local_vendor = Path(__file__).resolve().parent.parent / "vendor" / "ffmpeg.exe"
    if local_vendor.exists():
        return local_vendor

    in_path = shutil.which("ffmpeg")
    if in_path:
        return Path(in_path)

    return None


def build_output_path(src: Path, out_dir: Path) -> Path:
    candidate = out_dir / f"{src.stem}.ogg"
    idx = 1
    while candidate.exists():
        candidate = out_dir / f"{src.stem}_{idx}.ogg"
        idx += 1
    return candidate


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


def run_conversion(
    ffmpeg_path: Path,
    files: list[Path],
    out_dir: Path,
    result_queue: "queue.Queue[str]",
    t: "callable",
) -> None:
    ok = 0
    failed = 0
    total = len(files)

    for idx, src in enumerate(files, 1):
        dst = build_output_path(src, out_dir)
        cmd = [
            str(ffmpeg_path),
            "-hide_banner",
            "-y",
            "-i", str(src),
            "-vn",
            "-c:a", "libvorbis",
            "-q:a", "5",
            str(dst),
        ]

        result_queue.put(f"PROGRESS::{idx - 1}::{total}::{src.name}")
        result_queue.put(t("log_converting", src=src.name, dst=dst.name))
        extra = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
        proc = subprocess.run(cmd, capture_output=True, text=True, **extra)

        if proc.returncode == 0:
            ok += 1
            result_queue.put(t("log_ok", name=dst.name))
        else:
            failed += 1
            err = (proc.stderr or proc.stdout or "").strip()
            short_err = err[-240:] if err else t("log_error_unknown")
            result_queue.put(t("log_error", name=src.name, err=short_err))

    result_queue.put(f"DONE::{ok}::{failed}")
