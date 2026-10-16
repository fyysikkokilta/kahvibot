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
# The reader service (reader/pipeline, below) reads the coffee level from each
# frame and stores it. Any failure in the reader silently degrades to "no
# reading"; the photo always goes out.

# Show readings to users. Keep False for the burn-in week: readings are still
# stored, so drift can be caught before going visible.
coffee_reader_show = False

# The reader service's SQLite store, opened read-only for the "last brewed"
# caption line. "" = no such line.
coffee_db = ""                        # e.g. "/home/konsta/coffee-data/kahvi.db"

# Advisory camera lock shared with the background sampler ("" = no lock,
# exactly today's behaviour). The sampler skips its tick while the bot holds
# it; the bot waits at most 5 s and then takes the photo anyway.
camera_lock = ""

# Show /graph (the coffee level curve). Drawn by the reader service.
coffee_graph_enabled = False

# Messages containing any of these get the graph instead of a photo. Matched
# as prefixes and case-insensitively, so Finnish endings need not be listed:
# "graafi" also catches graafin/graafia, "aikasarja" catches aikasarjan.
# Only used when coffee_graph_enabled is True. These are checked before
# trigger_words below, so "kahvigraafi" gives the graph, not a photo.
# Note "maara"/"amount": someone asking for the amount arguably wants the
# current reading rather than the day's curve - move those two lines to
# trigger_words if that turns out to be how people use it.
graph_trigger_words = [
    "graafi", "graph", "kuvaaja", "aikasarja", "taikasarja",
    "timeseries", "time series", "time-series", "trendi",
    "määrä",
    "amount", "ammount", "plot", "chart",
]

# --- Reader service (reader/pipeline, reader/PIPELINE.md) -------------------------
# When set, the bot asks the resident reader service for its freshest frame and
# reading instead of running fswebcam itself, and gets /graph from it. Any
# failure falls back to a plain fswebcam photo with no reading.
# Path of the AF_UNIX socket (kahvi-reader.service), or a TCP port on a dev box.
reader_service_socket = ""            # e.g. "/run/kahvi-sampler/ipc.sock"
reader_service_max_age = 15.0         # reuse a service frame this many seconds old
reader_service_timeout = 3.0          # seconds before falling back to the camera

# --- Coffee-machine power plugs ---------------------------------------------
# The reader service logs the plugs and their brews into coffee_db. With
# coffee_db set, photo captions get a "keitetty 12 min sitten / brewed 12 min
# ago" line per pot (or "brewing now").
power_devices = {"left": "east", "right": "west"}   # camera side -> plug name (camera-left = EAST)

# Caption text on replies the whole group sees (photo readings, "last brewed",
# the survey invitation, the graph caption). False = pictures only, which is
# the burn-in setting: the survey button still appears so people can annotate,
# and error replies still speak. Set True once the numbers are trusted.
caption_text_enabled = False

# Burn each machine's reading into the bottom corners of the photo
# (banner.py). Recommended while caption_text_enabled is False, since it is
# then the only place a number appears. The plate sits over the machine it
# describes, so the names are compass points rather than left/right: which
# pot is 'left' depends on whether you are the camera or a person standing
# at the machines, and that ambiguity has already caused one wrong mapping.
photo_banner_enabled = False
photo_banner_names = {"left": "EAST", "right": "WEST"}
photo_banner_font = ""      # e.g. a DejaVuSans-Bold.ttf path; blank = autodetect

# --- Annotation surveys (feedback.py; UX_FEEDBACK.md) ---
coffee_survey_enabled = False
coffee_survey_bot_username = "TsufeBot"   # for t.me deep links, no @
coffee_survey_dir = "/home/konsta/coffee-data/survey"
coffee_survey_reader_dir = "/home/marci/dev/kiltiskahvi/reader/models"  # calibration.json (optional)
# Ladder span per side, FRAME pixels: median y_base/y_top of the desktop
# annotations per side (n=98 left / 159 right, era hd2026). NEVER from
# per-frame model output - that would anchor the ladder.
coffee_survey_span = {"left":  {"base": 568.4, "top": 206.3},
                      "right": {"base": 554.1, "top": 222.6}}
coffee_survey_span_source = "per_side_const_v1"
coffee_survey_rate = 8            # target prompts/day (probability = rate/eligible users)
coffee_survey_blind_frac = 0.25   # fraction of prompts served from the blind pool
coffee_survey_daily_cap = 15      # global prompts/day
coffee_survey_volunteer_cap = 5   # volunteered surveys/user/day
coffee_survey_eval_day_salt = "coffee10-blind-v1"  # MUST match inject_hand_lines salt
coffee_survey_frames_dir = ""     # blind pool of retained frames (stem.jpg + stem.json)
coffee_survey_sentinel_dir = ""   # desktop-annotated frames + sentinel_lines.json
coffee_survey_admin_chat = 0      # nightly tg_clicks gzip goes here; 0 = off


# if a message contains any of these words, the bot responds
trigger_words = [
    "kahvi",
    "\u2615", # coffeecup emoji
    "tsufe",
    "kahavi",
    "coffee",
    #"sima", # wappu mode
]
