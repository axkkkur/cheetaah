from __future__ import annotations

import re
import unicodedata


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.casefold()
    kept: list[str] = []
    for ch in s:
        cat = unicodedata.category(ch)
        if cat.startswith(("L", "N", "M")):
            kept.append(ch)
        elif ch.isspace():
            kept.append(" ")
    return re.sub(r"\s+", " ", "".join(kept)).strip()


def quote_in(quote: str, source: str) -> bool:
    nq = _norm(quote)
    if len(nq) < 8:
        return False
    return nq in _norm(source)
