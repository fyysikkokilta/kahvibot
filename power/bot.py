import asyncio
import logging
import time

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from config import TELEGRAM_TOKEN, DEVICES
from aliases import ALIASES, COMBINED
from plot import get_csv_path, plot_power, plot_all, last_brew, brew_summary

logger = logging.getLogger("bot")

try:
    from config import ADMIN_CHAT_ID
except ImportError:
    ADMIN_CHAT_ID = None
ADMIN_CHAT_ID = int(ADMIN_CHAT_ID) if str(ADMIN_CHAT_ID or "").strip().isdigit() else None

try:
    from config import RATE_LIMIT_SECONDS
except ImportError:
    RATE_LIMIT_SECONDS = 3.0
RATE_LIMIT_SECONDS = float(RATE_LIMIT_SECONDS or 0)

try:
    from config import ALLOWED_CHATS
except ImportError:
    ALLOWED_CHATS = []
ALLOWED_CHATS = {int(c) for c in (ALLOWED_CHATS or [])}

COMMANDS = [
    ("plot", "Power plot for a device"),
    ("brew", "When was the last brew"),
    ("help", "Show available commands"),
]

_device_index = 0

_RATE_LIMIT = {}


def _throttled(chat_id, action):
    """True if this chat already did `action` within RATE_LIMIT_SECONDS."""
    if RATE_LIMIT_SECONDS <= 0:
        return False
    key = (chat_id, action)
    now = time.monotonic()
    last = _RATE_LIMIT.get(key)
    if last is not None and now - last < RATE_LIMIT_SECONDS:
        return True
    _RATE_LIMIT[key] = now
    return False


def _allowed(update: Update) -> bool:
    """False when ALLOWED_CHATS is set and this chat is not in it. The bot then
    stays silent: in a group it shares with kahvibot, both would otherwise answer
    every "kahvi"."""
    if not ALLOWED_CHATS:
        return True
    chat = update.effective_chat
    return chat is not None and chat.id in ALLOWED_CHATS


def pick_devices(context):
    return [context.args[0].lower()] if context.args else DEVICES


async def cmd_plot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return
    if _throttled(update.effective_chat.id, "plot"):
        await context.bot.send_message(
            update.effective_chat.id,
            f"Please wait {RATE_LIMIT_SECONDS:g}s between plot requests.",
        )
        return
    for device in pick_devices(context):
        if device == "all":
            await context.bot.send_message(
                update.effective_chat.id, "Generating combined plot..."
            )
            try:
                png_path = await asyncio.to_thread(plot_all)
            except FileNotFoundError:
                await context.bot.send_message(
                    update.effective_chat.id, "No recent data for any device."
                )
                continue
            caption = "Combined power usage since midnight"
            with open(png_path, "rb") as f:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id, photo=f, caption=caption
                )
            continue
        if device not in DEVICES:
            await context.bot.send_message(
                update.effective_chat.id,
                f"Unknown device '{device}'. Available: {', '.join(DEVICES)}",
            )
            continue
        csv_path = get_csv_path(device)
        if not csv_path.is_file():
            await context.bot.send_message(update.effective_chat.id, f"No data yet for {device}.")
            continue
        await context.bot.send_message(update.effective_chat.id, f"Generating plot for {device}...")
        try:
            png_path = await asyncio.to_thread(plot_power, device)
            caption = await asyncio.to_thread(_brew_caption, device)
        except FileNotFoundError:
            await context.bot.send_message(update.effective_chat.id, f"No recent data for {device}.")
            continue
        with open(png_path, "rb") as f:
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=f, caption=caption)


def _brew_caption(device):
    return brew_summary(last_brew(device))


async def cmd_brew(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return
    if _throttled(update.effective_chat.id, "brew"):
        await context.bot.send_message(
            update.effective_chat.id, "Please wait a moment before asking again."
        )
        return
    for device in pick_devices(context):
        if device not in DEVICES:
            await context.bot.send_message(
                update.effective_chat.id,
                f"Unknown device '{device}'. Available: {', '.join(DEVICES)}",
            )
            continue
        summary = await asyncio.to_thread(_brew_caption, device)
        await context.bot.send_message(update.effective_chat.id, f"{device}: {summary}")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return
    text = (
        "Available commands:\n"
        "/plot [device] — power plot\n"
        f"Devices: {', '.join(DEVICES)}\n"
        "/brew — last brew info\n"
        "/help — this menu\n"
        "Also: /plot_<device>, /brew_<device>, /plot all, and plain messages "
        "with brew/kahvi/tsufe or plot/graph in them."
    )
    await context.bot.send_message(update.effective_chat.id, text)


async def run_action(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str):
    if action == "plot":
        await cmd_plot(update, context)
    elif action == "brew":
        await cmd_brew(update, context)
    else:
        await cmd_help(update, context)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update) or update.message is None or not update.message.text:
        return
    text = update.message.text.strip().lower()
    words = text.split()
    device = next((w for w in words if w in DEVICES), None)
    if device:
        context.args = [device]
    for action, pattern in ALIASES.items():
        if pattern.search(text):
            await run_action(update, context, action)
            return


def _inline_device(update: Update) -> str:
    return update.effective_message.text.split("_", 1)[1].lower()


async def cmd_plot_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.args = [_inline_device(update)]
    await cmd_plot(update, context)


async def cmd_brew_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.args = [_inline_device(update)]
    await cmd_brew(update, context)


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception while handling an update:", exc_info=context.error)
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(text=f"Bot error: {context.error}", chat_id=ADMIN_CHAT_ID)
        except Exception:
            logger.exception("Failed to notify admin")


async def post_init(application: Application) -> None:
    try:
        me = await application.bot.get_me()
    except Exception as exc:
        logger.error("Failed to validate TELEGRAM_TOKEN: %s", exc)
        raise RuntimeError(
            f"Bot token failed validation (check TELEGRAM_TOKEN in config.py): {exc}"
        ) from exc
    logger.info("Bot online as @%s", me.username)
    await application.bot.set_my_commands(COMMANDS)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.add_error_handler(error_handler)
    app.add_handler(CommandHandler(["plot"], cmd_plot))
    app.add_handler(CommandHandler(["brew"], cmd_brew))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("plot_all", cmd_plot_inline))
    for device in DEVICES:
        app.add_handler(CommandHandler(f"plot_{device}", cmd_plot_inline))
        app.add_handler(CommandHandler(f"brew_{device}", cmd_brew_inline))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex(COMBINED), handle_message))
    app.run_polling()


if __name__ == "__main__":
    main()
