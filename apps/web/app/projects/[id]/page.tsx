"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FactValue } from "@/components/fact";
import { Empty, ErrorNote, Panel, SeverityTag, Spinner } from "@/components/ui";
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
        <Link href={`/projects/${id}/upload`} className="font-bold text-mask hover:underline">
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
        <Link href={`/projects/${id}/upload`} className="font-bold text-mask hover:underline">
          Review how its columns were mapped
        </Link>{" "}
        to run the analysis.
      </Empty>
    );
  }
  if (overview.isPending) return <Spinner />;
  if (overview.error) return <ErrorNote error={overview.error} />;
  const o = overview.data;
  const r = o.risks;
  const blockers = r.unresolved_by_severity?.BLOCKER ?? 0;

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <div className="flex flex-col gap-6">
        <section
          className={
            r.ready
              ? "rounded-md border border-mask/40 bg-mask-tint px-5 py-4"
              : "rounded-md border border-blocker/30 bg-blocker-tint px-5 py-4"
          }
        >
          <h2 className="text-xl font-bold">
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
        </section>

        <Panel title="Cost by build quantity">
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
                  <td className="tabular font-bold">{quantity(t.volume)}</td>
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
            <ol className="divide-y divide-rule">
              {o.next_actions.map((action, i) => (
                <li key={i} className="flex items-center justify-between gap-4 py-2 text-sm">
                  <span>{action.label}</span>
                  {action.risk_id && (
                    <Link href={`/projects/${id}/risks#${action.risk_id}`} className="shrink-0 font-bold text-mask hover:underline">
                      Review
                    </Link>
                  )}
                </li>
              ))}
            </ol>
          )}
        </Panel>
      </div>

      <aside className="flex flex-col gap-6">
        <Panel title="Open risks">
          <ul className="space-y-2">
            {SEVERITIES.map((s) => (
              <li key={s} className="flex items-center justify-between">
                <SeverityTag severity={s} />
                <span className="tabular text-lg font-bold">{r.unresolved_by_severity?.[s] ?? 0}</span>
              </li>
            ))}
          </ul>
          <p className="mt-4 border-t border-rule pt-3 text-sm text-ink-2">
            Spend on lines with blocker or high risks: <FactValue fact={r.spend_at_risk_pct} kind="pct" />
          </p>
          <Link href={`/projects/${id}/risks`} className="mt-3 inline-block text-sm font-bold text-mask hover:underline">
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
