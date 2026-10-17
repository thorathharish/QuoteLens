"use client";

import clsx from "clsx";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { Schemas } from "@/lib/api/client";
import { sentence } from "@/lib/format";

type Project = Schemas["Project"];

/** The wordmark: an embossed monogram key plus the name, as in the template's header. */
export function Brand() {
  return (
    <Link href="/" className="group flex items-center gap-3 rounded-md" aria-label="QuoteLens home">
      <span className="chip flex h-9 w-9 items-center justify-center rounded-lg text-xs font-semibold tracking-tight text-ink">
        QL
      </span>
      <span className="hidden leading-none sm:block">
        <span className="block text-sm font-semibold tracking-tight text-ink">QuoteLens</span>
        <span className="label mt-1 block !text-[0.625rem]">BOM to quote</span>
      </span>
    </Link>
  );
}

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
                  "text-[0.6875rem] font-medium tracking-[0.14em] whitespace-nowrap uppercase",
                  active ? "text-ink" : "sr-only text-ink-3 sm:not-sr-only",
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
    <nav className="relative -mx-4 flex overflow-x-auto border-t border-rule sm:mx-0 sm:border-x" aria-label="Project sections">
      {TABS.map((tab) => {
        const href = base + tab.href;
        const active = tab.href === "" ? pathname === base : pathname.startsWith(href);
        return (
          <Link
            key={tab.label}
            href={href}
            aria-current={active ? "page" : undefined}
            className={clsx(
              "relative border-r border-rule px-4 py-3 text-xs font-medium tracking-[0.14em] whitespace-nowrap uppercase transition-colors last:border-r-0",
              active
                ? "bg-mask-tint text-ink after:absolute after:inset-x-0 after:bottom-0 after:h-0.5 after:bg-mask"
                : "text-ink-3 hover:bg-mask-tint/50 hover:text-ink",
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
      ? "text-mask"
      : status === "FAILED"
        ? "text-blocker"
        : "text-ink-2";
  return (
    <span className={clsx("chip inline-flex items-center gap-2 rounded-full px-2.5 py-1 text-[0.6875rem] font-medium tracking-[0.12em] uppercase", tone)}>
      <span className="status-dot" aria-hidden />
      {sentence(status ?? "DRAFT")}
    </span>
  );
}

export function DataModeTag({ mode }: { mode: Project["data_mode"] }) {
  const label =
    mode === "demo_snapshot" ? "Demo snapshot data" : mode === "live_first" ? "Live distributor data" : "Cached distributor data";
  return (
    <span
      className={clsx(
        "chip inline-flex items-center gap-2 rounded-full px-2.5 py-1 text-[0.6875rem] font-medium tracking-[0.12em] uppercase",
        mode === "demo_snapshot" ? "text-gold" : "text-mask",
      )}
      title={mode === "demo_snapshot" ? "Prices, stock and lifecycle are synthetic demo values" : undefined}
    >
      <span className="status-dot" aria-hidden />
      {label}
    </span>
  );
}
