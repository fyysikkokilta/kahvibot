#!/bin/bash
# Install the Telegram escalation for a kahvi-reader lock the watchdog cannot
# clear. Run from the guild LAN. Idempotent; backs up what it replaces.
#
#   bash 30_deploy_alert.sh
#
# Independent of the watchdog: this works whether or not 20_deploy_watchdog.sh
# has run, and catches the cases the watchdog is structurally unable to fix.
set -uo pipefail

PI="${PI:-konsta@192.168.50.169}"
KEY="${KEY:-$HOME/.ssh/id_ed25519}"
SRC="${SRC:-$(cd "$(dirname "$0")/alert" && pwd)}"
STAMP="$(date +%Y-%m-%dT%H%M)"
SSH=(ssh -i "$KEY" -o ConnectTimeout=8 -o BatchMode=yes "$PI")

echo "==> $SRC -> $PI   stamp=$STAMP"
"${SSH[@]}" true 2>/dev/null || { echo "UNREACHABLE - must be on the guild LAN."; exit 1; }

# The conf must name a config.py that actually holds a bot_token, or every
# alert would be silently unsendable at exactly the wrong moment.
[ -f "$SRC/kahvi-alert.conf" ] || {
    echo "Missing $SRC/kahvi-alert.conf (it is untracked: it holds a personal chat id)."
    echo "  cp $SRC/kahvi-alert.conf.example $SRC/kahvi-alert.conf   # then set CHAT_ID"
    exit 1; }
grep -qE '^CHAT_ID=[0-9]+' "$SRC/kahvi-alert.conf" || {
    echo "Set a numeric CHAT_ID in $SRC/kahvi-alert.conf first."; exit 1; }
CFG_PY=$(grep -E '^CONFIG_PY=' "$SRC/kahvi-alert.conf" | cut -d= -f2-)
"${SSH[@]}" "sudo grep -qE '^bot_token *=' '$CFG_PY'" || {
    echo "REFUSING: no bot_token assignment in $CFG_PY on the Pi"; exit 1; }
echo "    bot_token present in $CFG_PY (value not read here)"

echo "==> ship"
tar -C "$SRC" -czf - kahvi-alert kahvi-alert.conf kahvi-alert@.service \
                     kahvi-health.service kahvi-health.timer \
  | "${SSH[@]}" "set -eu
     B=/home/konsta/deploy-backup-$STAMP; mkdir -p \$B
     sudo cp -a /etc/systemd/system/kahvi-reader.service \$B/ 2>/dev/null || true
     sudo cp -a /etc/kahvi-alert.conf \$B/ 2>/dev/null || true
     T=\$(mktemp -d); tar -C \$T -xzf -
     sudo install -m 0755 -o root -g root \$T/kahvi-alert          /usr/local/bin/kahvi-alert
     sudo install -m 0600 -o root -g root \$T/kahvi-alert.conf     /etc/kahvi-alert.conf
     sudo install -m 0644 -o root -g root \$T/kahvi-alert@.service /etc/systemd/system/
     sudo install -m 0644 -o root -g root \$T/kahvi-health.service /etc/systemd/system/
     sudo install -m 0644 -o root -g root \$T/kahvi-health.timer   /etc/systemd/system/
     rm -rf \$T
     echo \"    backup -> \$B\""

echo "==> wire OnFailure= into the installed reader unit (idempotent)"
"${SSH[@]}" 'bash -s' <<'REMOTE'
set -u
U=/etc/systemd/system/kahvi-reader.service
if grep -q '^OnFailure=' "$U"; then
    echo "    already wired"
else
    sudo python3 - "$U" <<'PY'
import sys
p = sys.argv[1]
s = open(p, encoding="utf-8").read()
line = ("# Exhausting StartLimitBurst leaves the unit in `failed` and there it stays:\n"
        "# restarting has demonstrably not fixed it, which is the one case worth a\n"
        "# Telegram message rather than another retry.\n"
        "OnFailure=kahvi-alert@%n.service\n")
if "[Unit]\n" not in s:
    raise SystemExit("no [Unit] section, not patching")
s = s.replace("[Unit]\n", "[Unit]\n" + line, 1)
open(p, "w", encoding="utf-8").write(s)
print("    patched")
PY
fi
sudo systemctl daemon-reload
sudo systemctl enable --now kahvi-health.timer
REMOTE

echo "==> verify"
"${SSH[@]}" 'bash -s' <<'REMOTE'
set -u
ok=1

echo "-- a. OnFailure is on the unit"
systemctl show kahvi-reader -p OnFailure --value | grep -q kahvi-alert \
  && echo "    OK: $(systemctl show kahvi-reader -p OnFailure --value)" \
  || { echo "    FAIL: OnFailure not set"; ok=0; }

echo "-- b. the timer is armed"
systemctl is-enabled kahvi-health.timer
systemctl is-active  kahvi-health.timer
systemctl list-timers kahvi-health.timer --no-pager 2>/dev/null | sed -n 2p

echo "-- c. the check runs clean against a healthy reader"
sudo /usr/local/bin/kahvi-alert check && echo "    OK: check exited 0" \
  || { echo "    FAIL: check errored"; ok=0; }

echo "-- d. a real message actually reaches Telegram"
sudo /usr/local/bin/kahvi-alert test || { echo "    FAIL: test message not delivered"; ok=0; }

echo "-- e. the token never landed anywhere it should not"
sudo grep -qE '^bot_token|[0-9]{8,10}:[A-Za-z0-9_-]{30,}' /etc/kahvi-alert.conf \
  && { echo "    FAIL: a token-shaped string is in /etc/kahvi-alert.conf"; ok=0; } \
  || echo "    OK: no token in the conf file"
sudo grep -qE '[0-9]{8,10}:[A-Za-z0-9_-]{30,}' /usr/local/bin/kahvi-alert \
  && { echo "    FAIL: a token-shaped string is in the script"; ok=0; } \
  || echo "    OK: no token in the script"

[ "$ok" = 1 ] && echo "VERIFY: PASS" || echo "VERIFY: FAIL"
REMOTE

echo
echo "==> rollback:"
echo "    ssh $PI 'sudo systemctl disable --now kahvi-health.timer; \\"
echo "       sudo rm -f /usr/local/bin/kahvi-alert /etc/kahvi-alert.conf \\"
echo "         /etc/systemd/system/kahvi-{alert@,health}.service /etc/systemd/system/kahvi-health.timer; \\"
echo "       sudo cp -a /home/konsta/deploy-backup-$STAMP/kahvi-reader.service /etc/systemd/system/; \\"
echo "       sudo systemctl daemon-reload'"
