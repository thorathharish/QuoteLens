"""Numeric grounding: an LLM-written text may only state numbers present in its sources.

Used wherever Gemini rephrases or summarizes data (alternate explanations, risk narration,
copilot answers). If a number cannot be traced to the source text, the caller falls back
to deterministic text or flags the answer as unverified.
"""

import re
from collections.abc import Iterable

_NUMBER = re.compile(r"(?<![A-Za-z0-9])\d[\d,]*(?:\.\d+)?")


def _normalize(token: str) -> str:
    value = token.replace(",", "")
    if "." in value:
        value = value.rstrip("0").rstrip(".")
    return value.lstrip("0") or "0"


def numbers_in(text: str) -> set[str]:
    """Standalone numbers (not digits inside part numbers such as 'A1120ELHLX-T')."""
    return {_normalize(token) for token in _NUMBER.findall(text)}


def ungrounded_numbers(text: str, sources: Iterable[str]) -> set[str]:
    allowed: set[str] = set()
    for source in sources:
        allowed |= numbers_in(source)
        # Digits embedded in identifiers (MPNs, SKUs) count as present too.
        allowed |= {_normalize(d) for d in re.findall(r"\d+(?:\.\d+)?", source)}
    return numbers_in(text) - allowed


def is_grounded(text: str, sources: Iterable[str]) -> bool:
    return not ungrounded_numbers(text, sources)
