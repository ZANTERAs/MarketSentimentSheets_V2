# aliases_from_yfinance.py

import re
from functools import lru_cache

import yfinance as yf

# Common corporate suffixes to strip from names
CORP_SUFFIXES = [
    "inc.", "inc", "corp.", "corp", "corporation",
    "co.", "co", "ltd.", "ltd",
    "s.a.", "s.a", "sa", "s.a.c.i.",
    "plc", "ag", "nv"
]

def _normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def _strip_suffixes(name: str) -> str:
    """
    Remove common corporate suffixes from the end of the name.
    E.g. "NVIDIA Corporation" -> "NVIDIA"
    """
    name = name.strip()
    # Remove stuff after comma, e.g. "MercadoLibre, Inc." -> "MercadoLibre"
    name = name.split(",")[0]

    tokens = name.split()
    # Drop trailing suffix tokens
    while tokens:
        last = tokens[-1].lower().strip(".")
        if last in CORP_SUFFIXES:
            tokens.pop()
        else:
            break

    return " ".join(tokens).strip()


@lru_cache(maxsize=512)
def get_aliases_from_yfinance(ticker: str) -> list[str]:
    """
    Build a list of aliases for the company behind `ticker`
    using yfinance metadata.
    """
    ticker = ticker.upper()
    aliases: set[str] = set()

    # Always include some ticker variants
    aliases.add(ticker)
    # Remove dot, e.g. BRK.B -> BRKB
    aliases.add(ticker.replace(".", ""))
    # Part before dot, e.g. BRK.B -> BRK
    aliases.add(ticker.split(".")[0])

    try:
        t = yf.Ticker(ticker)
        # Newer yfinance recommends get_info(); fallback to .info if needed
        try:
            info = t.get_info()
        except AttributeError:
            info = getattr(t, "info", {}) or {}
    except Exception:
        info = {}

    # Collect names from yfinance
    raw_names = []
    for key in ("longName", "shortName"):
        val = info.get(key)
        if isinstance(val, str) and val.strip():
            raw_names.append(_normalize_spaces(val))

    # Add cleaned versions
    for name in raw_names:
        aliases.add(name)                     # "NVIDIA Corporation"
        base = _strip_suffixes(name)          # "NVIDIA"
        if base:
            aliases.add(base)
            aliases.add(base.replace(" ", ""))  # "MercadoLibre"

    # Filter empty and dedupe
    aliases = {a for a in aliases if a and isinstance(a, str)}

    # (Optional) You can still manually add special nicknames here if needed
    # e.g. if ticker == "META": aliases.add("Facebook")

    return sorted(aliases)
