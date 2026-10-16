# Competitor Analysis & Differentiation

> QuoteLens · AI Builder Cup 2026 · Manufacturing track. Part of the design package; see [README](README.md).

## 5. Competitor analysis and differentiation

*Based on publicly known positioning. I'll verify the specifics by web research before anything goes in the pitch deck.*

| Product | Category | Strengths | Gaps vs. our scope |
|---|---|---|---|
| **Octopart / Nexar (Altium)** | Part search and BOM tool | Huge multi-distributor pricing and stock aggregation, lifecycle data, API | Not an EMS quotation workflow. No manufacturing-impact math, explained risks or grounded copilot. |
| **SiliconExpert (Arrow)** | Component risk data | Deep lifecycle, compliance and cross-reference data; BOM risk scoring | Enterprise and data-centric. Gives scores rather than explained decisions. No quote building. |
| **Z2Data** | Supply-chain risk intelligence | Part and supplier risk, sub-tier visibility | Risk analytics only. Not focused on quotes or MOQ cost. |
| **Accuris (ex-IHS Parts Intelligence)** | Component data and BOM intelligence | Lifecycle, alternates, obsolescence forecasting | Heavy enterprise tooling. No conversational investigation. |
| **CalcuQuote** | EMS RFQ / quoting | End-to-end EMS quoting, supplier API pricing, BOM scrub | Closest competitor. Less emphasis on per-number provenance, natural-language investigation or LLM-explained risk. |
| **Luminovo** | EMS quoting and sourcing | Modern UX, PCBA quoting, sourcing automation | Direct competitor. Our edge is open evidence trails, a reviewable alternates workflow and a cited copilot. |
| **Cofactr** | Supply-chain platform and services | Sourcing plus logistics services | Service-led, not an explainable analysis copilot |
| **Distributor BOM tools (DigiKey, Mouser, Arrow)** | Single-vendor BOM carts | Free and real-time | Biased to one vendor. No cross-source comparison or risk narrative. |
| **Generic LLM + spreadsheet (ChatGPT/Gemini)** | Ad-hoc analysis | Flexible | No live data, invents prices and lifecycle, no audit trail |

**Our differentiation (the pitch)**
1. **Evidence on every number.** Actual, Calculated, Assumed, Unavailable and Recommended are always visible, with a click-through source and calculation trace.
2. **Explained risk, not just a score.** Rule, metrics, evidence and a suggested action, with a resolve/waive audit trail.
3. **Manufacturing-impact math tied to the quote.** MOQ, scrap, excess, shortage and price-break jumps per volume, with per-line contribution.
4. **A person approves alternates.** Parameter diff, fit class and explanation. Nothing is auto-swapped.
5. **Grounded copilot.** Tool-calling over project data, mandatory citations, and a numeric grounding check against hallucinated numbers.
6. **Vendor-neutral, GCP-native and lightweight.** Hybrid live and cached data with an honest freshness label.
