import subprocess
import sys
import tempfile
import threading
import uuid
from pathlib import Path

_MCI_ALIAS = "audio2ogg_preview"


def _subprocess_extra() -> dict:
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


class _WindowsMci:
    def __init__(self) -> None:
        self._winmm = None
        if sys.platform == "win32":
            try:
                import ctypes

                self._winmm = ctypes.WinDLL("winmm")
            except Exception:
                self._winmm = None

    @property
    def available(self) -> bool:
        return self._winmm is not None

    def send(self, command: str) -> int:
        if self._winmm is None:
            return 1
        return int(self._winmm.mciSendStringW(command, None, 0, None))

    def query(self, command: str) -> str:
        if self._winmm is None:
            return ""
        import ctypes

        buffer = ctypes.create_unicode_buffer(255)
        self._winmm.mciSendStringW(command, buffer, 255, None)
        return buffer.value.strip()

    def close(self) -> None:
        self.send(f"close {_MCI_ALIAS}")

    def play(self, path: Path) -> bool:
        self.close()
        escaped = str(path.resolve()).replace('"', '\\"')
        if self.send(f'open "{escaped}" type waveaudio alias {_MCI_ALIAS}') != 0:
            return False
        return self.send(f"play {_MCI_ALIAS}") == 0

    def stop(self) -> None:
        self.send(f"stop {_MCI_ALIAS}")
        self.close()

    def mode(self) -> str:
        return self.query(f"status {_MCI_ALIAS} mode").lower()


class AudioPlayer:
    def __init__(
        self,
        ffmpeg_path: Path | None,
        ffplay_path: Path | None,
    ) -> None:
        self._ffmpeg_path = ffmpeg_path
        self._ffplay_path = ffplay_path
        self._mci = _WindowsMci()
        self._proc: subprocess.Popen[bytes] | None = None
        self._current: Path | None = None
        self._backend: str | None = None
        self._temp_wav: Path | None = None
        self._lock = threading.Lock()

    @property
    def ffplay_path(self) -> Path | None:
        return self._ffplay_path

    @property
    def can_play(self) -> bool:
        if self._ffplay_path is not None:
            return True
        return sys.platform == "win32" and self._ffmpeg_path is not None and self._mci.available

    @property
    def current_path(self) -> Path | None:
        if not self.is_playing():
            return None
        with self._lock:
            return self._current

    def is_playing(self, path: Path | None = None) -> bool:
        with self._lock:
            backend = self._backend
            current = self._current
            proc = self._proc

        if backend == "ffplay":
            if proc is None or proc.poll() is not None:
                self._reset_state()
                return False
        elif backend == "mci":
            if self._mci.mode() != "playing":
                self._reset_state()
                return False
        else:
            return False

        if path is None:
            return True
        return current is not None and current.resolve() == path.resolve()

    def stop(self) -> None:
        with self._lock:
            backend = self._backend
            proc = self._proc
            self._proc = None
            self._current = None
            self._backend = None
            temp_wav = self._temp_wav
            self._temp_wav = None

        if backend == "ffplay" and proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        elif backend == "mci":
            self._mci.stop()

        if temp_wav is not None:
            try:
                temp_wav.unlink(missing_ok=True)
            except OSError:
                pass

    def play(self, path: Path) -> bool:
        if not path.exists() or not self.can_play:
            return False

        self.stop()
        if self._ffplay_path is not None:
            return self._play_ffplay(path)
        return self._play_via_ffmpeg_mci(path)

    def _play_ffplay(self, path: Path) -> bool:
        cmd = [
            str(self._ffplay_path),
            "-nodisp",
            "-autoexit",
            "-hide_banner",
            "-loglevel",
            "quiet",
            str(path),
        ]
        try:
            proc = subprocess.Popen(cmd, **_subprocess_extra())
        except OSError:
            return False

        with self._lock:
            self._proc = proc
            self._current = path
            self._backend = "ffplay"
        return True

    def _play_via_ffmpeg_mci(self, path: Path) -> bool:
        if self._ffmpeg_path is None or not self._mci.available:
            return False

        preview_dir = Path(tempfile.gettempdir()) / "audio2ogg-preview"
        preview_dir.mkdir(parents=True, exist_ok=True)
        temp_wav = preview_dir / f"{uuid.uuid4().hex}.wav"

        cmd = [
            str(self._ffmpeg_path),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(path),
            "-ac",
            "2",
            "-ar",
            "44100",
            str(temp_wav),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, **_subprocess_extra())
        except OSError:
            return False

        if proc.returncode != 0 or not temp_wav.exists():
            try:
                temp_wav.unlink(missing_ok=True)
            except OSError:
                pass
            return False

        if not self._mci.play(temp_wav):
            try:
                temp_wav.unlink(missing_ok=True)
            except OSError:
                pass
            return False

        with self._lock:
            self._current = path
            self._backend = "mci"
            self._temp_wav = temp_wav
        return True

    def _reset_state(self) -> None:
        with self._lock:
            temp_wav = self._temp_wav
            self._proc = None
            self._current = None
            self._backend = None
            self._temp_wav = None
        if temp_wav is not None:
            try:
                temp_wav.unlink(missing_ok=True)
            except OSError:
                pass
        self._mci.close()
