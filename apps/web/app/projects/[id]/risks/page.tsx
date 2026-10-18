"use client";

import { useMutation } from "@tanstack/react-query";
import clsx from "clsx";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { AskButton } from "@/components/copilot";
import { FactValue, useEvidence } from "@/components/fact";
import { LineDialog } from "@/components/line-detail";
import { Button, Dialog, Empty, ErrorNote, PageSkeleton, SeverityTag, Tag, TextArea } from "@/components/ui";
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

  if (risks.isPending) return <PageSkeleton rows={8} label="Loading risks" />;
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
        <label className="flex items-center gap-2 text-sm text-ink-2">
          <input type="checkbox" className="h-4 w-4 accent-mask" checked={showClosed} onChange={(e) => setShowClosed(e.target.checked)} />
          Show resolved and waived
        </label>
      </div>

      {visible.length === 0 && <Empty title="No open risks">Everything has been resolved or waived.</Empty>}

      {SEVERITIES.map((severity) => {
        const group = visible.filter((r) => r.severity === severity);
        if (group.length === 0) return null;
        return (
          <section key={severity} aria-labelledby={`sev-${severity}`}>
            <h2 id={`sev-${severity}`} className="mb-3 flex items-center gap-3 text-lg font-semibold">
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
  const { id: projectId } = useParams<{ id: string }>();
  const closed = risk.status === "RESOLVED" || risk.status === "WAIVED";
  return (
    <li
      id={risk.id}
      className={clsx(
        "surface scroll-mt-40 rounded-[var(--radius-panel)] px-5 py-4 target:ring-2 target:ring-mask",
        risk.severity === "BLOCKER" && !closed && "border-l-2 border-l-blocker",
        closed && "opacity-70",
      )}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-semibold">
          {risk.title}
          {part && (
            <button onClick={onOpenLine} className="code ml-2 rounded-sm font-medium text-mask hover:underline">
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
          <Tag tone={closed ? "mask" : "neutral"}>{sentence(risk.status ?? "OPEN")}</Tag>
        </span>
      </div>
      <p className="mt-1 max-w-[75ch] leading-relaxed">{risk.why}</p>
      {risk.resolution_note && <p className="mt-1 text-sm text-ink-2">Note: {risk.resolution_note}</p>}
      {risk.suggested_actions?.length ? (
        <p className="mt-2 text-sm text-ink-2">Suggested: {risk.suggested_actions.map((a) => a.label).join("; ")}</p>
      ) : null}
      {!closed && risk.suggested_actions?.some((a) => a.label.includes("exchange rate")) && (
        <Link href={`/projects/${projectId}/impact#rates`} className="mt-1 inline-block text-sm font-medium text-mask hover:underline">
          Set the exchange rate →
        </Link>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-2">
        <Button variant="quiet" className="-ml-1.5" onClick={() => evidence.open({ evidence_ids: risk.evidence_ids })}>
          Show evidence ({risk.evidence_ids.length})
        </Button>
        <span className="ml-auto" />
        <AskButton
          context={{
            key: risk.id,
            label: part ?? risk.title,
            detail: part ? risk.title.toLowerCase() : sentence(risk.severity ?? "risk"),
            suggestions: [
              "How can I clear this risk?",
              part ? `Is there a replacement for ${part}?` : "Which lines does this affect?",
            ],
          }}
        />
        {!closed && (
          <span className="flex flex-wrap items-center gap-1">
            {risk.status === "OPEN" && (
              <Button variant="quiet" onClick={() => onDecide("ACKNOWLEDGED")}>
                Acknowledge
              </Button>
            )}
            <Button variant="danger" onClick={() => onDecide("WAIVED")}>
              Waive
            </Button>
            <Button onClick={() => onDecide("RESOLVED")}>Mark resolved</Button>
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
