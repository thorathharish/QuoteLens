# User Flows

> QuoteLens · AI Builder Cup 2026 · Manufacturing track. Part of the design package; see [README](README.md).

## 4. User flows

### Personas
| Persona | Goal | Primary screens |
|---|---|---|
| **P0 First-time viewer / judge** | See the value in under 3 minutes | Landing → Guided demo |
| **P1 Sourcing / procurement specialist** | Best compliant source, availability, cost | Sourcing, Risks, Alternatives, Copilot |
| **P2 Quote / cost engineer (EMS)** | An accurate, defensible quote per volume | Upload, Map, BOM, Impact, Quote |
| **P3 Design / NPI engineer** | Approve or reject alternates technically | Alternatives, Copilot |
| **P4 Sales / program manager** | Know quote readiness and the risks to tell the customer | Overview, Quote, Copilot |

### P0 Generalized first-time viewer (guided demo)
```mermaid
flowchart LR
  A[Landing: problem + 'Run guided demo'] --> B[Seed sample BOM<br/>motor-controller, 60 lines]
  B --> C[Mapping preview<br/>tour: AI mapped 9/10 columns, confirm]
  C --> D[Analysis progress<br/>live/cache chips]
  D --> E[Overview: readiness 62%<br/>3 blockers, 18% spend at risk]
  E --> F[Open blocker: EOL part<br/>Why + evidence]
  F --> G[Alternatives: drop-in found<br/>approve]
  G --> H[Impact: MOQ excess<br/>price-break jump saves X]
  H --> I[Copilot: 'Which parts threaten a<br/>6-week delivery?' → cited answer]
  I --> J[Quote: readiness 100%<br/>finalize + export]
```

### P2 Quote engineer (core path)
```mermaid
flowchart TD
  S[New project: name, customer, volumes 100/1k/5k, target date] --> U[Upload XLSX/CSV]
  U --> M{Mapping confidence OK?}
  M -- edit --> M2[Fix column mapping] --> V
  M -- yes --> V[Validation results]
  V --> E{Data issues?}
  E -- yes --> FIX[Inline fix with reason<br/>audit logged] --> AN
  E -- no --> AN[Run analysis]
  AN --> IMP[Impact tab: set scrap/markup assumptions<br/>review per-line trace]
  IMP --> RISK[Clear or waive blockers]
  RISK --> Q[Create quote version] --> R{Readiness = 100%?}
  R -- no --> RISK
  R -- yes --> FIN[Finalize → export XLSX]
```

### P1 Sourcing specialist
```mermaid
flowchart TD
  A[Risks tab filtered: SUPPLY + LIFECYCLE] --> B[Line detail: offers compare<br/>stock, MOQ, lead, price breaks, source age]
  B --> C{Accept recommended offer?}
  C -- override --> C2[Select other offer + reason]
  C -- yes --> D
  C2 --> D{Part risky? EOL / single-source / long lead}
  D -- yes --> E[Search alternatives] --> F[Send to engineering review]
  D -- no --> G[Mark risk resolved]
  A --> H[Copilot: 'compare DigiKey vs Mouser for U7 at 5k']
```

### P3 Design / NPI engineer
```mermaid
flowchart LR
  A[Alternatives queue: PROPOSED] --> B[Param diff table<br/>critical mismatches highlighted]
  B --> C[Ask copilot: 'is the alt's<br/>temp range OK for automotive?']
  C --> D{Decision}
  D -- approve + note --> E[Line versioned, re-priced, risks re-run]
  D -- reject + reason --> F[Kept as rejected with rationale]
```

### P4 Sales / program manager
```mermaid
flowchart LR
  A[Overview: readiness, totals by volume, top risks] --> B[Copilot: 'summarize risks I must tell the customer']
  B --> C[Cited summary] --> D[Quote tab: finalized version + assumptions list] --> E[Export]
```
