# ADR-0004: Normalized offer records
- **Status:** Accepted
- **Context:** The reference implementation stored about 30 per-distributor columns per BOM row, which made adding sources and comparing them painful.
- **Decision:** Store one `Offer` document per (line, distributor, SKU), with price breaks, stock, MOQ, multiple, lead time, lifecycle, an evidence ref, and mode/fetched_at.
- **Consequences:** Any number of sources, generic comparison and scoring, and clean evidence links.
