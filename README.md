# omatsufe

Telegram bot that monitors coffee-machine power usage via MQTT and reports plots and last-brew info.

## Components

- **`mqtt_logger.py`** — subscribes to MQTT topics (`zigbee2mqtt/<device>`) and appends `timestamp,power` rows to `data/power_<device>.csv`.
- **`plot.py`** — reads the CSVs, plots power over time (log scale, last 24 h), and detects "brews" as power events above a threshold.
- **`bot.py`** — Telegram bot with `/plot`, `/brew`, `/help` commands plus keyword aliases (`kahvi`, `tsufe`, `brew`, `plot`, ...).
- **`aliases.py`** — keyword patterns that trigger bot actions.

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
| `BREW_THRESHOLD` | `300` | W above which a brew starts |
| `HEAT` | `100` | W below which a brew ends (hysteresis) |
| `PLOT_HOURS` | `24` | Hours of history shown in plots |

## Bot commands

- `/plot [device]` — power plot for a device
- `/brew [device]` — last brew time/duration/peak
- `/help` — available commands