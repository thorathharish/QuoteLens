"use client";

import clsx from "clsx";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { FactValue } from "@/components/fact";
import { LineDialog } from "@/components/line-detail";
import { ErrorNote, PageSkeleton, Tag } from "@/components/ui";
import { useLines } from "@/lib/api/hooks";
import { sentence } from "@/lib/format";

const ISSUE_LABEL: Record<string, string> = {
  MISSING_MPN: "Missing part number",
  MISSING_MFR: "Missing manufacturer",
  QTY_INVALID: "Invalid quantity",
  REFDES_QTY_MISMATCH: "Designators ≠ quantity",
  DUPLICATE_MPN_CONFLICT: "Conflicting duplicates",
  SUSPECT_MPN_FORMAT: "Odd part number",
  UOM_CONFLICT: "Unit conflict",
  DNP: "Do not populate",
};

export default function BomPage() {
  const { id } = useParams<{ id: string }>();
  const lines = useLines(id);
  const [issue, setIssue] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<string | null>(null);

  const rows = useMemo(() => {
    const items = lines.data?.items ?? [];
    const needle = query.trim().toLowerCase();
    return items.filter(
      (line) =>
        (!issue || line.validation?.some((v) => v.code === issue)) &&
        (!needle ||
          [line.mpn, line.manufacturer, line.description, line.cpn, line.refdes?.join(",")]
            .filter(Boolean)
            .some((v) => String(v).toLowerCase().includes(needle))),
    );
  }, [lines.data, issue, query]);

  if (lines.isPending) return <PageSkeleton />;
  if (lines.error) return <ErrorNote error={lines.error} />;
  const counts = Object.entries(lines.data.issue_counts ?? {});

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-ink-2">Data issues:</span>
        {counts.length === 0 && <span className="text-sm text-mask">none found</span>}
        {counts.map(([code, count]) => (
          <button
            key={code}
            onClick={() => setIssue(issue === code ? null : code)}
            aria-pressed={issue === code}
            className={clsx(
              "rounded-md px-3 py-1.5 text-sm transition-colors active:translate-y-px",
              issue === code ? "metal" : "chip text-ink hover:text-mask",
            )}
          >
            {ISSUE_LABEL[code] ?? sentence(code)} <span className="tabular font-semibold">{count}</span>
          </button>
        ))}
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search part, maker, designator"
          aria-label="Search lines"
          className="ml-auto w-72 rounded-md border border-rule-strong bg-silk px-2.5 py-1.5 text-sm"
        />
      </div>

      <div className="relative overflow-x-auto surface rounded-[var(--radius-panel)] p-2">
        <table className="data-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Designators</th>
              <th>Part number</th>
              <th>Manufacturer</th>
              <th className="num">Qty/board</th>
              <th>Match</th>
              <th>Issues</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((line) => (
              <tr key={line.id} onClick={() => setOpen(line.id)} className="cursor-pointer">
                <td className="tabular text-ink-3">{line.line_no}</td>
                <td className="max-w-40 truncate" title={line.refdes?.join(", ")}>
                  {line.refdes?.join(", ")}
                </td>
                <td>
                  <button className="code text-left font-medium hover:underline" onClick={() => setOpen(line.id)}>
                    {line.mpn ?? <span className="text-blocker">missing</span>}
                  </button>
                  {line.substituted_from && (
                    <span className="ml-2">
                      <Tag tone="mask">replaces {line.substituted_from}</Tag>
                    </span>
                  )}
                </td>
                <td>{line.manufacturer ?? <span className="text-ink-3">—</span>}</td>
                <td className="num" onClick={(e) => e.stopPropagation()}>
                  <FactValue fact={line.qty_per} kind="qty" />
                </td>
                <td>{line.dnp ? <span className="text-ink-3">Not fitted</span> : matchLabel(line.match?.status)}</td>
                <td className="text-xs text-medium">
                  {line.validation?.filter((v) => v.code !== "DNP").map((v) => ISSUE_LABEL[v.code] ?? v.code).join(", ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <p className="px-4 py-6 text-sm text-ink-2">No lines match this filter.</p>}
      </div>
      <LineDialog projectId={id} lineId={open} onClose={() => setOpen(null)} />
    </div>
  );
}

function matchLabel(status: string | undefined) {
  if (status === "MATCHED") return <span className="text-mask">Matched</span>;
  if (status === "NOT_FOUND") return <span className="text-high">Not found</span>;
  if (status === "AMBIGUOUS") return <span className="text-high">Ambiguous</span>;
  return <span className="text-ink-3">Not sourced</span>;
}
