# ADR-0002: Deterministic core, LLM at the edges
- **Status:** Accepted
- **Context:** Quotes and risk calls must be explainable and reproducible. LLMs can invent numbers.
- **Decision:** Pricing, offer selection, risk detection, impact maths and readiness are pure, unit-tested Python. Gemini is used only for header mapping, explanation narration (validated against rule metrics), alternate-suitability explanations and the copilot (tool-grounded).
- **Consequences:** Same inputs give the same numbers. If an LLM call fails, wording falls back to a template; the numbers stay correct. LLM output never writes financial values.
