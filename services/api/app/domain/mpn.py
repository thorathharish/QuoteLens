"""Manufacturer part number (MPN) normalization: the join key between BOMs and catalogs.

Deliberately conservative: only case and invisible/whitespace differences are removed.
Punctuation is significant in real MPNs (e.g. Nexperia's "BAT54S,215", Microchip's
"MCP2561-E/SN"), so it is kept; looser matching belongs to the sourcing matcher, which
reports its confidence instead of silently rewriting the key.
"""

import re
import unicodedata

_INVISIBLE = re.compile(r"[\s​‌‍⁠﻿]+")


def normalize_mpn(raw: str | None) -> str | None:
    """Return the canonical MPN key, or None when nothing meaningful remains."""
    if raw is None:
        return None
    text = unicodedata.normalize("NFKC", raw)
    text = _INVISIBLE.sub("", text).upper()
    return text or None
