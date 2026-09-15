"""Which handler does a message reach? Needs no token, config or network.

    python -m pytest test_triggers.py
"""
import re

import pytest

from triggers import DEFAULT_GRAPH_WORDS, graph_words_regex

# the deployed photo triggers, from config-example.py
PHOTO = re.compile("|".join(["kahvi", "☕", "tsufe", "kahavi", "coffee"]), re.IGNORECASE)
GRAPH = graph_words_regex()


def route(text):
    """The graph handler is registered first, so it wins when both match."""
    if GRAPH.search(text):
        return "graph"
    if PHOTO.search(text):
        return "photo"
    return "nothing"


@pytest.mark.parametrize("text", [
    "graafi", "graafin", "graafia", "näytä graafi", "GRAAFI",
    "aikasarja", "aikasarjan", "aikasarjaa",
    "taikasarja",                      # the usual slip, and unambiguous
    "timeseries", "time series", "time-series",
    "määrä", "määrää", "kahvin määrä",
    "amount", "ammount of coffee",
    "plot", "chart", "trendi", "kuvaaja",
])
def test_asks_for_the_graph(text):
    assert route(text) == "graph"


@pytest.mark.parametrize("text", ["kahvigraafi", "kahvimäärä", "kahviaikasarja",
                                  "tsufegraafi", "coffeeamount", "kahvinmäärä"])
def test_finnish_compounds_reach_the_graph_not_the_photo(text):
    """Finnish glues the words together; a word-boundary match would miss all of
    these and hand them to the photo handler, since they contain "kahvi"."""
    assert route(text) == "graph"


@pytest.mark.parametrize("text", ["kahvi", "tsufe", "onko kahvia", "☕", "kahavi"])
def test_plain_coffee_still_gets_a_photo(text):
    assert route(text) == "photo"


@pytest.mark.parametrize("text", ["telegraafi", "sähkögraafi", "moi", "kiitos"])
def test_unrelated_words_trigger_nothing(text):
    """Compounding is allowed only onto the coffee words, so a telegraph is
    not a request for a coffee graph."""
    assert route(text) == "nothing"


def test_multiword_trigger_is_separator_insensitive():
    rx = graph_words_regex(["time series"])
    for t in ("time series", "time-series", "timeseries"):
        assert rx.search(t), t


def test_empty_list_disables_matching():
    assert graph_words_regex([]) is None
    assert graph_words_regex(["", "  "]) is None


def test_default_list_covers_what_was_asked_for():
    for w in ("graafi", "graph", "aikasarja", "taikasarja", "timeseries",
              "määrä", "amount", "ammount"):
        assert w in DEFAULT_GRAPH_WORDS
