# Deploying and supervising the reader on kahviraspi

`fyysikkokilta/kahvibot` is authoritative, including for what runs on the Pi.
Anything on the Pi that is not in this repository is drift, and drift is what
made 2026-09-15 take 21 hours to understand.

## How the Pi gets its code

`git fetch && git checkout`, then `reader/install_reader.sh`. Resolved on
2026-09-16; before that the Pi sat on a local branch `pi-live-20260829` that
existed nowhere on origin, with `reader/` untracked entirely, so deploys were
tarballs over SSH.

Two things made that stick, both fixed:

* `origin` was `git@github.com:...` and marci's key was never authorised for
  GitHub, so the Pi could not fetch at all. It is now the HTTPS URL. The
  repository is public, the Pi only ever pulls, and nothing needs a key.
* `reader/` was untracked. It is now 49 files under git, and `install_reader.sh`
  writes the unit from the repo's own template, so the watchdog, `OnFailure=`
  and `PYTHONFAULTHANDLER` come with it.

The venv is not in git and is not rebuilt: `install_reader.sh` only creates it
when absent, which matters because pip-installing onnxruntime on a Pi 3B is slow
and not always possible. Preserve `reader/venv` across any future tree surgery.

`config.py` is gitignored and holds the bot token; checkout never touches it.

## Scripts

Run them from the guild LAN (`Fyysikkokilta`, 192.168.50.x); the Pi is not
reachable from outside it. Each backs up what it replaces to
`/home/konsta/deploy-backup-<stamp>/` and prints its own rollback command.

| | |
|---|---|
| `00_diagnose.sh` | Read-only. Which unit is installed, where the daemon is blocked (per-thread `wchan`), the camera lock, a real IPC probe, throttling, readings freshness. Run this first. |
| `10_deploy.sh` | `MODE=repair` restarts a wedged reader; `MODE=pipeline` ships this checkout and runs `install_reader.sh`. |
| `20_deploy_watchdog.sh` | Ships `pipeline/` and patches the installed unit to `Type=notify`. Refuses to run if the live `ExecStart` does not point at the tree it is about to write into. |
| `30_deploy_alert.sh` | Installs the Telegram escalation (below). |
| `90_rollback.sh` | Restores the backed-up units. `FULL=1` stops the reader entirely, leaving the bot on its fswebcam path — degraded but working. |
| `RUNBOOK-2026-09-16.md` | The incident record: what was wrong, what was ruled out, and in what order. |

Every script verifies rather than trusting an exit code: that the watchdog is
armed, that the IPC socket answers `{"op":"frame"}` with `ok=True`, that the
readings file actually grows, and that the bot has stopped falling back.

## Supervision

`kahvi-reader.service` runs `Type=notify` with `WatchdogSec=120`. The daemon
pings only while its loop is still completing ticks (`pipeline/notify.py`), so a
process that is alive but no longer working is killed and restarted in about two
minutes. `Restart=always` cannot do this on its own: the failure mode is a spin,
and a spinning process never exits.

`Environment=PYTHONFAULTHANDLER=1` turns the watchdog's SIGABRT into a full
Python traceback in the journal. That is what identified the 2026-09-15 spin.

## Escalation

`OnFailure=` plus a five-minute timer send a Telegram message when the watchdog
*cannot* fix things:

1. systemd gave up — `StartLimitBurst` exhausted, the unit is `failed`;
2. the kill did not land — a task in uninterruptible sleep never reaches
   `failed`, so only a poll finds it;
3. alive but writing nothing;
4. flapping — repeated restarts that never settle.

Alerts carry unit state, pid state, readings age, `vcgencmd get_throttled` and
the last journal lines, with a 30-minute cooldown per kind and a message when it
recovers.

`alert/kahvi-alert.conf` is **untracked**: it holds a personal Telegram chat id,
which does not belong in a shared repository. Copy the example and fill it in:

```sh
cp alert/kahvi-alert.conf.example alert/kahvi-alert.conf   # then set CHAT_ID
bash 30_deploy_alert.sh
```

The bot token is never copied anywhere — `kahvi-alert` reads it out of the bot's
own `config.py` at runtime, and the installer verifies it landed in neither the
script nor the conf.

## The thing no script fixes

Under-voltage events climbed 51 → 260/day over the week to 2026-09-15, with 327
`uvcvideo` URB failures alongside them. Mains at the plugs is a healthy
225–242 V, so it is the Pi's own supply or cable. It wants a 5 V 3 A brick.
