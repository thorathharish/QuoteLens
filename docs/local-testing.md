# Local testing with the real APIs

How to run QuoteLens on a laptop against the real distributor APIs (DigiKey, Mouser, element14) and a real LLM through OpenRouter, without GCP. Storage, jobs and the catalog stay local: the in-memory store, inline jobs and the seed catalog. Those parts are tested on GCP later (issues #3–#7).

| Part | Locally | Deployed |
|---|---|---|
| Distributor prices | Real APIs | Real APIs (keys in Secret Manager) |
| LLM (column mapping, copilot, alternative explanations) | OpenRouter, Gemini 2.5 models | Gemini on Vertex AI |
| Database | In memory (lost on restart) | Firestore |
| Analysis jobs | Run inline in the api | Pub/Sub → worker |
| Catalog and cache | Seed files in `data/catalog_seed` | BigQuery |

## 1. Keys in `services/api/.env`
The file is git-ignored. The values below are placeholders; never commit real ones.

```ini
# Distributors (already set)
DIGIKEY_CLIENT_ID=...
DIGIKEY_CLIENT_SECRET=...
MOUSER_API_KEY=...
ELEMENT14_API_KEY=...
ELEMENT14_STORE=in.element14.com
LIVE_DISTRIBUTORS_ENABLED=true

# LLM through OpenRouter (key from https://openrouter.ai/keys)
LLM_ENABLED=true
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_FLASH_MODEL=google/gemini-2.5-flash
OPENROUTER_PRO_MODEL=google/gemini-2.5-pro

# Leave these local
STORAGE_BACKEND=memory
JOB_BACKEND=inline
GCP_PROJECT=
```

Keep the Google models: the hackathon asks for Google AI models. OpenRouter charges per token from your OpenRouter balance (a few cents for a full test run), so add a small credit or set a spending limit on the key.

## 2. Check each API on its own (2 minutes)
From `services/api`:

```bash
uv sync
uv run python scripts/check_distributors.py RC0603FR-0710KL   # offers from each distributor
uv run python scripts/check_llm.py                            # expect "4/4 checks passed"
```

`check_llm.py` makes the same three kinds of calls QuoteLens makes: a plain answer, structured column mapping and a tool call. If one fails, its error is printed. An unknown model id or a missing credit balance are the usual causes.

## 3. Start the app
Two terminals:

```bash
# Terminal 1: api
cd services/api
uv run uvicorn app.main_api:app --port 8080        # http://127.0.0.1:8080/healthz

# Terminal 2: web
cd apps/web
pnpm install
pnpm dev                                           # http://localhost:3000
```

The api logs say which distributors and which LLM provider are active. Restarting the api clears all projects (memory store).

## 4. What to try
| # | Area | Steps | Expect |
|---|---|---|---|
| 1 | Live distributor prices | On the start page, **Start a new quote**. Set **Distributor prices** to *Live lookup for every part* and upload `data/samples/motor_controller.xlsx` | Offers marked *live* from DigiKey, Mouser and element14, with the time each was fetched. DigiKey stock shows as *unknown*. |
| 2 | INR offers | Open **Cost impact** and enter an INR per USD rate | Mouser and element14 offers priced in INR (India stores) are converted and compared, with the rate labelled *assumed*. |
| 3 | LLM column mapping | New project, upload `data/samples/llm_check/german_headers.csv` | The German headers (*Bestückungsorte*, *Hersteller*, *Bezeichnung*, *Bemerkung*) are suggested by Gemini with a confidence and reason; *Pos.* is left unmapped. You confirm the mapping. |
| 4 | Copilot | Open the copilot drawer and ask *"Which parts block this quote and why?"* | A streamed answer with source chips. Every number is checked against the project data before it is shown. |
| 5 | Alternatives | In a demo project (start page → **Open the demo project**), open the obsolete hall sensor **A1101ELHLT-T**, choose **Find alternates** | The drop-in alternate with a written explanation. Without an LLM the explanation falls back to a template. |
| 6 | Full journey | Follow [the demo runbook](demo-runbook.md) on `http://localhost:3000` | Ends with a finalized quote and an Excel download. |

Demo projects always use the snapshot catalog, so they never call the distributor APIs. Use a new project (step 1) to test live data.

## 5. Optional: the copilot evaluation set
With the LLM configured (the script runs its own in-process api; nothing else needs to be running):

```bash
cd services/api && uv run python scripts/run_copilot_eval.py
```

It asks the 10 questions in `tests/evals/copilot_questions.yaml` and reports how many answers are grounded and cited (target 8/10). Record the result in issue #18.

## Troubleshooting
| Problem | Do this |
|---|---|
| Copilot says it *needs an LLM* | `LLM_PROVIDER=openrouter` and `OPENROUTER_API_KEY` are missing or blank. Restart the api after editing `.env`. |
| `check_llm.py` reports 401 or 402 | The key is wrong (401), or there is no OpenRouter credit (402). |
| A distributor shows an error banner | Run `check_distributors.py` for that part. The other distributors and the catalog still answer. |
| The web page cannot reach the api | The api must listen on `127.0.0.1:8080`; Docker or WSL sometimes hold `[::1]:8080`. |
| The machine runs out of memory | Stop other dev servers. `pnpm dev` uses about 1 GB. |
