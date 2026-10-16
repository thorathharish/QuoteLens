# Demo runbook

A 6-minute walkthrough of the full journey, with the checks to do beforehand and the fallbacks if something misbehaves. Everything here works on the deployed URL and on a laptop.

## Before the demo (10 minutes)
1. `PROJECT_ID=<id> ./infra/demo-mode.sh on`: keeps web and api warm (no cold starts). **Turn it off afterwards.**
2. Open the web URL and choose **Open the demo project**. Wait for the analysis banner to finish, which takes a few seconds.
3. Check that the Overview says **3 blockers**, with totals for 100, 1,000 and 5,000 boards.
4. Copilot (if Gemini is configured, #8): ask *"Which parts block this quote and why?"*. Expect a cited answer within about 5 s.
5. Keep a second, untouched demo project open in another tab as a spare.
6. Check spend in Billing → Reports (see `infra/cost-check.md`).

## The walkthrough
| Time | Screen | What to do | What to say |
|---|---|---|---|
| 0:00 | Landing | Point at the explained BOM line, then choose **Open the demo project** | Every number in QuoteLens says where it came from: actual, calculated, assumed, unavailable or recommended. |
| 0:40 | Overview | Read the banner: *3 blockers stand between this BOM and a quote*; cost per build quantity | The totals exclude the lines we cannot price yet, and say so. |
| 1:10 | BOM | Filter **Missing part number**, open **F1**, enter `0451005.MRL` with a reason | A typo or a missing MPN is a blocker, not a silent zero. The fix is audited. |
| 1:50 | BOM | Open **J2** (quantity "TBD"), correct the quantity to **1** | The new value is labelled *actual* and cites who entered it. |
| 2:20 | Risks | Open the **obsolete hall sensor A1101ELHLT-T**; show the reason and **Show evidence** | Not a score: the reason, the numbers and the source records. Broker stock is excluded as a traceability risk. |
| 3:00 | Line, then Alternatives | **Find alternates**: A1120ELHLX-T is a **drop-in**; INA240A2 is **not suitable** because of its gain. **Approve** with a note | Nothing is swapped without a person's approval. Approving re-prices the line and removes the blocker. |
| 3:50 | Cost impact | Switch to 1,000 boards and open **Show steps** on SRP1265A-220M (MOQ 500) | MOQ, scrap and excess are calculated, and every step is shown. Cheaper order quantities are suggested. |
| 4:30 | Copilot | Ask *"Which parts threaten delivery by the target date?"* | Answers only from project data, with sources; numbers are verified before they are shown. |
| 5:20 | Quote | **Create quote version**, finalize with a note, **Download Excel** | Finalizing is blocked until blockers are cleared. The workbook keeps the provenance. |

## Fallbacks
| Problem | Do this |
|---|---|
| The analysis banner never finishes | Wait 60 s (cold worker); if still stuck, open the spare project. Root fix: check Pub/Sub delivery (#6). |
| The copilot returns *"needs Gemini"* or errors | Say the copilot needs Vertex AI. Show the evidence dialog and calculation steps instead, which carry the same information. |
| A distributor is slow | Demo projects use the snapshot catalog and never call live APIs. |
| Credit is running low | Set `LLM_ENABLED=false` on api and worker (`gcloud run services update … --update-env-vars LLM_ENABLED=false`). Everything except the copilot keeps working. |
| The page is slow on first load | Run `demo-mode.sh on`. Cloud Run was scaled to zero. |

## After the demo
`PROJECT_ID=<id> ./infra/demo-mode.sh off`. After judging, run `./infra/teardown.sh` (see `infra/cost-check.md`).
