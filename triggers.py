"""Keyword matching for the bot's message triggers.

Kept out of the bot script so it can be tested without a Telegram token or a
config file: `python -m pytest test_triggers.py`.
"""
from __future__ import annotations

import re

# Words that ask for the graph rather than a photo. Matched as prefixes, so
# Finnish endings need not be listed. "taikasarja" is in here deliberately: it
# is the usual slip for "aikasarja" and there is nothing else it could mean.
DEFAULT_GRAPH_WORDS = [
    "graafi", "graph", "kuvaaja", "aikasarja", "taikasarja",
    "timeseries", "time series", "time-series", "trendi",
    "määrä", "amount", "ammount", "plot", "chart",
]

# Finnish writes compounds as one word, so "kahvigraafi" and "kahvimäärä" are
# the natural way to ask. A plain \b would miss every one of them, and dropping
# \b altogether would make "telegraafi" ask for the graph. A trigger therefore
# counts at a word boundary, or joined straight onto one of the coffee words.
COMPOUND_PREFIXES = ("kahvi", "kahvin", "kahavi", "tsufe", "coffee")


def graph_words_regex(words=None, prefixes=COMPOUND_PREFIXES):
    """Match any of `words` at the start of a word, or compounded onto a coffee word.

    Finnish endings need not be listed: "aikasarja" also catches aikasarjan and
    aikasarjaa. Not anchored at the end on purpose, since "graafi" matching
    "graafinen" is still a request for the graph. A space in a trigger matches a
    space, a hyphen or nothing, so "time series" covers "time-series" too.
    """
    words = DEFAULT_GRAPH_WORDS if words is None else words
    # re.escape() escapes the space itself (it is special under re.VERBOSE), so
    # the backslash it adds has to be consumed along with the space.
    parts = [re.sub(r"\\?\s+", r"[\\s\\-]?", re.escape(w.strip()))
             for w in words if w and w.strip()]
    if not parts:
        return None
    starts = [r"\b"] + [r"(?<=%s)" % re.escape(p) for p in prefixes]
    return re.compile(r"(?:" + "|".join(starts) + r")(?:" + "|".join(parts) + ")",
                      re.IGNORECASE)
