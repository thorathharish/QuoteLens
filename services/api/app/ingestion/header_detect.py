"""Find the sheet and header row of a BOM, including below a title block."""

from dataclasses import dataclass

from rapidfuzz import fuzz

from app.domain.errors import ValidationFailedError
from app.ingestion.aliases import ALIAS_TO_FIELD, normalize_header
from app.ingestion.readers import Grid, Workbook

SCAN_ROWS = 25
FUZZY_THRESHOLD = 90
MIN_MATCHED_COLUMNS = 2


@dataclass(frozen=True, slots=True)
class HeaderLocation:
    sheet: str
    row_index: int  # 0-based index into the grid
    score: int

    @property
    def row_number(self) -> int:
        """1-based, as the user sees it in a spreadsheet."""
        return self.row_index + 1


def alias_score(header: str | None) -> int:
    """100 for an exact alias, the fuzzy ratio when it is ≥ threshold, else 0."""
    if not header:
        return 0
    key = normalize_header(header)
    if not key:
        return 0
    if key in ALIAS_TO_FIELD:
        return 100
    best = max((fuzz.ratio(key, alias) for alias in ALIAS_TO_FIELD), default=0)
    return int(best) if best >= FUZZY_THRESHOLD else 0


def _row_score(row: list[str | None]) -> int:
    return sum(1 for cell in row if alias_score(cell))


def detect_header(workbook: Workbook) -> HeaderLocation:
    best: HeaderLocation | None = None
    for sheet, grid in workbook.sheets.items():
        candidate = _best_row(sheet, grid)
        if candidate and (best is None or candidate.score > best.score):
            best = candidate
    if best is None or best.score < MIN_MATCHED_COLUMNS:
        raise ValidationFailedError(
            "Could not find a header row. Expected columns such as MPN, Manufacturer and Qty "
            f"within the first {SCAN_ROWS} rows."
        )
    return best


def _best_row(sheet: str, grid: Grid) -> HeaderLocation | None:
    best: HeaderLocation | None = None
    for index, row in enumerate(grid[:SCAN_ROWS]):
        score = _row_score(row)
        if score and (best is None or score > best.score):
            best = HeaderLocation(sheet=sheet, row_index=index, score=score)
    return best
