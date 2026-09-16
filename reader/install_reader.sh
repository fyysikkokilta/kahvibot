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
# Rollback:  sudo systemctl disable --now kahvi-reader
#            sudo systemctl enable --now kahvisampler     # if the old unit is still installed
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"          # .../kahvibot/reader
BOT="$(cd "$HERE/.." && pwd)"                  # .../kahvibot
DATA="${DATA:-/home/konsta/coffee-data}"       # readings and latest.json
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

sudo systemctl daemon-reload
if systemctl is-enabled kahvisampler >/dev/null 2>&1; then
    sudo systemctl disable --now kahvisampler        # the service replaces it
fi
sudo systemctl enable --now kahvi-reader

sleep 5
sudo systemctl status kahvi-reader --no-pager -n 12 || true

echo
echo "=== next ==="
echo "  journalctl -u kahvi-reader -f                 # one line per state change"
echo "  tail -f $DATA/readings-\$(date +%Y-%m).jsonl   # slim records: a, t_c, fm/flo/fhi"
echo "  ls -l /run/kahvi-sampler/ipc.sock             # the bot's socket"
echo "  bot config.py: reader_service_socket = \"/run/kahvi-sampler/ipc.sock\""
echo "                 coffee_reader_log    = \"$DATA/readings-%Y-%m.jsonl\""
echo "  then: sudo systemctl restart kahvibot"
