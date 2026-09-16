#!/bin/bash
# Undo 10_deploy.sh.
#
#   STAMP=2026-09-16T1600 bash 90_rollback.sh          # restore the backed-up units
#   STAMP=... FULL=1      bash 90_rollback.sh          # + stop the reader entirely
#
# FULL=1 leaves the bot on its own fswebcam path - degraded (16 s photos) but
# working, which is exactly where it has been since 2026-09-15 17:12. It is the
# safe landing spot if the guild room needs a working bot and you are out of time.
set -uo pipefail

PI="${PI:-konsta@192.168.50.169}"
KEY="${KEY:-$HOME/.ssh/id_ed25519}"
STAMP="${STAMP:?set STAMP=<the stamp 10_deploy.sh printed>}"
FULL="${FULL:-0}"
SSH=(ssh -i "$KEY" -o ConnectTimeout=8 -o BatchMode=yes "$PI")

"${SSH[@]}" "bash -s" <<REMOTE
set -u
B=/home/konsta/deploy-backup-$STAMP
[ -d "\$B" ] || { echo "no backup at \$B"; ls -d /home/konsta/deploy-backup-* 2>/dev/null; exit 1; }
echo "restoring from \$B"

[ -f "\$B/_etc_systemd_system_kahvi-reader.service" ] && \
    sudo cp -a "\$B/_etc_systemd_system_kahvi-reader.service" /etc/systemd/system/kahvi-reader.service
[ -f "\$B/_etc_tmpfiles.d_kahvicam.conf" ] && \
    sudo cp -a "\$B/_etc_tmpfiles.d_kahvicam.conf" /etc/tmpfiles.d/kahvicam.conf
[ -f "\$B/_home_marci_dev_kiltiskahvi_config.py" ] && \
    sudo cp -a "\$B/_home_marci_dev_kiltiskahvi_config.py" /home/marci/dev/kiltiskahvi/config.py

sudo systemctl daemon-reload

if [ "$FULL" = "1" ]; then
    echo "FULL: stopping the reader; the bot goes back to fswebcam"
    sudo systemctl disable --now kahvi-reader
else
    sudo systemctl restart kahvi-reader
fi

sudo systemctl restart kahvibot
sleep 5
systemctl is-active kahvi-reader kahvibot
sudo systemctl status kahvibot --no-pager -n 6
REMOTE
