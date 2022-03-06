# -*- coding: utf-8 -*-
"""
A quick script that responds to all messages that the bot is currently offline.
"""

from config import bot_token, trigger_words

import re

from telegram import (
    Update,
    MessageEntity,
)

from telegram.ext import (
    Updater,
    Filters,
    CommandHandler,
    MessageHandler,
    CallbackContext,
)


def handle_message(update: Update, ctx: CallbackContext):
    """
    Respond to all messages with a message saying that the bot is offline.
    """
    bot_user = ctx.bot.get_me()
    if bot_user is not None:
        bot_username_fi = bot_user.first_name
        bot_username_en = bot_username_fi
    else:
        bot_username_fi = "Botti"
        bot_username_en = "The bot"

    msg = f"{bot_username_fi} on huoltokatkolla. Yritä myöhemmin uudelleen.\n\n{bot_username_en} is on a maintenance break. Please try again later."
    update.message.reply_text(msg)


if __name__ == "__main__":
    if not bot_token:
      raise ValueError("Bot token not found, check the config file")

    updater = Updater(token=bot_token, use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("status", handle_message))
    dispatcher.add_handler(CommandHandler("help", handle_message))
    trigger_words_regex = re.compile("|".join(trigger_words), re.IGNORECASE)
    dispatcher.add_handler(MessageHandler(
        Filters.text & (
            Filters.chat_type.private  # answer any messages in private chat
            # in group chats, answer mentions or messages that contain the trigger words
            | Filters.entity(MessageEntity.MENTION)
            | Filters.regex(trigger_words_regex)
            ),
        handle_message
    ))

    updater.start_polling(drop_pending_updates=True)
    updater.idle()
