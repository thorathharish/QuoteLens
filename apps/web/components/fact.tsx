"use client";

import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { createContext, useContext, useState } from "react";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { dateTime, money, percent, quantity, sentence } from "@/lib/format";
import { Dialog, ErrorNote, Spinner } from "./ui";

export type Provenance = Schemas["Provenance"];
type Fact = { value?: unknown; unit?: string | null; provenance: Provenance; evidence_ids?: string[]; formula?: string | null; note?: string | null };

/**
 * Provenance marks: the signature element. Each has its own shape, so meaning never depends
 * on color alone.
 */
const MARKS: Record<Provenance, { glyph: string; label: string; className: string; explain: string }> = {
  ACTUAL: { glyph: "■", label: "Actual", className: "text-ink", explain: "Taken directly from a source" },
  CALCULATED: { glyph: "ƒ", label: "Calculated", className: "text-mask italic font-semibold", explain: "Computed from other values" },
  ASSUMED: {
    glyph: "◌",
    label: "Assumed",
    className: "text-medium",
    explain: "A default or a value someone entered",
  },
  UNAVAILABLE: { glyph: "—", label: "Unavailable", className: "text-ink-3", explain: "No source has this value" },
  RECOMMENDED: { glyph: "◆", label: "Recommended", className: "text-gold", explain: "A suggestion that needs a person's approval" },
};

export function ProvenanceMark({ provenance, withLabel = false }: { provenance: Provenance; withLabel?: boolean }) {
  const mark = MARKS[provenance];
  return (
    <span className={clsx("inline-flex items-center gap-1 text-xs", mark.className)} title={`${mark.label}: ${mark.explain}`}>
      <span aria-hidden className="w-3 text-center">
        {mark.glyph}
      </span>
      {withLabel ? <span>{mark.label}</span> : <span className="sr-only">{mark.label}</span>}
    </span>
  );
}

export function ProvenanceLegend() {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1">
      {(Object.keys(MARKS) as Provenance[]).map((p) => (
        <span key={p} className="text-xs text-ink-2" title={MARKS[p].explain}>
          <ProvenanceMark provenance={p} withLabel />
        </span>
      ))}
    </div>
  );
}

type Kind = "money" | "qty" | "pct" | "raw";

function display(fact: Fact, kind: Kind, currency: string): string {
  if (fact.provenance === "UNAVAILABLE" || fact.value === null || fact.value === undefined) return "—";
  const value = fact.value as string | number;
  switch (kind) {
    case "money":
      return money(value, fact.unit ?? currency);
    case "qty":
      return quantity(value);
    case "pct":
      return percent(value, 1);
    default:
      return String(value);
  }
}

/** A value with its provenance mark. Click to see the formula, note and evidence. */
export function FactValue({
  fact,
  kind = "raw",
  currency = "USD",
  className,
}: {
  fact: Fact | null | undefined;
  kind?: Kind;
  currency?: string;
  className?: string;
}) {
  const evidence = useEvidence();
  if (!fact) return <span className="text-ink-3">—</span>;
  const unavailable = fact.provenance === "UNAVAILABLE";
  const detail = [fact.formula, fact.note].filter(Boolean).join("\n");
  return (
    <button
      type="button"
      onClick={() => evidence.open(fact)}
      className={clsx(
        "group inline-flex items-baseline gap-1.5 rounded-sm px-0.5 text-left tabular hover:bg-mask-tint",
        unavailable && "hatch px-1",
        className,
      )}
      title={detail || MARKS[fact.provenance].explain}
    >
      <span className={clsx(unavailable && "text-ink-3")}>{display(fact, kind, currency)}</span>
      <ProvenanceMark provenance={fact.provenance} />
    </button>
  );
}

// ── Evidence dialog ─────────────────────────────────────────

const EvidenceContext = createContext<{ open: (fact: Fact | { evidence_ids: string[]; provenance?: Provenance }) => void }>({
  open: () => undefined,
});
export const useEvidence = () => useContext(EvidenceContext);

export function EvidenceProvider({ projectId, children }: { projectId: string; children: React.ReactNode }) {
  const [subject, setSubject] = useState<(Partial<Fact> & { evidence_ids?: string[] }) | null>(null);
  return (
    <EvidenceContext.Provider value={{ open: setSubject }}>
      {children}
      <Dialog open={subject !== null} onClose={() => setSubject(null)} title="Where this value comes from" wide>
        {subject && <EvidencePanel projectId={projectId} subject={subject} />}
      </Dialog>
    </EvidenceContext.Provider>
  );
}

function EvidencePanel({
  projectId,
  subject,
}: {
  projectId: string;
  subject: Partial<Fact> & { evidence_ids?: string[] };
}) {
  const ids = subject.evidence_ids ?? [];
  return (
    <div className="flex flex-col gap-4">
      {subject.provenance && (
        <div className="flex flex-col gap-1">
          <ProvenanceMark provenance={subject.provenance} withLabel />
          {subject.formula && (
            <p>
              <span className="text-ink-3">Formula </span>
              <span className="tabular">{subject.formula}</span>
            </p>
          )}
          {subject.note && <p className="text-ink-2">{subject.note}</p>}
        </div>
      )}
      {ids.length === 0 ? (
        <p className="text-sm text-ink-3">No source record is attached to this value.</p>
      ) : (
        ids.map((id) => <EvidenceRecord key={id} projectId={projectId} id={id} />)
      )}
    </div>
  );
}

export function EvidenceRecord({ projectId, id }: { projectId: string; id: string }) {
  const query = useQuery({
    queryKey: ["evidence", projectId, id],
    queryFn: () => unwrap(api.GET("/api/v1/projects/{pid}/evidence/{eid}", { params: { path: { pid: projectId, eid: id } } })),
    staleTime: Infinity,
  });
  if (query.isPending) return <Spinner label="Loading source" />;
  if (query.error) return <ErrorNote error={query.error} />;
  const ev = query.data;
  const excerpt = Object.entries(ev.payload_excerpt ?? {});
  return (
    <article className="rounded-md bg-laminate">
      <header className="flex flex-wrap items-center justify-between gap-2 rounded-t-md bg-laminate-2 px-3 py-2">
        <span className="font-semibold">{ev.source_name}</span>
        <span className="flex flex-wrap gap-x-3 text-xs text-ink-2">
          <span>{sentence(ev.kind)}</span>
          {ev.mode && <span>{ev.mode === "DEMO_SNAPSHOT" ? "Demo snapshot (synthetic data)" : sentence(ev.mode)}</span>}
          {ev.fetched_at && <span>Fetched {dateTime(ev.fetched_at)}</span>}
        </span>
      </header>
      <dl className="grid grid-cols-[minmax(7rem,max-content)_1fr] gap-x-4 gap-y-1 px-3 py-2 text-sm">
        {ev.source_ref && (
          <>
            <dt className="text-ink-3">Reference</dt>
            <dd className="code break-all">{ev.source_ref}</dd>
          </>
        )}
        {excerpt.map(([key, value]) => (
          <div key={key} className="contents">
            <dt className="text-ink-3">{sentence(key)}</dt>
            <dd className="break-words tabular">{formatExcerpt(value)}</dd>
          </div>
        ))}
      </dl>
    </article>
  );
}

function formatExcerpt(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (Array.isArray(value)) {
    return value
      .map((item) =>
        typeof item === "object" && item && "qty" in item && "price" in item
          ? `${quantity(String((item as { qty: unknown }).qty))} @ ${String((item as { price: unknown }).price)}`
          : JSON.stringify(item),
      )
      .join(", ");
  }
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
