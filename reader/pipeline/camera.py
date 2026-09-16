"""Camera abstraction. FswebcamCamera is byte-for-byte the deployed capture
(same arguments, same lock)."""
from __future__ import annotations

import io
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows dev box
    fcntl = None


@dataclass
class Frame:
    jpeg: bytes
    captured_wall: float            # epoch seconds
    captured_mono: float
    source: str = "camera"          # camera | archive | dark
    ident: str = ""                 # archive stem or capture path, for memoisation
    _rgb: Optional[np.ndarray] = field(default=None, repr=False)
    _luma: Optional[float] = field(default=None, repr=False)

    def luma(self) -> Optional[float]:
        """Mean luma via PIL draft decode (~1.4 ms). None if the JPEG is broken."""
        if self._luma is None:
            try:
                with Image.open(io.BytesIO(self.jpeg)) as im:
                    im.draft("L", (160, 96))
                    arr = np.asarray(im.convert("L"), dtype=np.float32)
                self._luma = float(arr.mean()) if arr.size else None
            except (OSError, ValueError, SyntaxError):
                self._luma = None
        return self._luma

    def rgb(self) -> Optional[np.ndarray]:
        if self._rgb is None:
            try:
                with Image.open(io.BytesIO(self.jpeg)) as im:
                    self._rgb = np.asarray(im.convert("RGB"))
            except OSError:
                return None
        return self._rgb


class CaptureBusy(Exception):
    """Another process holds the camera lock."""


class CaptureFailed(Exception):
    """fswebcam timed out, died, or wrote garbage."""


class FswebcamCamera:
    """The Pi camera. Holds the flock only across fswebcam, never across inference."""

    def __init__(self, clock, resolution=(1280, 720), lock_path: str = "/run/lock/kahvicam.lock",
                 tmp_path: str = "/run/kahvi-sampler/frame.jpg", timeout: float = 8.0,
                 lock_wait: float = 0.0):
        self.clock = clock
        self.resolution = resolution
        self.lock_path = lock_path
        self.tmp_path = Path(tmp_path)
        self.timeout = timeout
        self.lock_wait = lock_wait

    def capture(self) -> Frame:
        lock_fd = None
        try:
            if fcntl is not None and self.lock_path:
                lock_fd = open(self.lock_path, "a+b")
                flags = fcntl.LOCK_EX | (0 if self.lock_wait else fcntl.LOCK_NB)
                try:
                    fcntl.flock(lock_fd, flags)
                except OSError:
                    raise CaptureBusy()
            self.tmp_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.unlink(self.tmp_path)
            except OSError:
                pass
            w, h = self.resolution
            cmd = ["fswebcam", "--quiet", "-S", "20", "--no-banner",
                   "--resolution", f"{w}x{h}", str(self.tmp_path)]
            t_mono = self.clock.mono()
            t_wall = self.clock.wall()
            try:
                subprocess.run(cmd, timeout=self.timeout,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except (subprocess.TimeoutExpired, OSError):
                raise CaptureFailed()
            try:
                data = self.tmp_path.read_bytes()
            except OSError:
                raise CaptureFailed()
            if not data:
                raise CaptureFailed()
            return Frame(data, t_wall, t_mono, source="camera", ident=str(self.tmp_path))
        finally:
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                except (OSError, ValueError):
                    pass
                lock_fd.close()
