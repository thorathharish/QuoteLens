"use client";

import { useMutation } from "@tanstack/react-query";
import clsx from "clsx";
import { useParams } from "next/navigation";
import { useState } from "react";
import { FactValue, useEvidence } from "@/components/fact";
import { LineDialog } from "@/components/line-detail";
import { Button, Dialog, Empty, ErrorNote, SeverityTag, Spinner, TextArea } from "@/components/ui";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useInvalidateProject, useLines, useRisks } from "@/lib/api/hooks";
import { sentence } from "@/lib/format";

type Risk = Schemas["Risk"];
type Decision = "ACKNOWLEDGED" | "RESOLVED" | "WAIVED";

const SEVERITIES = ["BLOCKER", "HIGH", "MEDIUM", "LOW"] as const;
const HEADINGS: Record<string, string> = {
  BLOCKER: "Blockers: the quote cannot be finalized until these are resolved or waived",
  HIGH: "High",
  MEDIUM: "Medium",
  LOW: "Low",
};

export default function RisksPage() {
  const { id } = useParams<{ id: string }>();
  const risks = useRisks(id);
  const lines = useLines(id);
  const [showClosed, setShowClosed] = useState(false);
  const [reviewing, setReviewing] = useState<{ risk: Risk; decision: Decision } | null>(null);
  const [lineId, setLineId] = useState<string | null>(null);

  if (risks.isPending) return <Spinner />;
  if (risks.error) return <ErrorNote error={risks.error} />;
  const labels = new Map((lines.data?.items ?? []).map((l) => [l.id, l.mpn ?? l.refdes?.join(", ") ?? l.id]));
  const visible = risks.data.items.filter(
    (r) => showClosed || r.status === "OPEN" || r.status === "ACKNOWLEDGED",
  );

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <p className="text-ink-2">
          {risks.data.summary.open_blockers === 0
            ? "No open blockers."
            : `${risks.data.summary.open_blockers} open blocker(s).`}{" "}
          Every risk below says why it was raised and links to its evidence.
        </p>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={showClosed} onChange={(e) => setShowClosed(e.target.checked)} />
          Show resolved and waived
        </label>
      </div>

      {visible.length === 0 && <Empty title="No open risks">Everything has been resolved or waived.</Empty>}

      {SEVERITIES.map((severity) => {
        const group = visible.filter((r) => r.severity === severity);
        if (group.length === 0) return null;
        return (
          <section key={severity} aria-labelledby={`sev-${severity}`}>
            <h2 id={`sev-${severity}`} className="mb-3 flex items-center gap-3 text-base font-bold">
              <SeverityTag severity={severity} />
              <span>{HEADINGS[severity]}</span>
            </h2>
            <ul className="flex flex-col gap-3">
              {group.map((risk) => (
                <RiskItem
                  key={risk.id}
                  risk={risk}
                  part={risk.line_id ? labels.get(risk.line_id) : undefined}
                  onDecide={(decision) => setReviewing({ risk, decision })}
                  onOpenLine={() => risk.line_id && setLineId(risk.line_id)}
                />
              ))}
            </ul>
          </section>
        );
      })}

      <ReviewDialog projectId={id} reviewing={reviewing} onClose={() => setReviewing(null)} />
      <LineDialog projectId={id} lineId={lineId} onClose={() => setLineId(null)} />
    </div>
  );
}

function RiskItem({
  risk,
  part,
  onDecide,
  onOpenLine,
}: {
  risk: Risk;
  part?: string;
  onDecide: (decision: Decision) => void;
  onOpenLine: () => void;
}) {
  const evidence = useEvidence();
  const closed = risk.status === "RESOLVED" || risk.status === "WAIVED";
  return (
    <li
      id={risk.id}
      className={clsx(
        "rounded-md border bg-silk px-4 py-3 target:ring-2 target:ring-mask",
        risk.severity === "BLOCKER" ? "border-blocker/40" : "border-rule",
        closed && "opacity-70",
      )}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-bold">
          {risk.title}
          {part && (
            <button onClick={onOpenLine} className="code ml-2 font-medium text-mask hover:underline">
              {part}
            </button>
          )}
        </h3>
        <span className="flex items-center gap-3 text-sm">
          {risk.cost_exposure && (
            <span className="text-ink-3">
              Line cost <FactValue fact={risk.cost_exposure} kind="money" />
            </span>
          )}
          <span className={clsx("font-bold", closed ? "text-mask" : "text-ink-2")}>{sentence(risk.status ?? "OPEN")}</span>
        </span>
      </div>
      <p className="mt-1 max-w-[75ch] leading-relaxed">{risk.why}</p>
      {risk.resolution_note && <p className="mt-1 text-sm text-ink-2">Note: {risk.resolution_note}</p>}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button variant="quiet" onClick={() => evidence.open({ evidence_ids: risk.evidence_ids })}>
          Show evidence ({risk.evidence_ids.length})
        </Button>
        {risk.suggested_actions?.length ? (
          <span className="text-sm text-ink-2">Suggested: {risk.suggested_actions.map((a) => a.label).join("; ")}</span>
        ) : null}
        {!closed && (
          <span className="ml-auto flex gap-2">
            {risk.status === "OPEN" && <Button onClick={() => onDecide("ACKNOWLEDGED")}>Acknowledge</Button>}
            <Button onClick={() => onDecide("RESOLVED")}>Mark resolved</Button>
            <Button variant="danger" onClick={() => onDecide("WAIVED")}>
              Waive
            </Button>
          </span>
        )}
      </div>
    </li>
  );
}

function ReviewDialog({
  projectId,
  reviewing,
  onClose,
}: {
  projectId: string;
  reviewing: { risk: Risk; decision: Decision } | null;
  onClose: () => void;
}) {
  const invalidate = useInvalidateProject(projectId);
  const [note, setNote] = useState("");
  const review = useMutation({
    mutationFn: () =>
      unwrap(
        api.PATCH("/api/v1/projects/{pid}/risks/{rid}", {
          params: { path: { pid: projectId, rid: reviewing?.risk.id ?? "" } },
          body: { status: reviewing?.decision ?? "ACKNOWLEDGED", note: note || null },
        }),
      ),
    onSuccess: () => {
      setNote("");
      onClose();
      void invalidate();
    },
  });
  const verb = { ACKNOWLEDGED: "Acknowledge", RESOLVED: "Mark resolved", WAIVED: "Waive" }[reviewing?.decision ?? "ACKNOWLEDGED"];
  const needsNote = reviewing?.decision === "WAIVED";
  return (
    <Dialog open={reviewing !== null} onClose={onClose} title={`${verb}: ${reviewing?.risk.title ?? ""}`}>
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          review.mutate();
        }}
      >
        <p className="text-sm text-ink-2">
          {needsNote
            ? "Waiving accepts the risk for this quote. Say who agreed and why; it is recorded in the audit trail."
            : "Your decision is recorded in the audit trail with your role."}
        </p>
        <TextArea
          label={needsNote ? "Reason (required)" : "Note (optional)"}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          required={needsNote}
        />
        <ErrorNote error={review.error} />
        <div className="flex gap-2">
          <Button
            variant={needsNote ? "danger" : "primary"}
            type="submit"
            disabled={review.isPending || (needsNote && note.trim().length < 3)}
          >
            {verb}
          </Button>
          <Button type="button" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
