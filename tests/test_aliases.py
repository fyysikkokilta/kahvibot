from aliases import ALIASES, COMBINED


def test_brew_alias_matches_known_keywords():
    for word in ["brew", "covfefe", "hamiltonian", "tsufe", "kahvi", "BREW"]:
        assert ALIASES["brew"].search(word), word


def test_plot_alias_matches_known_keywords():
    for word in ["plot", "chart", "graph"]:
        assert ALIASES["plot"].search(word), word


def test_help_alias_matches_known_keywords():
    for word in ["help", "commands", "menu"]:
        assert ALIASES["help"].search(word), word


def test_aliases_use_word_boundaries():
    # "brewing" should not match the standalone "brew" keyword
    assert not ALIASES["brew"].search("brewing")
    assert not ALIASES["plot"].search("plotting")


def test_combined_matches_anything_the_individual_patterns_match():
    assert COMBINED.search("can you show me a chart")
    assert COMBINED.search("kahvi please")
    assert not COMBINED.search("good morning")
