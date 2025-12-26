"""Fast video preview decoding using FFmpeg rawvideo pipes."""

from __future__ import annotations

import subprocess
from typing import Optional

from PIL import Image

from .ffmpeg_utils import FFMPEG


class VideoPreviewStream:
    """Decode preview frames without spawning FFmpeg per-frame."""

    def __init__(self, fps: float = 30.0, max_skip_seconds: float = 2.0):
        self._fps = float(fps)
        self._max_skip_frames = max(1, int(round(float(max_skip_seconds) * self._fps)))

        self._proc: Optional[subprocess.Popen] = None
        self._filepath: Optional[str] = None
        self._width: int = 0
        self._height: int = 0

        self._base_time: float = 0.0
        self._next_index: int = 0  # next frame index to read
        self._frame_size: int = 0
        self._last_frame: Optional[Image.Image] = None

    def close(self) -> None:
        proc = self._proc
        self._proc = None
        self._filepath = None
        self._width = 0
        self._height = 0
        self._base_time = 0.0
        self._next_index = 0
        self._frame_size = 0
        self._last_frame = None

        if not proc:
            return

        try:
            if proc.stdout:
                proc.stdout.close()
        except Exception:
            pass
        try:
            if proc.stderr:
                proc.stderr.close()
        except Exception:
            pass

        try:
            proc.terminate()
            proc.wait(timeout=1)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def get_frame(self, filepath: str, time: float, width: int, height: int) -> Optional[Image.Image]:
        """Return a preview frame for `filepath` at `time` seconds."""
        if not filepath:
            return None

        try:
            time = max(0.0, float(time))
        except Exception:
            time = 0.0

        try:
            width = int(width)
            height = int(height)
        except Exception:
            return None

        if width <= 0 or height <= 0:
            return None

        if (
            not self._proc
            or self._proc.poll() is not None
            or self._filepath != filepath
            or self._width != width
            or self._height != height
        ):
            if not self._start(filepath=filepath, start_time=time, width=width, height=height):
                return None

        target_index = int(round((time - self._base_time) * self._fps))
        last_index = self._next_index - 1

        if target_index <= last_index:
            # Minor timestamp jitter can go backwards by ~1 frame; avoid restarting in that case.
            if self._last_frame is not None and target_index >= (last_index - 1):
                return self._last_frame

            if not self._start(filepath=filepath, start_time=time, width=width, height=height):
                return None
            target_index = 0
            last_index = -1

        reads_needed = target_index - last_index
        if reads_needed <= 0 and self._last_frame is not None:
            return self._last_frame

        if reads_needed > self._max_skip_frames:
            if not self._start(filepath=filepath, start_time=time, width=width, height=height):
                return None
            target_index = 0
            last_index = -1
            reads_needed = 1

        last = None
        for i in range(reads_needed):
            raw = self._read_raw_frame()
            if not raw:
                self.close()
                return None
            self._next_index += 1
            if i == reads_needed - 1:
                last = raw

        if last is None:
            return None

        try:
            image = Image.frombytes("RGB", (width, height), last)
            self._last_frame = image
            return image
        except Exception:
            return None

    def _read_raw_frame(self) -> Optional[bytes]:
        if not self._proc or not self._proc.stdout or self._frame_size <= 0:
            return None
        try:
            data = self._proc.stdout.read(self._frame_size)
            if not data or len(data) != self._frame_size:
                return None
            return data
        except Exception:
            return None

    def _start(self, filepath: str, start_time: float, width: int, height: int) -> bool:
        self.close()

        self._filepath = filepath
        self._width = width
        self._height = height
        self._base_time = float(start_time)
        self._next_index = 0
        self._frame_size = int(width) * int(height) * 3
        self._last_frame = None

        scale = (
            f"scale='min(iw,{width})':'min(ih,{height})':force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,"
            f"fps={self._fps}"
        )

        cmd = [
            FFMPEG,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-ss",
            f"{start_time:.3f}",
            "-i",
            filepath,
            "-an",
            "-vf",
            scale,
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ]

        creationflags = 0
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags = subprocess.CREATE_NO_WINDOW

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            return True
        except Exception:
            self.close()
            return False
