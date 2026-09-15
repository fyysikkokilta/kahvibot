"""Local IPC between kahvibot and the ReaderService.

Protocol: one JSON request line; response is one JSON header line followed by
`header["bytes"]` raw bytes (the JPEG or PNG). AF_UNIX on the Pi, loopback TCP
where AF_UNIX is missing (Windows dev box). Requests:
  {"op": "frame", "max_age": 15}   -> header {ok, age, reused, seq, pots, bytes}
  {"op": "graph"}                  -> header {ok, caption, bytes}
  {"op": "ping"}                   -> header {ok, seq, last_lit_age}
The server thread only enqueues; the service loop executes requests between
ticks so the model is never used from two threads.
"""
from __future__ import annotations

import json
import queue
import socket
import threading
from dataclasses import dataclass, field
from typing import Optional

HAS_UNIX = hasattr(socket, "AF_UNIX")


def _bind(addr):
    if HAS_UNIX and not isinstance(addr, tuple):
        import os
        try:
            os.unlink(addr)
        except OSError:
            pass
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.bind(addr)
        return s
    host, port = addr if isinstance(addr, tuple) else ("127.0.0.1", int(addr))
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, port))
    return s


def _connect(addr, timeout):
    if HAS_UNIX and not isinstance(addr, tuple):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    else:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        addr = addr if isinstance(addr, tuple) else ("127.0.0.1", int(addr))
    s.settimeout(timeout)
    s.connect(addr)
    return s


def _readline(sock) -> tuple[bytes, bytes]:
    """Read up to the first newline. Returns (line, bytes already read past it):
    header and body are sent in one write, so the first recv usually carries
    the start of the body too."""
    buf = b""
    while b"\n" not in buf:
        chunk = sock.recv(1 << 16)
        if not chunk:
            break
        buf += chunk
        if len(buf) > 1 << 20:
            break
    line, _, rest = buf.partition(b"\n")
    return line, rest


def _readn(sock, n: int, prefix: bytes = b"") -> bytes:
    out = bytearray(prefix[:n])
    while len(out) < n:
        chunk = sock.recv(min(1 << 16, n - len(out)))
        if not chunk:
            break
        out += chunk
    return bytes(out)


@dataclass
class Request:
    payload: dict
    done: threading.Event = field(default_factory=threading.Event)
    header: dict = field(default_factory=dict)
    body: bytes = b""


class IPCServer(threading.Thread):
    """Accepts connections and hands Requests to the service loop via a queue."""

    def __init__(self, addr, inbox: "queue.Queue[Request]", timeout: float = 5.0,
                 service=None):
        super().__init__(daemon=True, name="kahvi-ipc")
        self.sock = _bind(addr)
        self.sock.listen(8)
        self.inbox = inbox
        self.timeout = timeout
        self.service = service
        self.stop = threading.Event()

    def run(self):
        self.sock.settimeout(0.5)
        while not self.stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn):
        conn.settimeout(self.timeout)
        try:
            line, _ = _readline(conn)
            try:
                payload = json.loads(line.decode("utf-8"))
            except ValueError:
                payload = {"op": "bad"}
            fast = self._fast_frame(payload)
            if fast is not None:
                hdr, body = fast
                hdr["bytes"] = len(body)
                conn.sendall(json.dumps(hdr).encode("utf-8") + b"\n" + body)
                return
            req = Request(payload)
            self.inbox.put(req)
            if not req.done.wait(self.timeout):
                req.header = {"ok": False, "error": "timeout"}
                req.body = b""
            hdr = dict(req.header)
            hdr["bytes"] = len(req.body)
            conn.sendall(json.dumps(hdr).encode("utf-8") + b"\n" + req.body)
        except OSError:
            pass
        finally:
            conn.close()


    def _fast_frame(self, payload):
        """Serve a frame young enough to reuse, without waiting for the loop.

        Only the reuse case qualifies: it reads an already-captured frame and the
        reading computed with it, touching neither camera nor model, so nothing
        here can race the service's own tick. Anything needing a new capture goes
        through the queue as before. Returns (header, body) or None.
        """
        svc = self.service
        if svc is None:
            return None
        if payload.get("op") == "graph":
            # A warm cache is just bytes; serving it here keeps /graph off the
            # queue, where it would wait for a tick and then for a render.
            cache = getattr(svc, "graphcache", None)
            png = getattr(cache, "png", None) if cache is not None else None
            if png:
                cache.hits += 1
                return {"ok": True, "caption": cache.caption, "fast": True}, png
            return None
        if payload.get("op") != "frame":
            return None
        try:
            lit = svc.last_lit                      # one atomic attribute read
            if lit is None:
                return None
            max_age = payload.get("max_age")
            max_age = svc.cfg.reuse_max_age if max_age is None else float(max_age)
            age = svc.clock.mono() - lit.frame.captured_mono
            if age > max_age:
                return None
            svc.stats.requests += 1
            svc.stats.requests_reused += 1
            svc.stats.request_photo_latency.append(0.0)
            svc.stats.request_reading_latency.append(0.0)
            return ({"ok": True, "age": round(age, 2), "reused": True, "seq": lit.seq,
                     "pots": lit.pots, "captured_at": lit.frame.captured_wall,
                     "fast": True},
                    lit.frame.jpeg)
        except Exception:  # noqa: BLE001 - fall back to the queue, never fail here
            return None


def execute(service, req: Request) -> None:
    """Run one request on the service (loop thread) and release the waiter."""
    op = req.payload.get("op")
    try:
        if op == "frame":
            res = service.frame(req.payload.get("max_age"))
            if res is None:
                req.header = {"ok": False, "error": "capture failed"}
            else:
                req.header = {"ok": True, "age": round(res.age_s, 2), "reused": res.reused,
                              "seq": res.seq, "pots": res.pots,
                              "captured_at": res.frame.captured_wall}
                req.body = res.frame.jpeg
        elif op == "graph":
            png, caption = service.graph()
            req.header = {"ok": True, "caption": caption}
            req.body = png or b""
        elif op == "ping":
            age = None
            if service.last_lit is not None:
                age = service.clock.mono() - service.last_lit.frame.captured_mono
            req.header = {"ok": True, "seq": service.seq, "last_lit_age": age}
        else:
            req.header = {"ok": False, "error": "unknown op"}
    except Exception as exc:  # noqa: BLE001 - never let a request kill the loop
        req.header = {"ok": False, "error": repr(exc)}
    finally:
        req.done.set()


class Client:
    def __init__(self, addr, timeout: float = 3.0):
        self.addr, self.timeout = addr, timeout

    def call(self, payload: dict):
        s = _connect(self.addr, self.timeout)
        try:
            s.sendall(json.dumps(payload).encode("utf-8") + b"\n")
            line, rest = _readline(s)
            hdr = json.loads(line.decode("utf-8"))
            body = _readn(s, int(hdr.get("bytes", 0)), rest)
            return hdr, body
        finally:
            s.close()


def serve_forever(service, addr, poll_s: float = 0.25):
    """Daemon main loop: requests first, then due ticks, then a short sleep."""
    inbox: "queue.Queue[Request]" = queue.Queue()
    server = IPCServer(addr, inbox, service=service)
    server.start()
    try:
        while True:
            try:
                req = inbox.get(timeout=min(poll_s, service.seconds_to_next_tick() or poll_s))
                execute(service, req)
                continue
            except queue.Empty:
                pass
            service.run_due()
    finally:
        server.stop.set()
        service.store.flush(force=True)
