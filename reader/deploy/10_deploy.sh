#!/bin/bash
# Go-live. Run 00_diagnose.sh FIRST - it tells you which MODE you want.
#
#   MODE=repair   bash 10_deploy.sh     # default: repair the reader already on the Pi
#   MODE=pipeline bash 10_deploy.sh     # ship the reader-pipeline branch + install_reader.sh
#
# Everything it overwrites is backed up to /home/konsta/deploy-backup-<stamp>/ on
# the Pi and echoed at the end. Nothing is deleted. Rollback: 90_rollback.sh.
set -uo pipefail

PI="${PI:-konsta@192.168.50.169}"
KEY="${KEY:-$HOME/.ssh/id_ed25519}"
MODE="${MODE:-repair}"
CHECKOUT="${CHECKOUT:-$(cd "$(dirname "$0")/../.." && pwd)}"
STAMP="$(date +%Y-%m-%dT%H%M)"
SSH=(ssh -i "$KEY" -o ConnectTimeout=8 -o BatchMode=yes "$PI")

echo "==> mode=$MODE  pi=$PI  stamp=$STAMP"
"${SSH[@]}" true 2>/dev/null || { echo "UNREACHABLE - must be on the guild LAN."; exit 1; }

# ---------------------------------------------------------------- backup
"${SSH[@]}" "bash -s" <<REMOTE || { echo "backup failed, stopping"; exit 1; }
set -eu
B=/home/konsta/deploy-backup-$STAMP
mkdir -p "\$B"
for f in /etc/systemd/system/kahvi-reader.service \
         /etc/systemd/system/kahvisampler.service \
         /etc/tmpfiles.d/kahvicam.conf \
         /home/marci/dev/kiltiskahvi/config.py; do
    [ -f "\$f" ] && sudo cp -a "\$f" "\$B/\$(echo "\$f" | tr / _)" || true
done
sudo systemctl show kahvi-reader -p FragmentPath -p ExecStart > "\$B/unit-state.txt" 2>&1 || true
echo "backup -> \$B"; ls -1 "\$B"
REMOTE

case "$MODE" in
# ---------------------------------------------------------------- repair
repair)
"${SSH[@]}" "bash -s" <<'REMOTE'
set -u
echo "== 1. shared camera lock (install_reader.sh step 2, skipped by the 09-15 hand-deploy)"
# The bot runs as root, the reader as konsta; both flock this file. Whoever
# creates it first decides the mode, so pre-create it 0666 declaratively.
echo 'f /run/lock/kahvicam.lock 0666 root root -' | sudo tee /etc/tmpfiles.d/kahvicam.conf >/dev/null
sudo systemd-tmpfiles --create /etc/tmpfiles.d/kahvicam.conf
ls -l /run/lock/kahvicam.lock

echo "== 2. restart the wedged reader"
sudo systemctl daemon-reload
sudo systemctl restart kahvi-reader
sudo systemctl is-enabled kahvi-reader >/dev/null 2>&1 || sudo systemctl enable kahvi-reader
REMOTE
;;
# ---------------------------------------------------------------- pipeline
pipeline)
echo "==> shipping $CHECKOUT (branch: $(git -C "$CHECKOUT" rev-parse --abbrev-ref HEAD 2>/dev/null))"
# reader-pipeline is not on any remote, so the Pi cannot git pull it: stream a tar.
tar -C "$CHECKOUT" -czf - \
    --exclude='.git' --exclude='__pycache__' --exclude='reader/venv' \
    --exclude='reader/gym' --exclude='supabase' . \
  | "${SSH[@]}" "set -eu
     rm -rf /home/konsta/kahvibot-deploy.new
     mkdir -p /home/konsta/kahvibot-deploy.new
     tar -C /home/konsta/kahvibot-deploy.new -xzf -
     [ -d /home/konsta/kahvibot-deploy ] && mv /home/konsta/kahvibot-deploy /home/konsta/kahvibot-deploy.prev-$STAMP
     mv /home/konsta/kahvibot-deploy.new /home/konsta/kahvibot-deploy
     echo 'shipped:'; du -sh /home/konsta/kahvibot-deploy" \
  || { echo "ship failed, nothing started"; exit 1; }

"${SSH[@]}" "bash -s" <<'REMOTE'
set -u
echo "== install_reader.sh (idempotent: venv, tmpfiles lock, mqtt pw, unit with real paths)"
cd /home/konsta/kahvibot-deploy
bash reader/install_reader.sh
REMOTE
echo
echo "!! config.py still needs the data dir pointed at the new log location:"
echo "     coffee_reader_log = \"/home/konsta/coffee-data/readings-%Y-%m.jsonl\""
echo "   then: sudo systemctl restart kahvibot     (see RUNBOOK.md 5)"
;;
*) echo "unknown MODE=$MODE (repair|pipeline)"; exit 2;;
esac

# ---------------------------------------------------------------- verify
echo
echo "==> verifying (up to ~90 s)"
"${SSH[@]}" "bash -s" <<'REMOTE'
set -u
ok=1

echo "-- a. did it come up?"
for i in $(seq 1 12); do
    if sudo journalctl -u kahvi-reader --since "-3 min" --no-pager 2>/dev/null | grep -q "reader service up"; then
        sudo journalctl -u kahvi-reader --since "-3 min" --no-pager | grep "reader service up" | tail -2
        break
    fi
    sleep 5
    [ "$i" = 12 ] && { echo "FAIL: no 'reader service up' in 60 s"; ok=0; }
done

echo "-- b. does the socket ANSWER (the thing that was broken)?"
timeout 25 python3 - <<'PY' 2>&1 || echo "probe exited non-zero"
import socket, json, time, sys
def call(payload, tmo=15.0):
    t0 = time.time()
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(tmo)
    s.connect("/run/kahvi-sampler/ipc.sock")
    s.sendall(json.dumps(payload).encode() + b"
")
    buf = b""
    while b"
" not in buf:
        c = s.recv(65536)
        if not c: break
        buf += c
    return json.loads(buf.split(b"
")[0].decode()), time.time() - t0
try:
    # "frame" is what the bot calls and can be served by the fast path; "ping"
    # only completes on the loop thread, so the two together localise a stall.
    hf, dtf = call({"op": "frame", "max_age": 15.0})
    print("   frame %.2fs ok=%s reused=%s bytes=%s" % (dtf, hf.get("ok"), hf.get("reused"), hf.get("bytes")))
    hp, dtp = call({"op": "ping"})
    print("   ping  %.2fs -> %s" % (dtp, hp))
    if not hf.get("ok"):
        print("   FAIL: frame not ok - the bot's own path is broken"); sys.exit(1)
    if not hp.get("ok"):
        print("   WARN: ping timed out while frame worked -> loop thread is not")
        print("         executing queued requests (fast path is masking it)")
    sys.exit(0)
except Exception as e:
    print("   FAIL %s: %s" % (type(e).__name__, e)); sys.exit(1)
PY

echo "-- c. are readings landing again? (interval 10 s)"
for d in /home/konsta/coffee-data /home/konsta/coffee-reader; do
    f="$d/readings-$(date +%Y-%m).jsonl"; [ -f "$f" ] || continue
    a=$(wc -l < "$f"); sleep 45; b=$(wc -l < "$f")
    echo "   $f: $a -> $b lines"
    [ "$b" -gt "$a" ] && echo "   OK: growing" || echo "   (no new lines in 45 s - check camera/lock)"
done

echo "-- d. is the bot still falling back?"
sudo journalctl -u kahvibot --since "-2 min" --no-pager 2>/dev/null | grep -c "reader service unavailable" \
  | xargs -I{} echo "   fallbacks in last 2 min: {}   (want 0)"

echo "-- e. service + power"
systemctl is-active kahvi-reader; systemctl is-enabled kahvi-reader
vcgencmd get_throttled 2>/dev/null
[ "$ok" = 1 ] && echo "VERIFY: PASS" || echo "VERIFY: FAIL - see 90_rollback.sh"
REMOTE

echo
echo "==> done. backup on the Pi: /home/konsta/deploy-backup-$STAMP/"
echo "    rollback:  STAMP=$STAMP bash 90_rollback.sh"
