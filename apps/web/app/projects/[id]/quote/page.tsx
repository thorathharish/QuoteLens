"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import Link from "next/link";
import { FactValue } from "@/components/fact";
import { Button, Empty, ErrorNote, Field, Panel, Spinner, Tag } from "@/components/ui";
import { api, getRole, unwrap, type Schemas } from "@/lib/api/client";
import { useProject, useProjectMutation, useQuotes, useRisks } from "@/lib/api/hooks";
import { dateTime, quantity, sentence } from "@/lib/format";

type Quote = Schemas["QuoteVersion"];

export default function QuotePage() {
  const { id } = useParams<{ id: string }>();
  const project = useProject(id);
  const quotes = useQuotes(id);
  const risks = useRisks(id);
  const [note, setNote] = useState("");

  const create = useProjectMutation(id, () =>
    unwrap(api.POST("/api/v1/projects/{pid}/quotes", { params: { path: { pid: id } }, body: { note: note || null } })),
  );
  const reopen = useProjectMutation(id, () =>
    unwrap(api.POST("/api/v1/projects/{pid}/reopen", { params: { path: { pid: id } }, body: { reason: "New revision requested" } })),
  );

  if (quotes.isPending || project.isPending) return <Spinner />;
  if (quotes.error) return <ErrorNote error={quotes.error} />;
  const finalized = project.data?.status === "FINALIZED";
  const blockers = (risks.data?.items ?? []).filter(
    (r) => r.severity === "BLOCKER" && (r.status === "OPEN" || r.status === "ACKNOWLEDGED"),
  );

  return (
    <div className="flex flex-col gap-6">
      <Panel title="Readiness">
        {blockers.length === 0 ? (
          <p className="text-mask">No open blockers. The latest version can be finalized.</p>
        ) : (
          <>
            <p>Finalizing needs these blockers resolved or waived:</p>
            <ul className="mt-2 list-disc pl-5 text-sm">
              {blockers.map((b) => (
                <li key={b.id}>
                  <Link href={`/projects/${id}/risks#${b.id}`} className="text-mask hover:underline">
                    {b.title}
                  </Link>
                </li>
              ))}
            </ul>
          </>
        )}
      </Panel>

      {finalized ? (
        <div className="flex items-center gap-4 rounded-md border border-mask/40 bg-mask-tint px-4 py-3">
          <span>This project is finalized and read-only.</span>
          <Button onClick={() => reopen.mutate(undefined)} disabled={reopen.isPending}>
            Start a new revision
          </Button>
          <ErrorNote error={reopen.error} />
        </div>
      ) : (
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate(undefined, { onSuccess: () => setNote("") });
          }}
        >
          <Field label="Note for this version" value={note} onChange={(e) => setNote(e.target.value)} className="min-w-72 flex-1" />
          <Button variant="primary" type="submit" disabled={create.isPending}>
            Create quote version
          </Button>
          <ErrorNote error={create.error} />
        </form>
      )}

      {quotes.data.items.length === 0 ? (
        <Empty title="No quote versions yet">A version freezes today&apos;s prices, assumptions and risks so it can be sent and audited.</Empty>
      ) : (
        quotes.data.items.map((quote, i) => (
          <QuoteVersionPanel key={quote.id} projectId={id} quote={quote} latest={i === 0} canFinalize={!finalized && blockers.length === 0} />
        ))
      )}
    </div>
  );
}

function QuoteVersionPanel({
  projectId,
  quote,
  latest,
  canFinalize,
}: {
  projectId: string;
  quote: Quote;
  latest: boolean;
  canFinalize: boolean;
}) {
  const [note, setNote] = useState("");
  const finalize = useProjectMutation(projectId, () =>
    unwrap(
      api.POST("/api/v1/projects/{pid}/quotes/{version}/finalize", {
        params: { path: { pid: projectId, version: quote.version } },
        body: { note },
      }),
    ),
  );
  const [downloading, setDownloading] = useState(false);
  const download = async () => {
    setDownloading(true);
    try {
      const response = await fetch(`/api/v1/projects/${projectId}/quotes/${quote.version}/export?format=xlsx`, {
        headers: { "X-Demo-Role": getRole() },
      });
      if (!response.ok) throw new Error(`Export failed (${response.status})`);
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = /filename="([^"]+)"/.exec(response.headers.get("content-disposition") ?? "")?.[1] ?? `quote-v${quote.version}.xlsx`;
      link.click();
      URL.revokeObjectURL(url);
    } finally {
      setDownloading(false);
    }
  };

  return (
    <Panel
      title={
        <span className="flex items-center gap-3">
          Version {quote.version}
          <Tag tone={quote.status === "FINALIZED" ? "mask" : "neutral"}>{sentence(quote.status ?? "DRAFT")}</Tag>
          {quote.data_mode === "demo_snapshot" && <Tag tone="gold">Demo data</Tag>}
        </span>
      }
      action={
        <Button onClick={download} disabled={downloading}>
          {downloading ? "Preparing workbook…" : "Download Excel"}
        </Button>
      }
    >
      <p className="mb-3 text-sm text-ink-2">
        Created {dateTime(quote.created_at)} by {sentence(quote.created_by ?? "VIEWER")}
        {quote.finalized_at && <>, finalized {dateTime(quote.finalized_at)} by {sentence(quote.finalized_by ?? "")}</>}
        {quote.note && <>. {quote.note}</>}
      </p>
      <table className="data-table">
        <thead>
          <tr>
            <th>Boards</th>
            <th className="num">Material</th>
            <th className="num">Adders</th>
            <th className="num">Total</th>
            <th className="num">Per board</th>
          </tr>
        </thead>
        <tbody>
          {quote.volumes.map((v) => (
            <tr key={v.volume}>
              <td className="tabular font-bold">{quantity(v.volume)}</td>
              <td className="num">
                <FactValue fact={v.material} kind="money" currency={quote.currency} />
              </td>
              <td className="num">
                <FactValue fact={v.adders} kind="money" currency={quote.currency} />
              </td>
              <td className="num">
                <FactValue fact={v.total} kind="money" currency={quote.currency} />
              </td>
              <td className="num">
                <FactValue fact={v.per_unit} kind="money" currency={quote.currency} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {latest && quote.status === "DRAFT" && (
        <form
          className="mt-4 flex flex-wrap items-end gap-3 border-t border-rule pt-4"
          onSubmit={(e) => {
            e.preventDefault();
            finalize.mutate(undefined);
          }}
        >
          <Field label="Finalization note (required)" value={note} onChange={(e) => setNote(e.target.value)} className="min-w-72 flex-1" required />
          <Button variant="primary" type="submit" disabled={!canFinalize || finalize.isPending || note.trim().length < 3}>
            Finalize quote
          </Button>
          {!canFinalize && <span className="text-sm text-ink-2">Resolve or waive open blockers first.</span>}
          <ErrorNote error={finalize.error} />
        </form>
      )}
    </Panel>
  );
}
