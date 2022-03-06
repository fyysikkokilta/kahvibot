"""
Minimal config file for kahvibot. Just define values as normal Python code.
"""

# put your bot token here as a string
bot_token = ""

# The Telegram username of the bot's admin. This is used in the help text.
admin_username = ""

# The size of the pictures the webcamera takes.  As of 2022-03-06, the guild
# room has a Creative Live! Cam Sync HD USB webcamera, which at least claims to
# be 720p
camera_dimensions = (1280, 720)


# Use this picture as a watermark, for sponsorships etc. Should be a PNG image
# with transparency. It is overlaid directly with the camera image, so it
# should have the same dimensions as `camera_dimensions` above. Leave as an
# empty string to have no watermark.
watermark_path = ""


# if a message contains any of these words, the bot responds
trigger_words = [
    "kahvi",
    "\u2615", # coffeecup emoji
    "tsufe",
    "kahavi",
    "coffee",
    #"sima", # wappu mode
]
