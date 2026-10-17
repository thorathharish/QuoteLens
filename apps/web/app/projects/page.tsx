"use client";

import { useMutation } from "@tanstack/react-query";
import clsx from "clsx";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { ProvenanceMark } from "@/components/fact";
import { NewQuotePanel } from "@/components/new-quote";
import { RoleSwitcher } from "@/components/role";
import { ThemeSelect } from "@/components/theme";
import { Button, Empty, ErrorNote, Skeleton } from "@/components/ui";
import { Brand, StatusTag } from "@/components/workspace";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useProjects } from "@/lib/api/hooks";
import { dateTime, money } from "@/lib/format";

type Project = Schemas["Project"];
type Filter = "all" | "open" | "done";

const FILTERS: { key: Filter; label: string; test: (p: Project) => boolean }[] = [
  { key: "all", label: "All", test: () => true },
  { key: "open", label: "In progress", test: (p) => p.status !== "FINALIZED" },
  { key: "done", label: "Finalized", test: (p) => p.status === "FINALIZED" },
];

/** The tool's home: every quote, and a panel to start a new one from a customer BOM. */
export default function ProjectsPage() {
  return (
    <Suspense>
      <ProjectsHome />
    </Suspense>
  );
}

function ProjectsHome() {
  const router = useRouter();
  const params = useSearchParams();
  const projects = useProjects();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const firstField = useRef<HTMLInputElement>(null);

  // /projects?new=1 (the rail's "New quote") puts the cursor in the form.
  useEffect(() => {
    if (params.get("new")) firstField.current?.focus();
  }, [params]);

  const demo = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/demo/projects", { body: { scenario: "motor_controller" } })),
    onSuccess: (seeded) => router.push(`/projects/${seeded.project_id}?job=${seeded.job_id}`),
  });

  const items = useMemo(() => projects.data?.items ?? [], [projects.data]);
  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const test = FILTERS.find((f) => f.key === filter)?.test ?? (() => true);
    return items.filter(
      (p) => test(p) && (!needle || [p.name, p.customer].filter(Boolean).some((v) => String(v).toLowerCase().includes(needle))),
    );
  }, [items, query, filter]);

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-30 border-b border-rule bg-[var(--header-bg)] backdrop-blur-xl">
        <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-3 sm:px-6 lg:pl-5">
          <div className="flex items-center gap-5">
            <Brand />
            <span className="hidden text-sm text-ink-3 sm:inline">Projects</span>
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <ThemeSelect compact />
            <RoleSwitcher />
          </div>
        </div>
      </header>

      <div className="flex flex-1 flex-col lg:flex-row">
        <ToolRail onNew={() => firstField.current?.focus()} />

        <main id="main" className="min-w-0 flex-1 px-4 py-8 sm:px-6 lg:px-8">
          <p className="label">Projects</p>
          <h1 className="mt-1 text-[1.875rem] font-light tracking-[-0.04em]">Your quotes</h1>

          <div className="mt-5 flex flex-wrap items-center gap-3">
            <label className="flex min-w-0 flex-1 basis-64 items-center gap-2 rounded-md border border-rule-strong bg-silk px-3 py-2 text-ink-3 focus-within:border-mask sm:max-w-sm">
              <svg aria-hidden viewBox="0 0 24 24" className="h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round">
                <circle cx="11" cy="11" r="7" />
                <path d="m20 20-3.5-3.5" />
              </svg>
              <span className="sr-only">Search projects</span>
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search by project or customer"
                className="min-w-0 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-ink-3"
              />
            </label>
            <div className="flex gap-1.5" role="group" aria-label="Filter by status">
              {FILTERS.map((f) => (
                <button
                  key={f.key}
                  type="button"
                  aria-pressed={filter === f.key}
                  onClick={() => setFilter(f.key)}
                  className={clsx(
                    "rounded-full px-3 py-1.5 text-sm transition-colors active:translate-y-px",
                    filter === f.key ? "metal" : "chip text-ink-2 hover:text-ink",
                  )}
                >
                  {f.label} <span className="tabular opacity-70">{items.filter(f.test).length}</span>
                </button>
              ))}
            </div>
            <Button className="ml-auto" onClick={() => demo.mutate()} disabled={demo.isPending}>
              {demo.isPending ? "Preparing…" : "Open the demo"}
            </Button>
          </div>
          <div className="mt-2">
            <ErrorNote error={demo.error ?? projects.error} />
          </div>

          <div className="mt-4">
            {projects.isPending ? (
              <div className="surface flex flex-col gap-3 rounded-[var(--radius-panel)] p-5">
                {[0, 1, 2].map((i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : items.length === 0 ? (
              <Empty title="No quotes yet">
                Start one with the <span className="font-semibold text-mask">New quote</span> panel: add the project details and
                drop the customer BOM. Or open the demo to see a finished analysis.
              </Empty>
            ) : rows.length === 0 ? (
              <Empty title="Nothing matches">Try another search or filter.</Empty>
            ) : (
              <div className="surface relative overflow-x-auto rounded-[var(--radius-panel)] p-2">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Project</th>
                      <th>Status</th>
                      <th className="num">Blockers</th>
                      <th className="num">Total at first volume</th>
                      <th className="num">Updated</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((p) => (
                      <ProjectRow key={p.id} project={p} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </main>

        <aside
          aria-label="New quote"
          className="flex border-t border-rule lg:sticky lg:top-[61px] lg:h-[calc(100dvh-61px)] lg:w-[400px] lg:shrink-0 lg:self-start lg:border-t-0 lg:border-l"
          style={{ background: "var(--panel-bg)" }}
        >
          <NewQuotePanel ref={firstField} />
        </aside>
      </div>
    </div>
  );
}

function ProjectRow({ project: p }: { project: Project }) {
  const router = useRouter();
  const first = p.build_quantities[0];
  const total = first !== undefined ? p.stats?.totals_by_volume?.[String(first)] : undefined;
  const blockers = p.stats?.open_blockers ?? 0;
  const analyzed = (p.stats?.lines ?? 0) > 0;
  return (
    // The whole row opens the project; the name stays a real link for keyboard and new tabs.
    <tr className="cursor-pointer" onClick={() => router.push(`/projects/${p.id}`)}>
      <td>
        <Link href={`/projects/${p.id}`} className="block rounded-sm">
          <span className="block font-semibold text-ink">{p.name}</span>
          {p.customer && <span className="block text-xs text-ink-3">{p.customer}</span>}
        </Link>
      </td>
      <td className="whitespace-nowrap">
        <StatusTag status={p.status} />
      </td>
      <td className={clsx("num", blockers ? "font-semibold text-blocker" : "text-ink-3")}>{analyzed ? blockers : "—"}</td>
      <td className="num whitespace-nowrap">
        {total !== undefined ? (
          <span className="inline-flex items-baseline gap-1.5">
            {money(total, p.currency, 2)}
            <ProvenanceMark provenance="CALCULATED" />
            <span className="text-xs text-ink-3">at {first?.toLocaleString("en-US")}</span>
          </span>
        ) : (
          <span className="text-ink-3">—</span>
        )}
      </td>
      <td className="num whitespace-nowrap text-ink-3">{dateTime(p.updated_at)}</td>
    </tr>
  );
}

/** Tool-level rail (outside a project): the projects list and a jump to the new-quote form. */
function ToolRail({ onNew }: { onNew: () => void }) {
  return (
    <nav
      aria-label="Tool"
      className="sticky top-[61px] z-20 hidden h-[calc(100dvh-61px)] w-16 shrink-0 flex-col items-center gap-1 self-start border-r border-rule bg-laminate-2/95 pt-4 lg:flex"
    >
      <Link
        href="/projects"
        aria-current="page"
        title="Your quotes"
        className="relative flex h-11 w-11 items-center justify-center rounded-md bg-mask-tint text-mask"
      >
        <span aria-hidden className="absolute inset-y-2 -left-2.5 w-0.5 rounded-full bg-mask" />
        <svg aria-hidden viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinejoin="round">
          <path d="M3 7h7l2 2h9v10H3z" />
        </svg>
        <span className="sr-only">Your quotes</span>
      </Link>
      <button
        type="button"
        onClick={onNew}
        title="New quote"
        className="flex h-11 w-11 items-center justify-center rounded-md text-ink-2 transition-colors hover:bg-mask-tint/60 hover:text-ink"
      >
        <svg aria-hidden viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round">
          <path d="M12 5v14M5 12h14" />
        </svg>
        <span className="sr-only">New quote</span>
      </button>
    </nav>
  );
}
