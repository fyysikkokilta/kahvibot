#!/bin/bash
# Install or upgrade the coffee reader service on kahviraspi. Idempotent.
#
#   bash reader/install_reader.sh        # on the Pi, as konsta, from a checkout of this repo
#
# Copies read_frame.py, pipeline/ and models/ to $TARGET (default
# /home/konsta/coffee-reader, the directory the old sampler already used), creates
# the venv there if it is missing (onnxruntime, numpy, pillow), installs
# kahvi-reader.service and stops kahvisampler.service, which it replaces
# (PIPELINE.md §3). The bot keeps working throughout: it only starts using the
# service once reader_service_socket is set in its config.py.
#
# Rollback:  sudo systemctl disable --now kahvi-reader
#            sudo systemctl enable --now kahvisampler
set -euo pipefail

TARGET="${TARGET:-/home/konsta/coffee-reader}"
HERE="$(cd "$(dirname "$0")" && pwd)"

# 1. Code and model bundle. The service runs $TARGET/pipeline/run_daemon.py with
#    --model-dir $TARGET, so the ONNX files sit beside read_frame.py as before.
mkdir -p "$TARGET/pipeline"
cp "$HERE/read_frame.py" "$TARGET/read_frame.py"
cp "$HERE"/pipeline/*.py "$TARGET/pipeline/"
cp "$HERE"/models/* "$TARGET/"

if [ ! -x "$TARGET/venv/bin/python" ]; then
    python3 -m venv "$TARGET/venv"
    "$TARGET/venv/bin/pip" install -q --upgrade pip
    "$TARGET/venv/bin/pip" install -q onnxruntime numpy pillow
fi
(cd "$TARGET" && venv/bin/python -c "import read_frame, pipeline.service, pipeline.ipc; print('reader imports OK')")

# 2. Shared camera lock, pre-created so the root-run bot and the unprivileged
#    reader can both flock it regardless of start order.
echo 'f /run/lock/kahvicam.lock 0666 root root -' | sudo tee /etc/tmpfiles.d/kahvicam.conf >/dev/null
sudo systemd-tmpfiles --create /etc/tmpfiles.d/kahvicam.conf

# 3. The readings JSONL is shared with the root-run bot (fallback path): a default
#    ACL keeps every future log file writable by both, whoever creates it.
command -v setfacl >/dev/null || sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq acl >/dev/null
sudo setfacl -d -m "u:$(id -un):rw" -m u:root:rw "$TARGET"
for f in "$TARGET"/readings-*.jsonl; do
    [ -e "$f" ] && sudo setfacl -m "u:$(id -un):rw" "$f"
done

# 4. The unit. The old sampler and the service must not share the camera lock
#    loop, so the sampler goes first.
sudo cp "$HERE/pipeline/kahvi-reader.service" /etc/systemd/system/kahvi-reader.service
sudo systemctl daemon-reload
if systemctl is-enabled kahvisampler >/dev/null 2>&1; then
    sudo systemctl disable --now kahvisampler
fi
sudo systemctl enable --now kahvi-reader

sleep 3
sudo systemctl status kahvi-reader --no-pager -n 10 || true

echo
echo "=== next ==="
echo "  journalctl -u kahvi-reader -f                          # one line per state change"
echo "  tail -f $TARGET/readings-\$(date +%Y-%m).jsonl          # slim records with the agreement field a"
echo "  ls -l /run/kahvi-sampler/ipc.sock                      # the bot's socket"
echo "  bot: reader_service_socket = \"/run/kahvi-sampler/ipc.sock\" in config.py, then restart kahvibot"
