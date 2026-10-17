"use client";

import { useMutation } from "@tanstack/react-query";
import clsx from "clsx";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { AskButton } from "@/components/copilot";
import { FactValue, useEvidence } from "@/components/fact";
import { Button, Dialog, Empty, ErrorNote, PageSkeleton, Tag, TextArea } from "@/components/ui";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useAlternatives, useInvalidateProject, useLines, useProject } from "@/lib/api/hooks";
import { quantity, sentence } from "@/lib/format";

type Alternative = Schemas["Alternative"];

const FIT: Record<string, { label: string; tone: "mask" | "gold" | "neutral"; explain: string }> = {
  DROP_IN: { label: "Drop-in", tone: "mask", explain: "Same footprint, all critical parameters match" },
  FUNCTIONAL: { label: "Needs review", tone: "gold", explain: "Works electrically but needs a design check" },
  NOT_SUITABLE: { label: "Not suitable", tone: "neutral", explain: "A critical parameter does not match" },
};

export default function AlternativesPage() {
  return (
    <Suspense>
      <AlternativesView />
    </Suspense>
  );
}

function AlternativesView() {
  const { id } = useParams<{ id: string }>();
  const focus = useSearchParams().get("line");
  const alternatives = useAlternatives(id);
  const lines = useLines(id);
  const project = useProject(id);
  const [deciding, setDeciding] = useState<{ alt: Alternative; approve: boolean } | null>(null);

  if (alternatives.isPending) return <PageSkeleton />;
  if (alternatives.error) return <ErrorNote error={alternatives.error} />;
  const byLine = new Map<string, Alternative[]>();
  for (const alt of alternatives.data.items) byLine.set(alt.line_id, [...(byLine.get(alt.line_id) ?? []), alt]);
  const lineInfo = new Map((lines.data?.items ?? []).map((l) => [l.id, l]));
  const order = [...byLine.keys()].sort((a) => (a === focus ? -1 : 0));

  if (order.length === 0) {
    return (
      <Empty title="No alternates investigated yet">
        Open a line on the BOM or Risks tab and choose <span className="font-semibold">Find alternates</span>. Nothing is ever
        swapped until someone approves it.
      </Empty>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      {order.map((lineId) => {
        const line = lineInfo.get(lineId);
        return (
          <section key={lineId} className={clsx(lineId === focus && "rounded-md ring-2 ring-mask/40")}>
            <h2 className="mb-3 text-lg font-semibold">
              Alternates for <span className="code">{line?.substituted_from ?? line?.mpn ?? lineId}</span>
              {line?.substituted_from && (
                <span className="ml-3 text-sm font-normal text-mask">
                  now using <span className="code">{line.mpn}</span>
                </span>
              )}
            </h2>
            <div className="grid gap-4 xl:grid-cols-2">
              {byLine.get(lineId)?.map((alt) => (
                <AlternativeCard
                  key={alt.id}
                  alt={alt}
                  currency={project.data?.currency ?? "USD"}
                  onDecide={(approve) => setDeciding({ alt, approve })}
                />
              ))}
            </div>
          </section>
        );
      })}
      <DecisionDialog projectId={id} deciding={deciding} onClose={() => setDeciding(null)} />
    </div>
  );
}

function AlternativeCard({
  alt,
  currency,
  onDecide,
}: {
  alt: Alternative;
  currency: string;
  onDecide: (approve: boolean) => void;
}) {
  const evidence = useEvidence();
  const fit = FIT[alt.fit_class] ?? FIT.NOT_SUITABLE!;
  const summary = alt.offers_summary as Record<string, string | number | null>;
  return (
    <article className="surface rounded-[var(--radius-panel)]">
      <header className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5">
        <div>
          <span className="code font-semibold">{alt.candidate_mpn}</span>
          <span className="ml-2 text-sm text-ink-2">{alt.manufacturer}</span>
        </div>
        <span className="flex items-center gap-2" title={fit.explain}>
          <AskButton
            context={{
              key: alt.id,
              label: alt.candidate_mpn,
              detail: `alternate, ${fit.label.toLowerCase()}`,
              suggestions: [
                `What changes if I approve ${alt.candidate_mpn}?`,
                `How does ${alt.candidate_mpn} compare on cost and lead time?`,
              ],
            }}
          />
          <Tag tone={fit.tone}>{fit.label}</Tag>
          {alt.status !== "PROPOSED" && <Tag tone={alt.status === "APPROVED" ? "mask" : "neutral"}>{sentence(alt.status ?? "")}</Tag>}
        </span>
      </header>
      <div className="flex flex-col gap-3 px-4 py-3 text-sm">
        <p className="leading-relaxed">{alt.explanation}</p>
        <table className="data-table">
          <thead>
            <tr>
              <th>Parameter</th>
              <th>Original</th>
              <th>Candidate</th>
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            {alt.comparison?.map((c) => (
              <tr key={c.attribute}>
                <td>
                  {sentence(c.attribute)}
                  {c.critical && <span className="ml-1 text-xs text-ink-3">(critical)</span>}
                </td>
                <td className="tabular">{c.original ?? "—"}</td>
                <td className="tabular">{c.candidate ?? "—"}</td>
                <td
                  className={clsx(
                    "font-semibold",
                    c.result === "MATCH" && "text-mask",
                    c.result === "WITHIN_TOLERANCE" && "text-mask",
                    c.result === "MISMATCH" && "text-blocker",
                    c.result === "UNKNOWN" && "text-medium",
                  )}
                >
                  {{ MATCH: "Same", WITHIN_TOLERANCE: "Better", MISMATCH: "Different", UNKNOWN: "Unknown" }[c.result]}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
          <dt className="text-ink-3">Authorized stock</dt>
          <dd className="tabular">{quantity(summary.authorized_stock)}</dd>
          <dt className="text-ink-3">Cost difference</dt>
          <dd>
            <FactValue fact={alt.delta_cost} kind="money" currency={currency} />
          </dd>
          <dt className="text-ink-3">Lead time difference</dt>
          <dd>
            <FactValue fact={alt.delta_lead_days} kind="qty" /> days
          </dd>
        </dl>
        <div className="flex flex-wrap items-center gap-2 pt-3">
          <Button variant="quiet" onClick={() => evidence.open({ evidence_ids: alt.evidence_ids ?? [] })}>
            Show evidence
          </Button>
          {alt.note && <span className="text-ink-2">Decision note: {alt.note}</span>}
          {alt.status === "PROPOSED" && (
            <span className="ml-auto flex gap-2">
              <Button onClick={() => onDecide(false)}>Reject</Button>
              <Button
                variant="primary"
                onClick={() => onDecide(true)}
                disabled={alt.fit_class === "NOT_SUITABLE"}
                title={alt.fit_class === "NOT_SUITABLE" ? "Not suitable candidates cannot be approved" : undefined}
              >
                Approve replacement
              </Button>
            </span>
          )}
        </div>
      </div>
    </article>
  );
}

function DecisionDialog({
  projectId,
  deciding,
  onClose,
}: {
  projectId: string;
  deciding: { alt: Alternative; approve: boolean } | null;
  onClose: () => void;
}) {
  const invalidate = useInvalidateProject(projectId);
  const [note, setNote] = useState("");
  const decide = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/projects/{pid}/alternatives/{aid}/decision", {
          params: { path: { pid: projectId, aid: deciding?.alt.id ?? "" } },
          body: { decision: deciding?.approve ? "APPROVE" : "REJECT", note },
        }),
      ),
    onSuccess: () => {
      setNote("");
      onClose();
      void invalidate();
    },
  });
  const approve = deciding?.approve ?? false;
  return (
    <Dialog open={deciding !== null} onClose={onClose} title={approve ? `Approve ${deciding?.alt.candidate_mpn}` : `Reject ${deciding?.alt.candidate_mpn}`}>
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          decide.mutate();
        }}
      >
        <p className="text-sm text-ink-2">
          {approve
            ? "The BOM line will use this part from now on, keep the original part number on record, and be priced and risk-checked again."
            : "The candidate stays on record as rejected, with your reason."}
        </p>
        <TextArea label="Reason (required)" value={note} onChange={(e) => setNote(e.target.value)} required />
        <ErrorNote error={decide.error} />
        <div className="flex gap-2">
          <Button variant="primary" type="submit" disabled={decide.isPending || note.trim().length < 3}>
            {approve ? "Approve replacement" : "Reject"}
          </Button>
          <Button type="button" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
