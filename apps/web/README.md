# QuoteLens web

Next.js (App Router, TypeScript strict, Tailwind 4) frontend for QuoteLens.

```bash
pnpm install
cp .env.example .env.local      # points the /api/v1 proxy at the API (default 127.0.0.1:8080)
pnpm dev                        # http://localhost:3000 (run the API too: services/api)
pnpm lint && pnpm typecheck && pnpm test && pnpm build
pnpm gen:api                    # regenerate lib/api/schema.d.ts from the API's OpenAPI
```

## Structure
| Path | What |
|---|---|
| `app/page.tsx` | Landing: open the demo project, start a new quote, recent projects |
| `app/projects/[id]/…` | Workspace: overview, BOM, risks, cost impact, alternatives, quote, activity, upload/mapping |
| `app/api/v1/[...path]/route.ts` | Proxy to the API (streams SSE and downloads; adds a Cloud Run ID token when `API_AUDIENCE` is set) |
| `components/fact.tsx` | `FactValue`, provenance marks, evidence dialog: every number shows where it came from |
| `components/copilot.tsx` | Copilot drawer (SSE; answers appear only after the server's grounding check) |
| `lib/api/` | Typed client generated from OpenAPI (`openapi-fetch`) and TanStack Query hooks |

## Design
The palette comes from a printed circuit board: laminate page, solder-mask ink and green, ENIG gold
reserved for *recommended* values. Atkinson Hyperlegible for the UI; IBM Plex Mono only for part
numbers and SKUs. Provenance marks (■ actual, ƒ calculated, ◌ assumed, — unavailable,
◆ recommended) use distinct shapes, so meaning never depends on color alone.
