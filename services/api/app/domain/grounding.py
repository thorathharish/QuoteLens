"""Numeric grounding: an LLM-written text may only state numbers present in its sources.

Used wherever Gemini rephrases or summarizes data (alternate explanations, risk narration,
copilot answers). If a number cannot be traced to the source text, the caller falls back
to deterministic text or flags the answer as unverified.

Not counted as claims: list enumerators ("1."), digits inside identifiers and citation
markers ([E:ev_off_7f3a], A1120ELHLX-T). Percentages are grounded when they equal a source
fraction ×100 (0.897 → 89.7%).
"""

import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation

_NUMBER = re.compile(r"(?<![A-Za-z0-9_\-:.])\d[\d,]*(?:\.\d+)?")
_CITATION = re.compile(r"\[E:[^\]]*\]")
_ENUMERATOR = re.compile(r"(?m)^\s*\d+[.)]\s")


def _normalize(token: str) -> str:
    value = token.replace(",", "")
    if "." in value:
        value = value.rstrip("0").rstrip(".")
    return value.lstrip("0") or "0"


def _claims(text: str) -> str:
    return _ENUMERATOR.sub(" ", _CITATION.sub(" ", text))


def numbers_in(text: str) -> set[str]:
    """Standalone numbers stated in the text (see module docstring for exclusions)."""
    return {_normalize(token) for token in _NUMBER.findall(_claims(text))}


def _percent_forms(value: str) -> set[str]:
    try:
        number = Decimal(value)
    except InvalidOperation:
        return set()
    if not 0 < number <= 1 or "." not in value:
        return set()
    pct = number * 100
    return {_normalize(str(pct.quantize(Decimal(q)))) for q in ("1", "0.1", "0.01")}


def ungrounded_numbers(text: str, sources: Iterable[str]) -> set[str]:
    allowed: set[str] = set()
    for source in sources:
        found = {_normalize(d) for d in re.findall(r"\d[\d,]*(?:\.\d+)?", source)}
        allowed |= found
        for value in list(found):
            allowed |= _percent_forms(value)
    return numbers_in(text) - allowed


def is_grounded(text: str, sources: Iterable[str]) -> bool:
    return not ungrounded_numbers(text, sources)
