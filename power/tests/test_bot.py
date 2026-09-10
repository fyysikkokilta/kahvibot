import asyncio
import csv
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import bot
import plot


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "power"])
        for ts, power in rows:
            w.writerow([ts, power])
    return path


def make_context(args=None):
    return SimpleNamespace(args=args or [], bot=AsyncMock())


def make_update(text=None):
    msg = SimpleNamespace(text=text) if text else SimpleNamespace(text="test")
    return SimpleNamespace(
        effective_chat=SimpleNamespace(id=123), message=msg, effective_message=msg
    )


def run(coro):
    return asyncio.run(coro)


def test_pick_devices_defaults_to_all_devices():
    context = make_context(args=[])
    assert bot.pick_devices(context) == bot.DEVICES


def test_pick_devices_uses_requested_device_lowercased():
    context = make_context(args=["OIKEA"])
    assert bot.pick_devices(context) == ["oikea"]


def test_cmd_plot_rejects_unknown_device(tmp_path, monkeypatch):
    monkeypatch.setattr(plot, "DATA_DIR", tmp_path)
    update = make_update()
    context = make_context(args=["../../etc/passwd"])

    run(bot.cmd_plot(update, context))

    context.bot.send_message.assert_awaited_once()
    (chat_id, text), _ = context.bot.send_message.call_args
    assert chat_id == 123
    assert "Unknown device" in text
    context.bot.send_photo.assert_not_awaited()


def test_cmd_plot_reports_no_data_yet_for_known_device(tmp_path, monkeypatch):
    monkeypatch.setattr(plot, "DATA_DIR", tmp_path)
    update = make_update()
    context = make_context(args=["oikea"])

    run(bot.cmd_plot(update, context))

    messages = [c.args[1] for c in context.bot.send_message.call_args_list]
    assert any("No data yet" in m for m in messages)
    context.bot.send_photo.assert_not_awaited()


def test_cmd_brew_rejects_unknown_device():
    update = make_update()
    context = make_context(args=["nope"])

    run(bot.cmd_brew(update, context))

    (chat_id, text), _ = context.bot.send_message.call_args
    assert "Unknown device" in text


def test_cmd_brew_reports_no_brews_for_known_device(tmp_path, monkeypatch):
    monkeypatch.setattr(plot, "DATA_DIR", tmp_path)
    update = make_update()
    context = make_context(args=["oikea"])

    run(bot.cmd_brew(update, context))

    (chat_id, text), _ = context.bot.send_message.call_args
    assert "No brews detected" in text


def test_cmd_help_lists_devices():
    update = make_update()
    context = make_context()

    run(bot.cmd_help(update, context))

    (chat_id, text), _ = context.bot.send_message.call_args
    for device in bot.DEVICES:
        assert device in text


def test_cmd_plot_inline_extracts_device(tmp_path, monkeypatch):
    monkeypatch.setattr(plot, "DATA_DIR", tmp_path)
    update = make_update(text="/plot_oikea")
    context = make_context()

    run(bot.cmd_plot_inline(update, context))

    messages = [c.args[1] for c in context.bot.send_message.call_args_list]
    assert any("oikea" in m for m in messages)


def test_cmd_brew_inline_extracts_device(tmp_path, monkeypatch):
    monkeypatch.setattr(plot, "DATA_DIR", tmp_path)
    update = make_update(text="/brew_vasen")
    context = make_context()

    run(bot.cmd_brew_inline(update, context))

    (chat_id, text), _ = context.bot.send_message.call_args
    assert "vasen" in text


def test_cmd_plot_inline_rejects_unknown_device(tmp_path, monkeypatch):
    monkeypatch.setattr(plot, "DATA_DIR", tmp_path)
    update = make_update(text="/plot_noexist")
    context = make_context()

    run(bot.cmd_plot_inline(update, context))

    (chat_id, text), _ = context.bot.send_message.call_args
    assert "Unknown device" in text


def test_handle_message_extracts_device(tmp_path, monkeypatch):
    monkeypatch.setattr(plot, "DATA_DIR", tmp_path)
    update = make_update(text="kahvi oikea")
    context = make_context()

    run(bot.handle_message(update, context))

    (chat_id, text), _ = context.bot.send_message.call_args
    assert "oikea" in text


def test_handle_message_no_device_defaults_to_all(tmp_path, monkeypatch):
    monkeypatch.setattr(plot, "DATA_DIR", tmp_path)
    update = make_update(text="kahvi")
    context = make_context()

    run(bot.handle_message(update, context))

    messages = [c.args[1] for c in context.bot.send_message.call_args_list]
    assert len(messages) == 2


# --- rate limiting & combined plot --------------------------------------------


def test_throttle_blocks_repeat_same_action(monkeypatch):
    monkeypatch.setattr(bot, "RATE_LIMIT_SECONDS", 10.0)
    bot._RATE_LIMIT.clear()
    assert bot._throttled(999, "plot") is False
    assert bot._throttled(999, "plot") is True
    assert bot._throttled(999, "brew") is False
    bot._RATE_LIMIT.clear()


def test_throttle_disabled_when_limit_zero(monkeypatch):
    monkeypatch.setattr(bot, "RATE_LIMIT_SECONDS", 0.0)
    bot._RATE_LIMIT.clear()
    assert bot._throttled(999, "plot") is False
    assert bot._throttled(999, "plot") is False
    bot._RATE_LIMIT.clear()


def test_cmd_plot_all_sends_combined_photo(tmp_path, monkeypatch):
    monkeypatch.setattr(plot, "DATA_DIR", tmp_path)
    now = datetime.now()
    for device in bot.DEVICES:
        write_csv(
            plot.get_csv_path(device),
            [((now - timedelta(minutes=1)).isoformat(), 123)],
        )
    update = make_update()
    context = make_context(args=["all"])

    run(bot.cmd_plot(update, context))

    context.bot.send_photo.assert_awaited_once()
    assert context.bot.send_photo.call_args.kwargs["caption"] == "Combined power usage since midnight"


# --- chat allow-list -------------------------------------------------------------


def test_allowed_chats_silences_other_chats(tmp_path, monkeypatch):
    monkeypatch.setattr(plot, "DATA_DIR", tmp_path)
    monkeypatch.setattr(bot, "ALLOWED_CHATS", {456})
    update = make_update(text="kahvi")
    context = make_context()

    run(bot.handle_message(update, context))
    run(bot.cmd_brew(update, context))
    run(bot.cmd_help(update, context))

    context.bot.send_message.assert_not_awaited()


def test_allowed_chats_admits_listed_chat(tmp_path, monkeypatch):
    monkeypatch.setattr(plot, "DATA_DIR", tmp_path)
    monkeypatch.setattr(bot, "ALLOWED_CHATS", {123})
    update = make_update()
    context = make_context(args=["oikea"])

    run(bot.cmd_brew(update, context))

    context.bot.send_message.assert_awaited_once()
