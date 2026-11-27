"""The bot script has no .py suffix, so no test imports it and pytest never
compiles it. A syntax error in it reached the Pi on 2026-10-30 and kept the bot
down until it was fixed by hand. Needs no token, config or network.

    python -m pytest test_compile.py
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent


def test_bot_script_compiles():
    src = (HERE / "kahvibot").read_text(encoding="utf-8")
    compile(src, "kahvibot", "exec")
