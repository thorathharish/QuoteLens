"""Match BOM lines to catalog components.

Only an exact normalized MPN is a match. Near misses (typos, a missing packaging suffix)
are offered as `candidates` on a NOT_FOUND result for the user to confirm: silently
substituting a "similar" part number could quote the wrong component.
"""

from app.catalog.rows import CatalogComponent
from app.domain.enums import MatchStatus
from app.domain.models import MatchResult
from app.ingestion.normalize import normalize_manufacturer

MANUFACTURER_MISMATCH_CONFIDENCE = 0.9


def match_line(
    mpn: str | None,
    manufacturer: str | None,
    components: dict[str, CatalogComponent],
    candidates: list[str],
) -> MatchResult:
    if mpn is None:
        return MatchResult(status=MatchStatus.PENDING)
    component = components.get(mpn)
    if component is None:
        return MatchResult(status=MatchStatus.NOT_FOUND, candidates=candidates)
    same_maker = (
        manufacturer is None or normalize_manufacturer(component.manufacturer) == manufacturer
    )
    return MatchResult(
        status=MatchStatus.MATCHED,
        component_id=component.mpn_norm,
        confidence=1.0 if same_maker else MANUFACTURER_MISMATCH_CONFIDENCE,
    )
