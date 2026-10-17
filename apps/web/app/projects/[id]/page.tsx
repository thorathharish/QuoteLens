"use client";

import clsx from "clsx";
import Link from "next/link";
import { useParams } from "next/navigation";
import { FactValue } from "@/components/fact";
import { Empty, ErrorNote, PageSkeleton, Panel, SeverityTag } from "@/components/ui";
import { useOverview, useProject } from "@/lib/api/hooks";
import { percent, quantity } from "@/lib/format";

const SEVERITIES = ["BLOCKER", "HIGH", "MEDIUM", "LOW"] as const;

export default function OverviewPage() {
  const { id } = useParams<{ id: string }>();
  const project = useProject(id);
  const overview = useOverview(id);

  if (project.data && project.data.status === "DRAFT") {
    return (
      <Empty title="No BOM yet">
        <Link href={`/projects/${id}/upload`} className="font-semibold text-mask hover:underline">
          Upload the customer BOM
        </Link>{" "}
        to start pricing it.
      </Empty>
    );
  }
  if (project.data?.status === "MAPPING_REVIEW") {
    return (
      <Empty title="Confirm the column mapping">
        The file is uploaded.{" "}
        <Link href={`/projects/${id}/upload`} className="font-semibold text-mask hover:underline">
          Review how its columns were mapped
        </Link>{" "}
        to run the analysis.
      </Empty>
    );
  }
  if (overview.isPending) return <PageSkeleton label="Loading overview" />;
  if (overview.error) return <ErrorNote error={overview.error} />;
  const o = overview.data;
  const r = o.risks;
  const blockers = r.unresolved_by_severity?.BLOCKER ?? 0;

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <div className="flex flex-col gap-6">
        <section
          className="surface frame flex flex-wrap items-center gap-x-8 gap-y-3 rounded-[var(--radius-panel)] px-8 py-7"
        >
          <span
            aria-hidden
            className={clsx(
              "tabular text-7xl leading-none font-light tracking-[-0.06em]",
              r.ready ? "text-mask" : "text-blocker",
            )}
          >
            {blockers}
          </span>
          <div className="min-w-0 flex-1 basis-72">
          <p className={clsx("label flex items-center gap-2", r.ready ? "!text-mask" : "!text-blocker")}>
            <span className="status-dot" aria-hidden />
            {r.ready ? "Quote ready" : "Quote blocked"}
          </p>
          <h2 className="mt-1.5 text-2xl font-light tracking-[-0.03em]">
            {r.ready
              ? "Ready to quote"
              : `${blockers} blocker${blockers === 1 ? "" : "s"} stand between this BOM and a quote`}
          </h2>
          <p className="mt-1 text-ink-2">
            {quantity(o.matched)} of {quantity(o.lines)} lines matched to a known part.{" "}
            {o.unpriced_lines > 0 && `${o.unpriced_lines} line(s) cannot be priced yet. `}
            Lines without blocker or high risks:{" "}
            <FactValue fact={r.readiness_pct} kind="pct" />
          </p>
          </div>
        </section>

        <Panel title="Cost by build quantity">
          <div className="relative -mx-1 overflow-x-auto px-1">
          <table className="data-table">
            <thead>
              <tr>
                <th>Boards</th>
                <th className="num">Material</th>
                <th className="num">Total</th>
                <th className="num">Per board</th>
              </tr>
            </thead>
            <tbody>
              {o.totals_by_volume.map((t) => (
                <tr key={t.volume}>
                  <td className="tabular font-semibold">{quantity(t.volume)}</td>
                  <td className="num">
                    <FactValue fact={t.material} kind="money" currency={o.currency} />
                  </td>
                  <td className="num">
                    <FactValue fact={t.total} kind="money" currency={o.currency} />
                  </td>
                  <td className="num">
                    <FactValue fact={t.per_unit} kind="money" currency={o.currency} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
          {o.unpriced_lines > 0 && (
            <p className="mt-3 text-sm text-ink-2">
              Totals exclude {o.unpriced_lines} unpriced line(s); they are listed under{" "}
              <Link className="text-mask hover:underline" href={`/projects/${id}/risks`}>
                Risks
              </Link>
              .
            </p>
          )}
        </Panel>

        <Panel title="What to do next">
          {o.next_actions.length === 0 ? (
            <p className="text-sm text-ink-2">Nothing outstanding.</p>
          ) : (
            <ol className="-mx-2 flex flex-col">
              {o.next_actions.map((action, i) => (
                <li key={i}>
                  {action.risk_id ? (
                    <Link
                      href={`/projects/${id}/risks#${action.risk_id}`}
                      className="group flex items-center justify-between gap-4 rounded-md px-2 py-2.5 text-sm transition-colors hover:bg-mask-tint"
                    >
                      <span>{action.label}</span>
                      <span className="shrink-0 font-semibold text-mask">Review</span>
                    </Link>
                  ) : (
                    <span className="block px-2 py-2.5 text-sm">{action.label}</span>
                  )}
                </li>
              ))}
            </ol>
          )}
        </Panel>
      </div>

      <aside className="flex flex-col gap-6">
        <Panel title="Open risks">
          <ul className="grid grid-cols-2 gap-2">
            {SEVERITIES.map((s) => (
              <li key={s} className="chip flex flex-col gap-2 rounded-md px-3 py-3">
                <span className="tabular text-4xl leading-none font-light tracking-[-0.05em]">{r.unresolved_by_severity?.[s] ?? 0}</span>
                <span className="self-start">
                  <SeverityTag severity={s} />
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-4 text-sm text-ink-2">
            Spend on lines with blocker or high risks: <FactValue fact={r.spend_at_risk_pct} kind="pct" />
          </p>
          <Link href={`/projects/${id}/risks`} className="mt-3 inline-block text-sm font-semibold text-mask hover:underline">
            Review all {r.total} risks
          </Link>
        </Panel>
        <Panel title="Data">
          <p className="text-sm text-ink-2">
            {o.data_mode === "demo_snapshot"
              ? "Prices, stock and lifecycle come from the demo catalog: synthetic values for demonstration."
              : "Prices come from distributor data; every value shows its source and age."}
          </p>
          <p className="mt-2 text-sm text-ink-2">Matched lines: {percent(o.lines ? o.matched / o.lines : 0)}</p>
        </Panel>
      </aside>
    </div>
  );
}
