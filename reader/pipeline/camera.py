"""Camera abstraction. FswebcamCamera is byte-for-byte the deployed capture
(same arguments, same lock)."""
from __future__ import annotations

import io
import os
import re
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
    """fswebcam timed out, died, or wrote garbage. The message says which."""


# fswebcam colours its messages, and the reset code lands on a line of its own
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _last_line(text: str) -> str:
    lines = [ln.strip() for ln in _ANSI.sub("", text).splitlines() if ln.strip()]
    return lines[-1] if lines else "no output"


class FswebcamCamera:
    """The Pi camera. Holds the flock only across fswebcam, never across inference.

    `reset_cmd`, when given, re-enumerates the webcam on the USB bus. An
    under-voltage URB drop leaves the camera present but sending nothing
    (2026-10-27 and 2026-10-29), and before this only a reboot brought it back.
    """

    def __init__(self, clock, resolution=(1280, 720), lock_path: str = "/run/lock/kahvicam.lock",
                 tmp_path: str = "/run/kahvi-sampler/frame.jpg", timeout: float = 8.0,
                 lock_wait: float = 0.0, reset_cmd: Optional[list] = None,
                 reset_timeout: float = 30.0):
        self.clock = clock
        self.resolution = resolution
        self.lock_path = lock_path
        self.tmp_path = Path(tmp_path)
        self.timeout = timeout
        self.lock_wait = lock_wait
        self.reset_cmd = list(reset_cmd) if reset_cmd else None
        self.reset_timeout = reset_timeout

    def reset(self) -> "tuple[bool, str]":
        """Run the reset command. Returns (ok, its last line of output)."""
        if not self.reset_cmd:
            return False, "no reset command configured"
        try:
            p = subprocess.run(self.reset_cmd, timeout=self.reset_timeout,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        except subprocess.TimeoutExpired:
            return False, "timed out after %.0f s" % self.reset_timeout
        except OSError as e:
            return False, str(e)
        detail = _last_line(p.stdout.decode("utf-8", "replace"))
        if p.returncode != 0:
            detail = "exit %d: %s" % (p.returncode, detail)
        return p.returncode == 0, detail

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
            # stderr is kept: fswebcam 20140113 exits 0 on error, so its last
            # line is the only record of why a capture produced nothing.
            try:
                p = subprocess.run(cmd, timeout=self.timeout,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            except subprocess.TimeoutExpired:
                raise CaptureFailed("fswebcam timed out after %.0f s" % self.timeout)
            except OSError as e:
                raise CaptureFailed("fswebcam did not run: %s" % e)
            why = _last_line(p.stderr.decode("utf-8", "replace"))
            try:
                data = self.tmp_path.read_bytes()
            except OSError:
                raise CaptureFailed("no frame written (exit %d): %s" % (p.returncode, why))
            if not data:
                raise CaptureFailed("empty frame (exit %d): %s" % (p.returncode, why))
            return Frame(data, t_wall, t_mono, source="camera", ident=str(self.tmp_path))
        finally:
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                except (OSError, ValueError):
                    pass
                lock_fd.close()
