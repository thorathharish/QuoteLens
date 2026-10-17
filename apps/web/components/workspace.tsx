"use client";

import clsx from "clsx";
import Link from "next/link";
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

export const STAGES = [
  { key: "upload", label: "Upload" },
  { key: "map", label: "Map columns" },
  { key: "analyze", label: "Analyze" },
  { key: "review", label: "Review" },
  { key: "quote", label: "Quote" },
] as const;

export function stageIndex(status: Project["status"]): number {
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
