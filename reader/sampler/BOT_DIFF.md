# Bot-side change for camera arbitration (SAMPLER.md §2)

The entire bot diff: wrap the existing `fswebcam` call in an advisory `flock`
that the bot always wins. The sampler takes the same lock non-blocking and
skips its tick when the bot has the camera; the bot waits at most 5 s and then
**barges in** — the user's photo is never gated on the lock, so if `flock` is
missing, `/run/lock` is unwritable, or the sampler wedges while holding it,
the bot behaves exactly as today.

All three hunks are against the deployed merged file
(`pi_sd_backup/deploy/kahvibot.reader`, identical in the repo's
`coffee-reader` branch after the deploy commits).

## 1. Config read — add one line beside the other `coffee_reader_*` reads

```python
coffee_reader_log = getattr(_config, "coffee_reader_log", "")
```

after this existing line, add:

```python
# Advisory camera lock shared with the background sampler. Empty string
# (the default) is byte-for-byte today's behaviour: no lock, no sampler.
camera_lock = getattr(_config, "camera_lock", "")
```

## 2. `take_picture()` — the capture line

Before (the single `subprocess.run` line at the end of the comment block):

```python
        w, h = camera_dimensions
        subprocess.run(["fswebcam", "--quiet", "-S", "20", "--no-banner", "--resolution", f"{w}x{h}", f.name], check=True)
```

After:

```python
        w, h = camera_dimensions
        cmd = ["fswebcam", "--quiet", "-S", "20", "--no-banner",
               "--resolution", f"{w}x{h}", f.name]
        if camera_lock:
            # Sampler may be mid-capture: wait briefly for the lock, then
            # take the shot anyway — the user's photo is never gated on it.
            if subprocess.run(["flock", "-w", "5", camera_lock] + cmd).returncode != 0:
                subprocess.run(cmd, check=True)
        else:
            subprocess.run(cmd, check=True)
```

(Identical arguments, same `check=True` fallback semantics; the `flock` branch
cannot raise on a busy lock, only fall through to the barge-in.)

## 3. `config.py` on the Pi — append (install_sampler.sh does NOT do this;
it is a bot-side setting and belongs with the bot's deploy):

```python
camera_lock = "/run/lock/kahvicam.lock"
```

Also add the `camera_lock = ""` default + comment to `config-example.py` in
the repo, mirroring the other reader settings.

## Rollback

Remove `camera_lock` from `config.py` (or set `""`) and restart the bot —
the lock branch is dead code again. `systemctl disable --now kahvisampler`
removes the sampler with zero effect on the bot.
