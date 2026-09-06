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
from plot import get_csv_path, plot_power, last_brew, brew_summary

COMMANDS = [
    ("plot", "Power plot for a device"),
    ("brew", "When was the last brew"),
    ("help", "Show available commands"),
]

_device_index = 0


def pick_devices(context):
    return [context.args[0].lower()] if context.args else DEVICES


async def cmd_plot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for device in pick_devices(context):
        csv_path = get_csv_path(device)
        if not csv_path.is_file():
            await context.bot.send_message(update.effective_chat.id, f"No data yet for {device}.")
            continue
        await context.bot.send_message(update.effective_chat.id, f"Generating plot for {device}...")
        try:
            png_path = plot_power(device)
        except FileNotFoundError:
            await context.bot.send_message(update.effective_chat.id, f"No recent data for {device}.")
            continue
        caption = brew_summary(last_brew(device))
        with open(png_path, "rb") as f:
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=f, caption=caption)


async def cmd_brew(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for device in pick_devices(context):
        await context.bot.send_message(
            update.effective_chat.id, f"{device}: {brew_summary(last_brew(device))}"
        )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Available commands:\n"
        "/plot [device] — power plot\n"
        f"Devices: {', '.join(DEVICES)}\n"
        "/brew — last brew info\n"
        "/help — this menu"
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
    text = update.message.text.strip().lower()
    for action, pattern in ALIASES.items():
        if pattern.search(text):
            await run_action(update, context, action)
            return


async def post_init(application: Application) -> None:
    await application.bot.set_my_commands(COMMANDS)


def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler(["plot"], cmd_plot))
    app.add_handler(CommandHandler(["brew"], cmd_brew))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex(COMBINED), handle_message))
    app.run_polling()


if __name__ == "__main__":
    main()