#!/bin/bash
# READ-ONLY. Changes nothing on the Pi. Run this first, from the laptop, once
# you are back on the guild WiFi. It answers the one thing the 14:11 snapshot
# could not: which kahvi-reader unit is actually installed, and where the
# daemon is wedged.
#
#   bash 00_diagnose.sh            # writes diag_<timestamp>/ next to this script
set -uo pipefail

PI="${PI:-konsta@192.168.50.169}"
KEY="${KEY:-$HOME/.ssh/id_ed25519}"
OUT="diag_$(date +%Y-%m-%dT%H%M)"
SSH=(ssh -i "$KEY" -o ConnectTimeout=8 -o BatchMode=yes "$PI")

mkdir -p "$OUT"
echo "==> $PI  ->  $OUT/"

if ! "${SSH[@]}" true 2>/dev/null; then
    echo "UNREACHABLE. mDNS re-resolve:  ping -4 kahviraspi.local"
    echo "The Pi is on the guild LAN (192.168.50.x) only - this will not work off-site."
    exit 1
fi

"${SSH[@]}" 'bash -s' <<'REMOTE' > "$OUT/diagnose.txt" 2>&1
set -u
hr() { echo; echo "===== $* ====="; }

hr "which unit is installed (THE question)"
systemctl cat kahvi-reader 2>&1 | head -60
echo "--- enabled? ---"; systemctl is-enabled kahvi-reader 2>&1
echo "--- active?  ---"; systemctl is-active  kahvi-reader 2>&1

hr "unit runtime state"
systemctl show kahvi-reader -p MainPID -p ExecMainStartTimestamp -p NRestarts \
                            -p FragmentPath -p MemoryCurrent -p CPUUsageNSec 2>&1
sudo systemctl status kahvi-reader --no-pager -n 25 2>&1

hr "kahvi-reader journal (since the deploy)"
sudo journalctl -u kahvi-reader --since "2026-09-15 16:00" --no-pager 2>&1 | tail -120

hr "where the daemon is stuck"
PID=$(systemctl show kahvi-reader -p MainPID --value 2>/dev/null)
if [ -n "${PID:-}" ] && [ "$PID" != "0" ] && [ -d "/proc/$PID" ]; then
    echo "MainPID=$PID  started $(ps -o lstart= -p "$PID" 2>/dev/null)"
    echo "--- cmdline ---"; tr '\0' ' ' < "/proc/$PID/cmdline"; echo
    echo "--- state/wchan (main) ---"
    grep -E '^(State|Threads|VmRSS)' "/proc/$PID/status" 2>&1
    echo "wchan: $(cat "/proc/$PID/wchan" 2>/dev/null)"
    echo "--- per-thread wchan/state (where it blocks) ---"
    for t in /proc/$PID/task/*; do
        printf '  tid %-7s %-24s %s\n' "$(basename "$t")" \
               "$(cat "$t/wchan" 2>/dev/null)" \
               "$(grep -m1 '^State' "$t/status" 2>/dev/null | cut -f2)"
    done
    echo "--- open fds of interest (camera / lock / socket) ---"
    sudo ls -l "/proc/$PID/fd" 2>/dev/null | grep -Ei 'video|lock|sock' || echo "(none)"
    echo "--- held file locks ---"
    sudo cat /proc/locks 2>/dev/null | grep -w "$PID" || echo "(no locks held by $PID)"
else
    echo "no MainPID - the service is not running"
fi

hr "the socket the bot talks to"
ls -l /run/kahvi-sampler/ 2>&1
ss -xlp 2>/dev/null | grep -i kahvi || echo "(nothing listening on a kahvi socket)"

hr "camera lock (install_reader.sh step 2 creates this 0666)"
ls -l /run/lock/kahvicam.lock 2>&1
ls -l /etc/tmpfiles.d/kahvicam.conf 2>&1
echo "--- who has the camera ---"
sudo fuser -v /dev/video0 2>&1 || echo "(fuser: nothing)"

hr "camera wedge check (D-state = stuck in the USB driver, unkillable)"
ps -eo pid,stat,wchan:24,etime,cmd 2>/dev/null | grep -E 'fswebcam|[[:space:]]D[[:space:]<+lsN]*[[:space:]]' | grep -v grep || echo "(no D-state or fswebcam processes)"
echo "--- uvcvideo / usb errors, last 40 ---"
sudo dmesg -T 2>/dev/null | grep -iE "uvcvideo|usb .*(error|reset|disconnect)|Under-voltage" | tail -40

hr "live socket probe (5 s timeout, read-only ping)"
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

hr "power / thermal (ANALYSIS.md 3: 1006 under-voltage events in 7 days)"
vcgencmd get_throttled 2>&1; vcgencmd measure_volts 2>&1; vcgencmd measure_temp 2>&1
echo "throttled bits: 0x1=under-volt now 0x40000=under-volt since boot"

hr "memory / load"
free -m 2>&1; uptime 2>&1

hr "readings freshness"
for d in /home/konsta/coffee-data /home/konsta/coffee-reader; do
    f="$d/readings-$(date +%Y-%m).jsonl"
    [ -f "$f" ] && { echo "$f: $(wc -l < "$f") lines, mtime $(date -r "$f" '+%F %T')"; tail -1 "$f" | cut -c1-160; }
done

hr "bot: how often it fell back today"
sudo journalctl -u kahvibot --since today --no-pager 2>&1 | grep -c "reader service unavailable"
REMOTE

rc=$?
echo "==> exit $rc; wrote $OUT/diagnose.txt ($(wc -l < "$OUT/diagnose.txt") lines)"
echo
sed -n '1,40p' "$OUT/diagnose.txt"
echo "..."
echo "Full file: $OUT/diagnose.txt"
