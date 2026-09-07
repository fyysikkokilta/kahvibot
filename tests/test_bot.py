import asyncio
import csv
from types import SimpleNamespace
from unittest.mock import AsyncMock

import bot
import plot


def make_context(args=None):
    return SimpleNamespace(args=args or [], bot=AsyncMock())


def make_update():
    return SimpleNamespace(effective_chat=SimpleNamespace(id=123))


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
