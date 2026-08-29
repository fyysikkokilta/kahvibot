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


# --- Coffee level reader (optional) -----------------------------------------
# Runs a small ONNX model on each captured frame in a short-lived subprocess
# and (optionally) captions the photo with the amount of coffee. Any failure
# in the reader silently degrades to "no reading"; the photo always goes out.

# Command that runs the reader; the frame path is appended. Empty = disabled.
# e.g. ["/home/pi/coffee-reader/venv/bin/python", "/home/pi/coffee-reader/read_frame.py"]
coffee_reader_cmd = []

# Seconds to wait for the reader before giving up on this frame.
coffee_reader_timeout = 30

# Show readings to users. Keep False for the burn-in week: readings are still
# written to coffee_reader_log, so drift can be caught before going visible.
coffee_reader_show = False

# JSONL file that every reading is appended to ("" disables logging).
coffee_reader_log = "/home/pi/coffee-reader/readings.jsonl"

# Advisory camera lock shared with the background sampler ("" = no lock,
# exactly today's behaviour). The sampler skips its tick while the bot holds
# it; the bot waits at most 5 s and then takes the photo anyway.
camera_lock = ""


# if a message contains any of these words, the bot responds
trigger_words = [
    "kahvi",
    "\u2615", # coffeecup emoji
    "tsufe",
    "kahavi",
    "coffee",
    #"sima", # wappu mode
]
