"""Tests for admin.py with canned command output; no systemd, no Telegram.
Run: python -m pytest test_admin.py"""
import logging
import subprocess
from types import SimpleNamespace

import admin

ADMIN = 6345419304


class Msg:
    def __init__(self):
        self.replies = []

    def reply_text(self, text, **kw):
        self.replies.append(text)


def update(user_id=ADMIN, chat_type="private"):
    return SimpleNamespace(effective_user=SimpleNamespace(id=user_id),
                           effective_chat=SimpleNamespace(type=chat_type, id=user_id),
                           effective_message=Msg())


class FakeRun:
    """Records argv; answers from a table keyed on the argv's first words."""

    def __init__(self, table=None):
        self.calls, self.table = [], table or {}

    def __call__(self, argv, **kw):
        self.calls.append(list(argv))
        for key, (rc, out) in self.table.items():
            if " ".join(argv).startswith(key):
                return subprocess.CompletedProcess(argv, rc, out.encode())
        return subprocess.CompletedProcess(argv, 0, b"")


def make(table=None):
    run = FakeRun(table)
    return admin.AdminCommands([ADMIN], logging.getLogger("test"), run=run), run


def test_strangers_and_group_chats_get_nothing_and_run_nothing():
    a, run = make()
    for u in (update(user_id=42), update(chat_type="supergroup"), update(chat_type="group")):
        a.on_restart(u, SimpleNamespace(args=["reader"]))
        a.on_health(u, SimpleNamespace(args=[]))
        a.on_errors(u, SimpleNamespace(args=[]))
        assert u.effective_message.replies == []
    assert run.calls == []


def test_restart_runs_only_the_fixed_argv():
    a, run = make()
    u = update()
    a.on_restart(u, SimpleNamespace(args=["reader"]))
    assert run.calls == [["systemctl", "restart", "kahvi-reader"]]
    assert u.effective_message.replies[-1].startswith("✅ Done.")
    run.calls.clear()
    a.on_restart(u, SimpleNamespace(args=["reader;", "reboot"]))      # not a key: usage only
    a.on_restart(u, SimpleNamespace(args=["$(reboot)"]))
    assert run.calls == [] and u.effective_message.replies[-1].startswith("Usage")


def test_reboot_needs_confirm():
    a, run = make()
    u = update()
    a.on_restart(u, SimpleNamespace(args=["pi"]))
    assert run.calls == [] and "confirm" in u.effective_message.replies[-1]
    a.on_restart(u, SimpleNamespace(args=["pi", "confirm"]))
    assert run.calls == [["systemctl", "--no-block", "reboot"]]


def test_failed_restart_reports_exit_and_output():
    a, run = make({"/usr/local/bin/kahvi-camreset": (1, "no USB video device found")})
    u = update()
    a.on_restart(u, SimpleNamespace(args=["camera"]))
    assert u.effective_message.replies[-1] == "❌ Failed (exit 1):\nno USB video device found"


JOURNAL = """\
Oct 30 13:08:22 kahviraspi python[3265]: WARNING capture failed (1 in a row): no frame written (exit 0): stat: No such file or directory
Oct 30 13:08:31 kahviraspi python[3265]: WARNING capture failed (2 in a row): no frame written (exit 0): stat: No such file or directory
Oct 30 13:08:54 kahviraspi python[3265]: WARNING camera reset: reset 1-1.4 041e:4095 Live! Cam Sync HD VF0770
Oct 30 13:09:04 kahviraspi python[3265]: INFO camera back after 3 failed captures
Oct 30 07:07:03 kahviraspi kahvibot[539]: Caught exception
Oct 30 07:07:03 kahviraspi python[539]: ERROR:kahvibot:Caught exception
Oct 30 07:07:03 kahviraspi kahvibot[539]:
                                          PIL.UnidentifiedImageError: cannot identify image file '/tmp/tmpzfdjgott.jpg'
Oct 30 07:07:03 kahviraspi python[539]: PIL.UnidentifiedImageError: cannot identify image file '/tmp/tmpzfdjgott.jpg'
Oct 30 07:30:00 kahviraspi python[539]: ERROR:kahvibot:
Oct 30 07:30:00 kahviraspi python[539]: Traceback (most recent call last):
Oct 30 07:30:00 kahviraspi python[539]: PIL.UnidentifiedImageError: cannot identify image file '/tmp/tmp_as7j1j6.jpg'
"""
KERNEL = """\
Oct 30 12:49:51 kahviraspi kernel: Under-voltage detected! (0x00050005)
Oct 30 12:50:09 kahviraspi kernel: Under-voltage detected! (0x00050005)
Oct 30 12:51:00 kahviraspi kernel: uvcvideo: Failed to resubmit video URB (-1).
"""


def test_errors_groups_counts_and_skips_the_syslog_copy():
    a, run = make({"journalctl -u": (0, JOURNAL), "journalctl -k": (0, KERNEL)})
    text = a.errors_text(6)
    assert "Last 6 h: 6 warning/error lines, 4 kinds" in text
    assert "under-voltage: 2, 📷 webcam URB drops: 1" in text
    assert "2× (last Oct 30 13:08:31)\nWARNING capture failed (2 in a row)" in text
    # syslog duplicate dropped, two temp names are one kind, bare headers skipped
    assert "2× (last Oct 30 07:30:00)\nPIL.UnidentifiedImageError" in text
    assert "Traceback" not in text and "ERROR:kahvibot:\n" not in text
    assert "INFO camera back" not in text
    assert ["journalctl", "-u", "kahvi-reader", "-u", "kahvibot", "--since", "-360min",
            "--no-pager", "-o", "short"] in run.calls


def test_errors_rejects_a_bad_window():
    a, run = make()
    u = update()
    a.on_errors(u, SimpleNamespace(args=["yesterday"]))
    assert u.effective_message.replies[-1].startswith("Usage") and run.calls == []


def test_health_decodes_throttling_and_unit_states():
    a, run = make({"systemctl is-active kahvi-reader": (3, "failed"),
                   "systemctl is-active": (0, "active"),
                   "vcgencmd": (0, "throttled=0x50000"),
                   "uptime": (0, "up 1 hour, 20 minutes"),
                   "sh -c": (0, "7"),
                   "df": (0, "Avail\n  9.1G")})
    text = a.health_text()
    assert "❌ kahvi-reader: failed" in text and "✅ kahvibot: active" in text
    assert "throttled=0x50000: under-voltage since boot, throttled since boot" in text
    assert "under-voltage events this boot: 7" in text and "free on /: 9.1G" in text


def test_long_output_is_clipped_for_telegram():
    many = "".join("Oct 30 13:%02d:00 kahviraspi python[1]: ERROR kind %s\n" % (i % 60, chr(65 + i % 26) * 400)
                   for i in range(40))
    a, _ = make({"journalctl -u": (0, many)})
    assert len(a.errors_text(24)) <= admin.TELEGRAM_MAX
