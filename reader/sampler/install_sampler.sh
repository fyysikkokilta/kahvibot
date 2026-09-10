#!/bin/bash
# Install the coffee background sampler on kahviraspi. Idempotent.
#
# Run on the Pi as konsta:  bash install_sampler.sh
# Expects sampler.py and kahvisampler.service beside this script, and the
# reader deployment (read_frame.py, *.onnx, venv/) at $TARGET.
set -euo pipefail

TARGET="${TARGET:-/home/konsta/coffee-reader}"
HERE="$(cd "$(dirname "$0")" && pwd)"

[ -f "$TARGET/read_frame.py" ] || { echo "no reader deployment at $TARGET"; exit 1; }
[ -x "$TARGET/venv/bin/python" ] || { echo "no venv at $TARGET/venv (run install.sh first)"; exit 1; }

# 1. The daemon, beside read_frame.py (it imports from it).
if [ "$HERE" != "$TARGET" ]; then
    cp "$HERE/sampler.py" "$TARGET/sampler.py"
fi

# Sanity: the venv can import it (also catches a broken onnx bundle early).
(cd "$TARGET" && venv/bin/python -c "import sampler; print('sampler.py imports OK')")

# 2. Shared camera lock file, pre-created so the root-run bot and the
#    unprivileged sampler can both flock it regardless of start order.
echo 'f /run/lock/kahvicam.lock 0666 root root -' | sudo tee /etc/tmpfiles.d/kahvicam.conf >/dev/null
sudo systemd-tmpfiles --create /etc/tmpfiles.d/kahvicam.conf

# 3. Kill-switch directory (touch /etc/kahvi-sampler/disabled to stop).
sudo mkdir -p /etc/kahvi-sampler

# 3b. The readings JSONL is shared with the root-run bot: whichever process
#     writes first each month creates the file, and a root-created 0644 file
#     locks the unprivileged sampler out (found the hard way on first deploy).
#     A default ACL on the directory makes every future log file writable by
#     both, regardless of creator.
command -v setfacl >/dev/null || sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq acl >/dev/null
sudo setfacl -d -m "u:$(id -un):rw" -m u:root:rw "$TARGET"
for f in "$TARGET"/readings-*.jsonl; do
    [ -e "$f" ] && sudo setfacl -m "u:$(id -un):rw" "$f"
done

# 4. The unit.
sudo cp "$HERE/kahvisampler.service" /etc/systemd/system/kahvisampler.service
sudo systemctl daemon-reload
sudo systemctl enable --now kahvisampler

sleep 3
sudo systemctl status kahvisampler --no-pager -n 10 || true

echo
echo "=== burn-in acceptance gates (SAMPLER.md §9) ==="
echo "  journalctl -u kahvisampler -f                    # one line per state change only"
echo "  tail -f $TARGET/readings-\$(date +%Y-%m).jsonl    # slim records, ~1.4 MB/day"
echo "  vcgencmd get_throttled                           # must stay clear of throttle bits"
echo "  ls /var/lib/kahvi-sampler/retained | wc -l       # stratified retention, ~40/day"
echo "  touch /etc/kahvi-sampler/disabled                # kill switch (rm to re-enable)"
