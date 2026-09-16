#!/bin/bash
# Ship the systemd watchdog to the Pi. Run from the guild LAN.
#
#   bash 20_deploy_watchdog.sh
#
# Patches the INSTALLED unit in place (Type=simple -> notify + WatchdogSec)
# rather than overwriting it, because the live unit carries hand-edits that
# differ from the repo template. Idempotent; everything touched is backed up.
set -uo pipefail

PI="${PI:-konsta@192.168.50.169}"
KEY="${KEY:-$HOME/.ssh/id_ed25519}"
SRC="${SRC:-$(cd "$(dirname "$0")/../pipeline" && pwd)}"
LIVE="${LIVE:-/home/marci/dev/kiltiskahvi/reader/pipeline}"
STAMP="$(date +%Y-%m-%dT%H%M)"
SSH=(ssh -i "$KEY" -o ConnectTimeout=8 -o BatchMode=yes "$PI")

echo "==> $SRC  ->  $PI:$LIVE   stamp=$STAMP"
"${SSH[@]}" true 2>/dev/null || { echo "UNREACHABLE - must be on the guild LAN."; exit 1; }

# The live ExecStart must actually point at $LIVE, or we would ship into a tree
# nothing runs from. The 09-15 hand-deploy already got this wrong once.
"${SSH[@]}" "systemctl show kahvi-reader -p ExecStart --value" | grep -q "$LIVE/run_daemon.py" || {
    echo "REFUSING: the running unit's ExecStart does not reference $LIVE"
    "${SSH[@]}" "systemctl show kahvi-reader -p ExecStart --value"
    echo "Set LIVE=<the reader/pipeline dir in that ExecStart> and re-run."
    exit 1
}

echo "==> backup + ship"
tar -C "$SRC" -czf - notify.py service.py ipc.py run_daemon.py test_watchdog.py \
  | "${SSH[@]}" "set -eu
     B=/home/konsta/deploy-backup-$STAMP; mkdir -p \$B
     sudo cp -a /etc/systemd/system/kahvi-reader.service \$B/
     for f in notify.py service.py ipc.py run_daemon.py test_watchdog.py; do
         [ -f $LIVE/\$f ] && sudo cp -a $LIVE/\$f \$B/ || true
     done
     sudo tar -C $LIVE -xzf -
     sudo chown -R konsta:konsta $LIVE
     echo \"backup -> \$B\"; ls -1 \$B"

echo "==> patch the installed unit (idempotent)"
"${SSH[@]}" 'bash -s' <<'REMOTE'
set -u
U=/etc/systemd/system/kahvi-reader.service
if grep -q '^Type=notify' "$U"; then
    echo "  already Type=notify"
else
    sudo python3 - "$U" <<'PY'
import sys
p = sys.argv[1]
s = open(p, encoding="utf-8").read()
block = ("# notify, not simple: the daemon pings WATCHDOG=1 only while its loop is still\n"
         "# completing ticks, so a spin that leaves the process alive but useless\n"
         "# (2026-09-15, 21 h) becomes a restart in ~2 min. Restart=always cannot catch\n"
         "# that case, because the process never exits.\n"
         "Type=notify\nNotifyAccess=main\nWatchdogSec=120\n")
assert s.count("Type=simple\n") == 1, "unexpected unit contents, not patching"
open(p, "w", encoding="utf-8").write(s.replace("Type=simple\n", block, 1))
print("  patched")
PY
fi
grep -nE '^(Type|NotifyAccess|WatchdogSec|Restart|RestartSec)=' "$U"
sudo systemctl daemon-reload
REMOTE

echo "==> restart + verify"
"${SSH[@]}" 'bash -s' <<'REMOTE'
set -u
ok=1
sudo systemctl restart kahvi-reader || ok=0

echo "-- a. is the watchdog actually armed?"
systemctl show kahvi-reader -p Type -p WatchdogUSec -p NRestarts -p MainPID
# systemd renders this as "120s", "2min" or raw microseconds depending on version
wd=$(systemctl show kahvi-reader -p WatchdogUSec --value)
case "$wd" in
    120s|2min|120000000) echo "   OK: deadline $wd" ;;
    ""|0|infinity)       echo "   FAIL: watchdog not armed (WatchdogUSec=$wd)"; ok=0 ;;
    *)                   echo "   WARN: unexpected WatchdogUSec=$wd (armed, but verify)" ;;
esac

echo "-- b. did the daemon send READY=1 and announce the watchdog?"
for i in $(seq 1 12); do
    sudo journalctl -u kahvi-reader --since "-3 min" --no-pager 2>/dev/null \
      | grep -q "systemd watchdog on" && break
    sleep 5
    [ "$i" = 12 ] && { echo "   FAIL: no 'systemd watchdog on' line in 60 s"; ok=0; }
done
sudo journalctl -u kahvi-reader --since "-3 min" --no-pager | tail -6

echo "-- c. the bot's own path still works"
timeout 25 python3 - <<'PY' || ok=0
import socket, json, time, sys
t0=time.time()
s=socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(15)
s.connect("/run/kahvi-sampler/ipc.sock")
s.sendall(json.dumps({"op":"frame","max_age":15.0}).encode()+b"\n")
buf=b""
while b"\n" not in buf:
    c=s.recv(65536)
    if not c: break
    buf+=c
h=json.loads(buf.split(b"\n")[0].decode())
print("   frame %.2fs ok=%s bytes=%s" % (time.time()-t0, h.get("ok"), h.get("bytes")))
sys.exit(0 if h.get("ok") else 1)
PY

echo "-- d. readings still landing"
f=/home/konsta/coffee-data/readings-2026-09.jsonl
a=$(wc -l < "$f"); sleep 60; b=$(wc -l < "$f")
echo "   $a -> $b (+$((b-a)) in 60 s)"
[ "$b" -gt "$a" ] || { echo "   FAIL: no new readings"; ok=0; }

echo "-- e. no watchdog kill loop (NRestarts should stay put)"
sleep 20; systemctl show kahvi-reader -p NRestarts --value | xargs -I{} echo "   NRestarts={}"
systemctl is-active kahvi-reader

[ "$ok" = 1 ] && echo "VERIFY: PASS" || echo "VERIFY: FAIL"
REMOTE

echo
echo "==> rollback if needed:"
echo "    ssh $PI 'sudo cp -a /home/konsta/deploy-backup-$STAMP/kahvi-reader.service /etc/systemd/system/ && \\"
echo "       sudo cp -a /home/konsta/deploy-backup-$STAMP/*.py $LIVE/ && \\"
echo "       sudo systemctl daemon-reload && sudo systemctl restart kahvi-reader'"
