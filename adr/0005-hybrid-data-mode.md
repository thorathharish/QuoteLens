# ADR-0005: Hybrid live and cached distributor data with an explicit mode
- **Status:** Accepted
- **Context:** Live APIs (Nexar, DigiKey, Mouser) give credibility but bring rate limits, key approval and latency risk during a live demo.
- **Decision:** `DATA_MODE = live_first | cache_first | demo_snapshot`. Provider chain with timeouts and circuit breakers; live results are written through to BigQuery `catalog.offers_cache`. The demo runs `cache_first` with a pre-warmed cache. Every offer carries `mode` and `fetched_at`, shown in the UI.
- **Consequences:** The demo cannot be broken by an outage at a distributor. Data freshness is always disclosed, and snapshot data is never presented as live.
