#!/bin/bash
# Install or upgrade the coffee reader service. Idempotent.
#
#   bash reader/install_reader.sh        # on the Pi, from a checkout of this repo
#
# The reader runs from the checkout itself: code and the model bundle stay under
# version control and only data lives outside, so `git status` on the Pi means
# something. It builds its own virtualenv beside the code, because the reader
# needs onnxruntime and paho while the bot needs neither.
#
# The service is also the plug power logger and the only writer of the SQLite
# store, $DATA/kahvi.db. A first install imports whatever the older layout left
# behind (readings JSONL, the power logger's CSVs and brews), once.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"          # .../kahvibot/reader
BOT="$(cd "$HERE/.." && pwd)"                  # .../kahvibot
DATA="${DATA:-/home/konsta/coffee-data}"       # kahvi.db, survey/, frames/
RUN_USER="${RUN_USER:-$(id -un)}"
MQTT_USER="${MQTT_USER:-zigbee2mqtt}"
MQTT_PW_FILE="${MQTT_PW_FILE:-$HOME/mqtt.pw}"

# 1. A virtualenv beside the code. ONNX Runtime rather than torch: measured on
#    identical inputs it is 4.8x smaller resident and 2.1x faster, which is what
#    makes the model fit on this Pi at all.
if [ ! -x "$HERE/venv/bin/python" ]; then
    python3 -m venv "$HERE/venv"
    "$HERE/venv/bin/pip" install -q --upgrade pip
    "$HERE/venv/bin/pip" install -q onnxruntime numpy pillow "paho-mqtt>=2"
fi
(cd "$HERE" && venv/bin/python -c "import read_frame, pipeline.service, pipeline.ipc; print('reader imports OK')")

mkdir -p "$DATA"

# 2. Shared camera lock, pre-created so the root-run bot and the unprivileged
#    reader can both flock it whichever starts first.
echo 'f /run/lock/kahvicam.lock 0666 root root -' | sudo tee /etc/tmpfiles.d/kahvicam.conf >/dev/null
sudo systemd-tmpfiles --create /etc/tmpfiles.d/kahvicam.conf

# 3. The broker password, readable by the service user only. It is passed as a
#    file rather than on the command line, which is world-readable in ps and
#    sits in a unit anyone can cat.
if [ ! -f "$MQTT_PW_FILE" ] && [ -f /etc/mosquitto/zigbee2mqtt.pw ]; then
    sudo cp /etc/mosquitto/zigbee2mqtt.pw "$MQTT_PW_FILE"
    sudo chown "$RUN_USER:$RUN_USER" "$MQTT_PW_FILE"
    chmod 600 "$MQTT_PW_FILE"
fi

# 4. The unit, with this checkout's paths filled in.
sed -e "s|/home/marci/dev/kiltiskahvi/reader|$HERE|g" \
    -e "s|/home/marci/dev/kiltiskahvi/graphs.py|$BOT/graphs.py|g" \
    -e "s|/home/konsta/coffee-data|$DATA|g" \
    -e "s|/home/konsta/mqtt.pw|$MQTT_PW_FILE|g" \
    -e "s|^User=.*|User=$RUN_USER|" \
    -e "s|^Group=.*|Group=$RUN_USER|" \
    "$HERE/pipeline/kahvi-reader.service" | sudo tee /etc/systemd/system/kahvi-reader.service >/dev/null

# 5. One writer: the separate power logger is retired before the store opens.
for old in kahvi-power kahvisampler; do
    if [ -f "/etc/systemd/system/$old.service" ]; then
        sudo systemctl disable --now "$old" 2>/dev/null || true
        sudo rm -f "/etc/systemd/system/$old.service"
    fi
done
sudo systemctl daemon-reload

# 6. First install of the store: import the older files, with the reader stopped.
DB="$DATA/kahvi.db"
OLD_POWER="${OLD_POWER:-$HOME/power/data}"
if [ ! -f "$DB" ]; then
    sudo systemctl stop kahvi-reader 2>/dev/null || true
    KDB=(env -C "$HERE" venv/bin/python -m pipeline.kahvidb)
    shopt -s nullglob
    jsonl=("$DATA"/readings-*.jsonl)
    [ ${#jsonl[@]} -gt 0 ] && "${KDB[@]}" import-readings "$DB" "${jsonl[@]}"
    for dev in vasen oikea; do
        [ -f "$OLD_POWER/power_$dev.csv" ] && "${KDB[@]}" import-power "$DB" "$dev" "$OLD_POWER/power_$dev.csv"
        [ -f "$OLD_POWER/brews_$dev.jsonl" ] && "${KDB[@]}" import-brews "$DB" "$dev" "$OLD_POWER/brews_$dev.jsonl"
    done
    "${KDB[@]}" stats "$DB"
fi
sudo systemctl enable --now kahvi-reader
sudo systemctl restart kahvi-reader

sleep 5
sudo systemctl status kahvi-reader --no-pager -n 12 || true

echo
echo "=== next ==="
echo "  journalctl -u kahvi-reader -f                 # one line per state change"
echo "  (cd $HERE && venv/bin/python -m pipeline.kahvidb stats $DATA/kahvi.db)"
echo "  ls -l /run/kahvi-sampler/ipc.sock             # the bot's socket"
echo "  bot config.py: reader_service_socket = \"/run/kahvi-sampler/ipc.sock\""
echo "                 coffee_db            = \"$DATA/kahvi.db\""
echo "  then: sudo systemctl restart kahvibot"
