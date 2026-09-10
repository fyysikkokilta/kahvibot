"""Camera abstraction. FswebcamCamera is byte-for-byte the deployed capture
(same arguments, same lock); ArchiveCamera replays the frame archive for the gym."""
from __future__ import annotations

import collections
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


def _dark_jpeg(size=(1280, 720)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (2, 2, 2)).save(buf, "JPEG", quality=50)
    return buf.getvalue()


class ArchiveSource:
    """Frames from the archive by wall time, with the decoded RGB and luma cached
    per stem (the sampler ticks every 10 s against a 5-minute archive). When no
    frame lies within `max_gap_s` (nights, poller off) a dark frame is returned
    so the dark gate behaves as it would in the real room."""

    def __init__(self, archive, max_gap_s: float = 1200.0, cache_size: int = 16):
        self.archive = archive
        self.max_gap_s = max_gap_s
        self._cache: "collections.OrderedDict[str, tuple]" = collections.OrderedDict()
        self.cache_size = cache_size
        self._dark = _dark_jpeg()
        self._dark_rgb = None
        self.frames_served = 0
        self.dark_served = 0

    def frame_at(self, wall: float, mono: float) -> Frame:
        self.frames_served += 1
        hit = self.archive.nearest(wall)
        if hit is None or abs(hit.epoch - wall) > self.max_gap_s:
            self.dark_served += 1
            fr = Frame(self._dark, wall, mono, source="dark", ident="dark")
            fr._luma = 2.0
            return fr
        ent = self._cache.get(hit.stem)
        if ent is None:
            jpeg = hit.read()
            probe = Frame(jpeg, wall, mono)
            ent = (jpeg, probe.rgb(), probe.luma())
            self._cache[hit.stem] = ent
            if len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
        else:
            self._cache.move_to_end(hit.stem)
        jpeg, rgb, luma = ent
        fr = Frame(jpeg, wall, mono, source="archive", ident=hit.stem)
        fr._rgb, fr._luma = rgb, luma
        return fr


class ArchiveCamera:
    """Camera facade over ArchiveSource for the ReaderService: charges a fixed
    Pi capture cost to the (virtual) clock, then returns the frame at the
    capture instant."""

    def __init__(self, archive, clock, capture_cost_s: float = 2.0, max_gap_s: float = 1200.0,
                 source: Optional[ArchiveSource] = None):
        self.src = source or ArchiveSource(archive, max_gap_s)
        self.clock = clock
        self.capture_cost_s = capture_cost_s
        self.captures = 0

    @property
    def dark_captures(self):
        return self.src.dark_served

    def capture(self) -> Frame:
        t_mono = self.clock.mono()
        t_wall = self.clock.wall()
        self.clock.sleep(self.capture_cost_s)
        self.captures += 1
        return self.src.frame_at(t_wall, t_mono)
