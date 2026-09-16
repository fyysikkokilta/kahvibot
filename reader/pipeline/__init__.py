"""Streamlined kahvibot reading pipeline: one warm reader, one writer, one clock.

The sampler daemon becomes the only process that touches the camera and the
model. The bot asks it for the latest frame (or a fresh one) over a local
socket and falls back to its old fswebcam path if the daemon is unreachable.
Every record carries the calibrated millilitres and the surface entropy; the
ok/uncertain/abstain decision is made by the consumer via `gate.Gate`, so it is
a config value rather than a model redeploy.

Modules:
  clock     RealClock / VirtualClock (the latter for tests)
  camera    Frame, FswebcamCamera (the Pi's fswebcam under a flock)
  reader    WarmReader: model loaded once, cached boxes, per-call TTA
  gate      entropy tiers
  store     single-writer JSONL with monthly rotation + latest.json sidecar
  graphing  day buffer + graph cache keyed on the last usable reading
  service   ReaderService: sampling loop + request handling
  ipc       socket server/client (AF_UNIX on the Pi, loopback TCP elsewhere)
  botclient reference client for the socket; handy for debugging by hand
"""
