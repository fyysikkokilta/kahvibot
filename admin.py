"""Admin commands over a private chat with the bot: /health, /errors, /restart.

The bot runs as root, so this is a remote control for the Pi. Two rules keep it
from being more than that:

  * only numeric Telegram user ids in `admin_user_ids` count, and only in a
    private chat. Usernames are not used: they can be changed and then claimed
    by someone else. Anyone else gets no reply at all, and the attempt is logged.
  * every command is a fixed argv from the tables below. Nothing a user types
    reaches a shell or an argument list; `/restart` only picks a key.

Everything runs through `self.run` (subprocess.run by default), so the tests
drive it with canned output and no systemd.
"""
from __future__ import annotations

import collections
import os
import re
import sqlite3
import subprocess
import time

UNITS = ("kahvibot", "kahvi-reader", "mosquitto", "zigbee2mqtt")

# /restart <what>: (argv, what to say first). The bot's own restart and the
# reboot are --no-block, so the reply goes out before the process dies.
RESTARTS = {
    "reader": (["systemctl", "restart", "kahvi-reader"], "Restarting kahvi-reader..."),
    "camera": (["/usr/local/bin/kahvi-camreset"], "Resetting the webcam on the USB bus..."),
    "bot": (["systemctl", "--no-block", "restart", "kahvibot"],
            "Restarting the bot. It answers again in ~30 s."),
    "pi": (["systemctl", "--no-block", "reboot"],
           "Rebooting the Pi. Back in ~2 min, if the power supply holds."),
}
CONFIRM = {"pi"}            # these need a trailing "confirm"

# get_throttled bits (Raspberry Pi firmware docs)
THROTTLED_BITS = {
    0: "under-voltage now", 1: "ARM frequency capped now", 2: "throttled now",
    3: "soft temperature limit now", 16: "under-voltage since boot",
    17: "frequency capped since boot", 18: "throttled since boot",
    19: "soft temperature limit since boot",
}

# What counts as an error line in the services' journal. Python logs go to
# stderr, which journald files at priority info whatever the level, so the
# level has to be read from the text instead of with `journalctl -p`.
_LEVEL = re.compile(r"\b(WARNING|ERROR|CRITICAL)\b|\w+Error:")
# lines that say only that an error follows: the next line is the error itself
_EMPTY = re.compile(r"^(ERROR:\w+:|Traceback \(most recent call last\):)$")
_TMPFILE = re.compile(r"/tmp/tmp\w+")
_PREFIX = re.compile(r"^\w{3}\s+\d+ [\d:]+ \S+ (\S+?)\[\d+\]: ")   # "Oct 30 13:08:22 host unit[pid]: "
_NUMBERS = re.compile(r"\d+(\.\d+)?")
TELEGRAM_MAX = 4000


class AdminCommands:
    def __init__(self, admin_ids, logger, coffee_db: str = "", run=subprocess.run):
        self.admin_ids = {int(i) for i in admin_ids or ()}
        self.logger = logger
        self.coffee_db = coffee_db
        self.run = run

    # -- access ----------------------------------------------------------------

    def allowed(self, update) -> bool:
        user, chat = update.effective_user, update.effective_chat
        ok = (user is not None and chat is not None and chat.type == "private"
              and user.id in self.admin_ids)
        if not ok:
            self.logger.warning("admin command refused: user %s in %s chat %s",
                                getattr(user, "id", None), getattr(chat, "type", None),
                                getattr(chat, "id", None))
        return ok

    def _sh(self, argv, timeout=20.0) -> "tuple[int, str]":
        try:
            p = self.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        except subprocess.TimeoutExpired:
            return 124, "timed out after %.0f s" % timeout
        except OSError as e:
            return 127, str(e)
        return p.returncode, (p.stdout or b"").decode("utf-8", "replace").strip()

    # -- /health ---------------------------------------------------------------

    def health_text(self) -> str:
        lines = []
        for unit in UNITS:
            _, state = self._sh(["systemctl", "is-active", unit])
            lines.append("%s %s: %s" % ("✅" if state == "active" else "❌", unit, state or "?"))
        _, up = self._sh(["uptime", "-p"])
        lines.append("⏱ " + (up or "uptime unknown"))
        lines.append("⚡ " + self._throttled())
        _, n = self._sh(["sh", "-c", "journalctl -k -b --no-pager | grep -c 'Under-voltage detected'"])
        lines.append("⚡ under-voltage events this boot: %s" % (n.strip() or "0"))
        lines.append("📷 /dev/video0: %s" % ("present" if os.path.exists("/dev/video0") else "MISSING"))
        lines.append("☕ " + self._last_reading())
        _, df = self._sh(["df", "-h", "--output=avail", "/"])
        free = df.splitlines()[-1].strip() if df else "?"
        lines.append("💾 free on /: %s" % free)
        return "\n".join(lines)

    def _throttled(self) -> str:
        rc, out = self._sh(["vcgencmd", "get_throttled"])
        m = re.search(r"0x[0-9a-fA-F]+", out)
        if rc != 0 or not m:
            return "get_throttled unavailable"
        v = int(m.group(0), 16)
        flags = [t for b, t in sorted(THROTTLED_BITS.items()) if v & (1 << b)]
        return "throttled=%s%s" % (m.group(0), (": " + ", ".join(flags)) if flags else " (all clear)")

    def _last_reading(self) -> str:
        if not self.coffee_db:
            return "no coffee_db configured"
        try:
            conn = sqlite3.connect("file:%s?mode=ro" % self.coffee_db, uri=True, timeout=2.0)
            try:
                (t,) = conn.execute("SELECT max(t) FROM readings").fetchone()
            finally:
                conn.close()
        except sqlite3.Error as e:
            return "readings unavailable (%s)" % e
        if t is None:
            return "no readings yet"
        return "last reading %.0f min ago" % ((time.time() - t) / 60)

    # -- /errors ---------------------------------------------------------------

    def errors_text(self, hours: float = 24.0, top: int = 12) -> str:
        since = "-%dmin" % int(hours * 60)
        _, out = self._sh(["journalctl", "-u", "kahvi-reader", "-u", "kahvibot", "--since", since,
                           "--no-pager", "-o", "short"], timeout=30.0)
        counts, last = collections.Counter(), {}
        for line in out.splitlines():
            m = _PREFIX.match(line)
            # The bot logs every line twice: to syslog as "kahvibot" (a multi-line
            # entry, continued on indented lines) and to stderr as "python". Count
            # the stderr copy only, which is also the only copy the reader writes.
            if m is None or m.group(1) == "kahvibot" or not _LEVEL.search(line):
                continue
            msg = line[m.end():].strip()
            if _EMPTY.match(msg):
                continue
            # "3 in a row" and "4 in a row", or two temp file names, are one entry
            key = _NUMBERS.sub("#", _TMPFILE.sub("/tmp/…", msg))[:160]
            counts[key] += 1
            last[key] = (line[:15], msg)
        _, kern = self._sh(["journalctl", "-k", "--since", since, "--no-pager", "-o", "short"],
                           timeout=30.0)
        uv = kern.count("Under-voltage detected")
        urb = kern.count("Failed to resubmit video URB")

        head = "Last %g h: %d warning/error lines, %d kinds" % (hours, sum(counts.values()), len(counts))
        lines = [head, "⚡ under-voltage: %d, 📷 webcam URB drops: %d" % (uv, urb)]
        for key, n in counts.most_common(top):
            when, msg = last[key]
            lines.append("\n%d× (last %s)\n%s" % (n, when, msg[:300]))
        if len(counts) > top:
            lines.append("\n... and %d more kinds" % (len(counts) - top))
        return _clip("\n".join(lines))

    # -- telegram handlers -------------------------------------------------------

    def on_health(self, update, ctx):
        if not self.allowed(update):
            return
        self.logger.info("admin /health by %s", update.effective_user.id)
        update.effective_message.reply_text(self.health_text())

    def on_errors(self, update, ctx):
        if not self.allowed(update):
            return
        hours = 24.0
        if ctx.args:
            try:
                hours = min(max(float(ctx.args[0]), 0.1), 24.0 * 14)
            except ValueError:
                update.effective_message.reply_text("Usage: /errors [hours], e.g. /errors 6")
                return
        self.logger.info("admin /errors %g by %s", hours, update.effective_user.id)
        update.effective_message.reply_text(self.errors_text(hours))

    def on_restart(self, update, ctx):
        if not self.allowed(update):
            return
        msg = update.effective_message
        args = [a.lower() for a in (ctx.args or [])]
        what = args[0] if args else ""
        if what not in RESTARTS:
            msg.reply_text("Usage: /restart reader | camera | bot | pi confirm")
            return
        if what in CONFIRM and args[1:2] != ["confirm"]:
            msg.reply_text("That reboots the whole Pi. Send /restart %s confirm to do it." % what)
            return
        argv, notice = RESTARTS[what]
        self.logger.warning("admin /restart %s by %s", what, update.effective_user.id)
        msg.reply_text(notice)
        rc, out = self._sh(argv, timeout=60.0)
        if what in ("bot", "pi"):
            return                              # queued; the result is the bot coming back
        if rc == 0:
            tail = ("\n" + out.splitlines()[-1]) if out else ""
            msg.reply_text("✅ Done.%s\nCheck with /health." % tail)
        else:
            msg.reply_text("❌ Failed (exit %d):\n%s" % (rc, _clip(out or "no output", 1500)))

    def on_admin(self, update, ctx):
        if not self.allowed(update):
            return
        update.effective_message.reply_text(
            "/health - services, power, camera, last reading\n"
            "/errors [hours] - warnings and errors, grouped (default 24 h)\n"
            "/restart reader | camera | bot - restart one part\n"
            "/restart pi confirm - reboot the Pi")

    def register(self, dispatcher, CommandHandler):
        for name, cb in (("admin", self.on_admin), ("health", self.on_health),
                         ("errors", self.on_errors), ("restart", self.on_restart)):
            dispatcher.add_handler(CommandHandler(name, cb))


def _clip(text: str, limit: int = TELEGRAM_MAX) -> str:
    return text if len(text) <= limit else text[:limit - 20] + "\n... (cut)"
