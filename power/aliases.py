import re

ALIASES = {
    "brew": re.compile(r"\b(?:brew|covfefe|hamiltonian|tsufe|kahvi)\b", re.IGNORECASE),
    "plot": re.compile(r"\b(?:plot|chart|graph)\b", re.IGNORECASE),
    "help": re.compile(r"\b(?:help|commands|menu)\b", re.IGNORECASE),
}

COMBINED = re.compile(
    "|".join(f"(?:{p.pattern})" for p in ALIASES.values()), re.IGNORECASE
)