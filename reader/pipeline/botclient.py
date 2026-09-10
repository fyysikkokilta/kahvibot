"""What kahvibot calls. Keeps the bot's failure discipline: any problem here
returns None and the bot falls back to its own fswebcam path without a reading.

    from pipeline.botclient import ReaderClient
    rc = ReaderClient("/run/kahvi-sampler/ipc.sock")
    got = rc.photo(max_age=15)        # -> (jpeg_bytes, pots, meta) or None
    png, caption = rc.graph()         # -> (bytes|None, str) or (None, None)
"""
from __future__ import annotations

from typing import Optional

from .ipc import Client


class ReaderClient:
    def __init__(self, addr, timeout: float = 3.0):
        self.client = Client(addr, timeout)

    def photo(self, max_age: float = 15.0):
        try:
            hdr, body = self.client.call({"op": "frame", "max_age": max_age})
        except (OSError, ValueError):
            return None
        if not hdr.get("ok") or not body:
            return None
        return body, hdr.get("pots", []), {"age": hdr.get("age"), "reused": hdr.get("reused"),
                                          "seq": hdr.get("seq"), "captured_at": hdr.get("captured_at")}

    def graph(self):
        try:
            hdr, body = self.client.call({"op": "graph"})
        except (OSError, ValueError):
            return None, None
        if not hdr.get("ok"):
            return None, None
        return (body or None), hdr.get("caption")

    def alive(self) -> Optional[dict]:
        try:
            hdr, _ = self.client.call({"op": "ping"})
        except (OSError, ValueError):
            return None
        return hdr if hdr.get("ok") else None
