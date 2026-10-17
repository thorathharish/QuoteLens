# Daily cost check (free-credit budget)

Takes about 2 minutes. Do it once a day and after each milestone. Background is in the [free-credit cost plan](../docs/implementation-plan.md#free-credit-cost-plan).

## 1. Credit and spend
- **Billing → Overview:** remaining credit and days left in the trial.
- **Billing → Reports:** group by **SKU** for the last 7 days. With the default `LLM_PROVIDER=openrouter`, expect everything at or near 0 (Gemini is billed by OpenRouter, not GCP; check the balance at openrouter.ai/credits). With `LLM_PROVIDER=vertex`, expect spend to be almost all **Vertex AI (Gemini)**.
- **Billing → Budgets & alerts:** `quotelens-hackathon` exists. Budgets only alert; they do not stop spend.

## 2. Usage against the Always Free tier
| Where | Check | Free limit |
|---|---|---|
| Firestore → Usage | Reads, writes, deletes today | 50k / 20k / 20k per day |
| Cloud Run → each service → Metrics | Instance count goes back to 0 when idle (unless demo mode is on) | 180k vCPU-s, 360k GB-s per month |
| BigQuery → Administration → Monitoring | Bytes processed | 1 TiB per month |
| Cloud Storage → bucket | Size; `exports/` older than 7 days auto-deleted | 5 GB-months (us-central1) |
| Artifact Registry → `quotelens` | At most 3 images per service | 0.5 GB |
| Cloud Build → History | Only builds from deploys | 2,500 build-min per month |

## 3. If spend is climbing
1. Check that `min-instances` is 0: `gcloud run services describe quotelens-api --region us-central1 --format='value(spec.template.metadata.annotations)'`. Run `infra/demo-mode.sh off` if it isn't.
2. Gemini: point the Pro model at Flash (`OPENROUTER_PRO_MODEL=google/gemini-2.5-flash`, or `GEMINI_PRO_MODEL` on Vertex) and lower `LLM_MAX_OUTPUT_TOKENS`.
3. Emergency: set `LLM_ENABLED=false` on api and worker. Everything keeps working with template explanations.
4. After judging: run `infra/teardown.sh`.
