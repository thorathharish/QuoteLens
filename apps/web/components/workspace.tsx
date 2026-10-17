"use client";

import clsx from "clsx";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { Schemas } from "@/lib/api/client";
import { sentence } from "@/lib/format";

type Project = Schemas["Project"];

const STAGES = [
  { key: "upload", label: "Upload" },
  { key: "map", label: "Map columns" },
  { key: "analyze", label: "Analyze" },
  { key: "review", label: "Review" },
  { key: "quote", label: "Quote" },
] as const;

function stageIndex(status: Project["status"]): number {
  switch (status) {
    case "DRAFT":
      return 0;
    case "MAPPING_REVIEW":
      return 1;
    case "ANALYZING":
    case "FAILED":
      return 2;
    case "IN_REVIEW":
      return 3;
    default:
      return 4;
  }
}

/**
 * The workflow drawn as a circuit trace: pads for stages, copper between them. Done pads and
 * traces are solid copper green, the current pad is gold, upcoming ones are bare laminate.
 */
export function TraceStepper({ status }: { status: Project["status"] }) {
  const current = stageIndex(status);
  return (
    <ol className="flex items-center" aria-label="Workflow progress">
      {STAGES.map((stage, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <li key={stage.key} className="flex flex-1 items-center last:flex-none" aria-current={active ? "step" : undefined}>
            <span className="flex items-center gap-2">
              <span
                className={clsx(
                  "h-3.5 w-3.5 rounded-sm",
                  done && "bg-mask",
                  active && "bg-gold-pad",
                  !done && !active && "bg-rule-strong",
                )}
                aria-hidden
              />
              {/* On a phone only the current stage is named; the pads still show progress. */}
              <span
                className={clsx(
                  "text-sm whitespace-nowrap",
                  active ? "font-semibold text-ink" : "sr-only text-ink-2 sm:not-sr-only",
                )}
              >
                {stage.label}
              </span>
            </span>
            {i < STAGES.length - 1 && (
              <span
                aria-hidden
                className={clsx("mx-2 h-0.5 min-w-3 flex-1 rounded-full sm:mx-3", done ? "bg-mask" : "bg-rule")}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}

const TABS = [
  { href: "", label: "Overview" },
  { href: "/bom", label: "BOM" },
  { href: "/risks", label: "Risks" },
  { href: "/impact", label: "Cost impact" },
  { href: "/alternatives", label: "Alternatives" },
  { href: "/quote", label: "Quote" },
  { href: "/activity", label: "Activity" },
];

export function ProjectTabs({ projectId }: { projectId: string }) {
  const pathname = usePathname();
  const base = `/projects/${projectId}`;
  return (
    <nav className="relative -mx-1 flex gap-1 overflow-x-auto" aria-label="Project sections">
      {TABS.map((tab) => {
        const href = base + tab.href;
        const active = tab.href === "" ? pathname === base : pathname.startsWith(href);
        return (
          <Link
            key={tab.label}
            href={href}
            aria-current={active ? "page" : undefined}
            className={clsx(
              "rounded-t-md px-3.5 py-2.5 text-sm whitespace-nowrap transition-colors",
              active ? "bg-laminate font-semibold text-ink" : "text-ink-2 hover:bg-laminate/60 hover:text-ink",
            )}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}

export function StatusTag({ status }: { status: Project["status"] }) {
  const tone =
    status === "QUOTE_READY" || status === "FINALIZED"
      ? "bg-mask-tint text-mask"
      : status === "FAILED"
        ? "bg-blocker-tint text-blocker"
        : "bg-low-tint text-ink-2";
  return <span className={clsx("rounded-sm px-1.5 py-0.5 text-xs font-semibold", tone)}>{sentence(status ?? "DRAFT")}</span>;
}

export function DataModeTag({ mode }: { mode: Project["data_mode"] }) {
  const label =
    mode === "demo_snapshot" ? "Demo snapshot data" : mode === "live_first" ? "Live distributor data" : "Cached distributor data";
  return (
    <span
      className={clsx(
        "rounded-sm px-1.5 py-0.5 text-xs font-semibold",
        mode === "demo_snapshot" ? "bg-gold-tint text-gold" : "bg-mask-tint text-mask",
      )}
      title={mode === "demo_snapshot" ? "Prices, stock and lifecycle are synthetic demo values" : undefined}
    >
      {label}
    </span>
  );
}
