# power (omatsufe)

MQTT power logger and Telegram bot for the two IKEA smart plugs on the guild-room
Moccamasters. Merged into the kahvibot repo from `luu3000/omatsufe` with its history;
it still runs standalone from this directory. kahvibot reads the brew event log this
logger writes (`data/brews_<device>.jsonl`) for its "keitetty 12 min sitten / brewed
12 min ago" caption line; see `power_brews_dir` in the repo's `config-example.py`.

## Components

- **`mqtt_logger.py`** — subscribes to MQTT topics (`zigbee2mqtt/<device>`), appends `timestamp,power` rows to `data/power_<device>.csv` (pruned to the newest 150k samples), and detects brews as they happen, appending `start` and `end` events to `data/brews_<device>.jsonl` (never pruned; this is the machine's history and what kahvibot reads).
- **`plot.py`** — reads the CSVs, plots power over time (log scale, last 24 h), and detects "brews" as power events above a threshold.
- **`bot.py`** — Telegram bot with `/plot`, `/brew`, `/help` commands plus keyword aliases (`kahvi`, `tsufe`, `brew`, `plot`, ...).
- **`aliases.py`** — keyword patterns that trigger bot actions.

Device names are validated against the configured `DEVICES` whitelist (bot) and
against known MQTT topics (logger) before being used to build file paths, and
`plot.py`'s `get_csv_path()` rejects any device name containing characters
outside `[A-Za-z0-9_-]` as defense in depth.

## Setup

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Create your config and fill in your secrets:

   ```bash
   cp config-example.py config.py
   ```

   `config.py` is gitignored — never commit it. All values can also be overridden with environment variables (see `config-example.py`).

3. Start the logger (captures power data from MQTT):

   ```bash
   python3 mqtt_logger.py
   ```

4. Start the bot (set `TELEGRAM_TOKEN` in `config.py` or the environment first):

   ```bash
   python3 bot.py
   ```

## Configuration

| Setting | Default | Description |
|---|---|---|
| `TELEGRAM_TOKEN` | (none) | Bot token from @BotFather |
| `MQTT_BROKER` | `localhost` | MQTT broker host |
| `MQTT_PORT` | `1883` | MQTT broker port |
| `MQTT_USER` | `zigbee2mqtt` | MQTT username |
| `MQTT_PASS` | (none) | MQTT password |
| `MQTT_BASE_TOPIC` | `zigbee2mqtt` | MQTT base topic for devices |
| `DEVICES` | `vasen,oikea` | Comma-separated device names |
| `DEFAULT_DEVICE` | `oikea` | Device used by default |
| `BREW_THRESHOLD` | `300` | W above which a brew starts (the heating element draws ~1.4 kW) |
| `HEAT` | `250` | W below which a brew ends. Must sit clearly above the hotplate's own draw (~100 W on a Moccamaster), or the plate cycling around the threshold splits one brew into several and the durations behind the cup estimate become garbage. Was 100. |
| `ALLOWED_CHATS` | (none) | Comma-separated Telegram chat ids the bot answers in; empty = every chat. Set it when the bot shares a group with kahvibot, which reacts to the same keywords |
| `PLOT_HOURS` | `24` | Legacy — plots now always show data from midnight |
| `CUP_CALIBRATION` | (none) | Reference brews for cup-count estimation, as `seconds:cups` pairs (e.g. `400:8,300:6`) |

### Cup-count estimation

Moccamaster-style filter machines draw roughly constant power for as long as
water is still passing through the filter, so brew duration scales with the
amount of water brewed. Once you've measured a couple of reference brews
(known cup count + observed duration from `/brew`), set `CUP_CALIBRATION` and
`/brew` will report an estimated cup count alongside the end time and duration.

- One point (`secs:cups`) assumes brewing starts immediately with no fixed
  warm-up offset, i.e. cups scale linearly from zero.
- Two or more points are fit with a line (`cups = slope * seconds + intercept`),
  which also captures any fixed startup delay before water starts flowing.

Leave unset until you have measurements — no cup estimate is shown without
calibration.

### Teaching brew sizes (recommended)

Instead of editing `CUP_CALIBRATION` by hand, teach real brews with
`calibrate.py`, which stores points in `data/calibration.json` (and beats the
env var at runtime):

```bash
python3 calibrate.py list                    # recent brews per device
python3 calibrate.py add oikea 8             # that pot made 8 cups
python3 calibrate.py add vasen 6 --at 06:47  # a specific brew by end time
python3 calibrate.py show                    # points + fitted mapping
python3 calibrate.py remove 0                # drop a bad point
```

Each `add` records the detected brew's duration (seconds) against the cup
count you tell it. With two or more points the fit captures both scale and any
fixed warm-up offset; one point scales linearly from zero.

### Brew event log

`data/brews_<device>.jsonl` gets one JSON line when a brew starts
(`{"event": "start", "t": ..., "power": ...}`) and one when it ends
(`{"event": "end", "start": ..., "end": ..., "duration_s": ..., "peak_w": ...}`),
timestamps in UTC. The same hysteresis rule as `/brew` uses, applied as samples arrive,
so nothing has to re-scan the CSV, and the file survives CSV pruning.

### zigbee2mqtt reporting

The logger only sees what the plug reports. IKEA plugs report power on change with a
minimum interval; set the `power` reporting for each plug in zigbee2mqtt to a short
minimum interval (a few seconds) and a small reportable change (a few watts), otherwise
brew start is timestamped late and a short brew can be missed entirely.

## Bot commands

- `/plot [device]` — power plot for a device
- `/brew [device]` — last brew end time/duration
- `/help` — available commands

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Tests use a stubbed `config` module (see `tests/conftest.py`) so no real `config.py`
or MQTT/Telegram credentials are needed.