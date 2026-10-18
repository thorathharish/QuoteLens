"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { Schemas } from "@/lib/api/client";
import { useOverview, useQuotes } from "@/lib/api/hooks";

type Status = Schemas["Project"]["status"];
type Step = { href: string; label: string };
type Guide = { note?: string; next?: Step; back?: Step };

/**
 * A slim bar at the bottom of each project page: what to do next, and a button to go there.
 * The order follows the workflow (overview → risks → alternatives → cost → quote), and the
 * advice adapts to the project (open blockers, a finalized quote).
 */
export function NextStepBar({ projectId, status }: { projectId: string; status: Status }) {
  const pathname = usePathname();
  const analyzed = status !== "DRAFT" && status !== "MAPPING_REVIEW" && status !== "ANALYZING" && status !== "FAILED";
  const overview = useOverview(projectId);
  const quotes = useQuotes(projectId);
  if (!analyzed || !overview.data) return null;

  const base = `/projects/${projectId}`;
  const page = pathname === base ? "" : pathname.slice(base.length);
  const blockers = overview.data.risks.unresolved_by_severity?.BLOCKER ?? 0;
  const finalized = (quotes.data?.items ?? []).some((q) => q.status === "FINALIZED");
  const to = (path: string, label: string): Step => ({ href: base + path, label });

  const guides: Record<string, Guide> = {
    "": blockers
      ? {
          note: `${blockers} blocker${blockers === 1 ? "" : "s"} stand between this BOM and a quote.`,
          next: to("/risks", `Resolve the ${blockers} blocker${blockers === 1 ? "" : "s"}`),
        }
      : { note: "No blockers: the BOM can be quoted.", next: to("/impact", "Check the cost impact") },
    "/bom": { back: to("", "Overview"), next: to("/risks", "Review the risks") },
    "/risks": blockers
      ? {
          back: to("/bom", "BOM"),
          note: `${blockers} blocker${blockers === 1 ? "" : "s"} still open: fix the line, approve a replacement or waive with a reason.`,
          next: to("/alternatives", "Look at replacement parts"),
        }
      : { back: to("/bom", "BOM"), note: "All blockers are cleared.", next: to("/impact", "Check the cost impact") },
    "/alternatives": { back: to("/risks", "Risks"), next: to("/impact", "Check the cost impact") },
    "/impact": { back: to("/risks", "Risks"), next: to("/quote", "Create the quote") },
    "/quote": finalized
      ? { back: to("/impact", "Cost impact"), note: "The quote is finalized. Download the Excel workbook above.", next: to("/activity", "See the audit trail") }
      : { back: to("/impact", "Cost impact"), note: blockers ? "Resolve or waive the blockers to finalize." : "Create a version, then finalize it above." },
    "/activity": { back: to("", "Overview") },
  };
  const guide = guides[page];
  if (!guide || (!guide.next && !guide.back && !guide.note)) return null;

  return (
    <nav
      aria-label="Next step"
      className="sticky bottom-0 z-10 -mx-4 mt-8 border-t border-rule bg-[var(--header-bg)] px-4 py-3 backdrop-blur-xl sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8"
    >
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        {guide.back && (
          <Link href={guide.back.href} className="text-sm text-ink-3 transition-colors hover:text-ink">
            ← {guide.back.label}
          </Link>
        )}
        {guide.note && <p className="min-w-0 flex-1 text-sm text-ink-2">{guide.note}</p>}
        {guide.next && (
          <Link
            href={guide.next.href}
            className="metal ml-auto inline-flex min-h-10 items-center gap-2 rounded-lg px-4 text-xs font-semibold tracking-[0.12em] uppercase transition-[filter] hover:brightness-110 active:translate-y-px"
          >
            Next: {guide.next.label}
            <span aria-hidden>→</span>
          </Link>
        )}
      </div>
    </nav>
  );
}
