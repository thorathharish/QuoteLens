"use client";

import { useMutation } from "@tanstack/react-query";
import clsx from "clsx";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ProvenanceLegend, ProvenanceMark, type Provenance } from "@/components/fact";
import { RoleSwitcher } from "@/components/role";
import { ThemeSelect } from "@/components/theme";
import { Button, ErrorNote, Field, Skeleton } from "@/components/ui";
import { Brand } from "@/components/workspace";
import { api, unwrap } from "@/lib/api/client";
import { useProjects } from "@/lib/api/hooks";
import { dateTime, sentence } from "@/lib/format";

/** One real line from the demo BOM, shown the way QuoteLens explains it. */
const SPECIMEN: { label: string; value: string; provenance: Provenance; source: string }[] = [
  { label: "Part", value: "A1101ELHLT-T", provenance: "ACTUAL", source: "BOM row 11" },
  { label: "Lifecycle", value: "Obsolete, last-time-buy 2026‑03‑31", provenance: "ACTUAL", source: "Catalog" },
  { label: "Needed for 100 boards", value: "300 units", provenance: "CALCULATED", source: "3 per board × 100 boards" },
  { label: "Authorized stock", value: "0 units", provenance: "ACTUAL", source: "3 distributors" },
  { label: "Unit price", value: "No authorized offer", provenance: "UNAVAILABLE", source: "Broker stock excluded" },
  { label: "Replacement", value: "A1120ELHLX-T, drop-in", provenance: "RECOMMENDED", source: "Needs approval" },
];

const POINTS = [
  { title: "Evidence on every number", body: "Each value says if it is actual, calculated, assumed or missing." },
  { title: "People approve decisions", body: "Mappings, waivers, alternates and the final quote need a person." },
];

/** Facts about the product and the demo BOM, not marketing numbers. */
const STATS = [
  { label: "Demo lines", value: "59" },
  { label: "Risk rules", value: "19" },
  { label: "Provenance kinds", value: "5" },
  { label: "Human gates", value: "4" },
];

export default function Home() {
  const router = useRouter();
  const projects = useProjects();
  const demo = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/demo/projects", { body: { scenario: "motor_controller" } })),
    onSuccess: (seeded) => router.push(`/projects/${seeded.project_id}?job=${seeded.job_id}`),
  });

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-30 border-b border-rule bg-[var(--header-bg)] backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
          <Brand />
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <ThemeSelect />
            <RoleSwitcher />
          </div>
        </div>
      </header>

      <main id="main" className="flex-1">
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:py-8">
          <section className="surface frame grid grid-cols-1 rounded-[var(--radius-panel)] lg:grid-cols-[0.92fr_1.08fr]">
            <div className="flex flex-col border-b border-rule p-6 sm:p-10 lg:border-r lg:border-b-0">
              <span className="chip inline-flex items-center gap-2 self-start rounded-full px-3 py-1.5 text-[0.6875rem] font-medium tracking-[0.14em] text-mask uppercase">
                <span className="status-dot" aria-hidden />
                Demo BOM ready
              </span>
              <p className="label mt-8">Motor controller · 59 lines · 3 blockers</p>
              <h1 className="text-display mt-4 max-w-[11ch] text-ink">Quotes you can defend, line by line.</h1>
              <p className="mt-6 max-w-[32rem] leading-relaxed text-ink-2 sm:text-lg">
                Upload a customer BOM. QuoteLens prices every part across distributors, shows the evidence behind
                each risk and works out MOQ and scrap cost per build, while a person approves every decision.
              </p>
              <ul className="mt-8 grid grid-cols-1 gap-5 border-t border-rule pt-6 sm:grid-cols-2">
                {POINTS.map((point) => (
                  <li key={point.title}>
                    <span className="flex h-8 w-8 items-center justify-center rounded-full border border-mask/30 bg-mask-tint text-mask">
                      <span className="status-dot" aria-hidden />
                    </span>
                    <p className="mt-3 font-medium tracking-[-0.02em] text-ink">{point.title}</p>
                    <p className="mt-1 text-sm text-ink-3">{point.body}</p>
                  </li>
                ))}
              </ul>
              <div className="mt-8 flex flex-wrap items-center gap-3">
                <Button variant="primary" className="min-h-11 px-5" onClick={() => demo.mutate()} disabled={demo.isPending}>
                  {demo.isPending ? "Preparing the demo…" : "Open the demo project"}
                </Button>
                <a
                  href="#new"
                  className="chip inline-flex min-h-11 items-center rounded-lg px-5 text-xs font-semibold tracking-[0.12em] text-ink uppercase transition-colors hover:text-mask active:translate-y-px"
                >
                  Start a new quote
                </a>
              </div>
              <div className="mt-3">
                <ErrorNote error={demo.error} />
              </div>
            </div>

            {/* A real interface fragment: how one line of the demo BOM is explained. */}
            <figure className="flex flex-col">
              <figcaption className="label flex items-center gap-2 px-6 pt-6 sm:px-10 sm:pt-10">
                <span className="status-dot text-mask" aria-hidden />
                One BOM line, explained
              </figcaption>
              <dl className="mx-6 mt-5 flex flex-1 flex-col justify-between sm:mx-10">
                {SPECIMEN.map((row) => (
                  <div
                    key={row.label}
                    className="grid grid-cols-[8rem_1fr] gap-4 border-b border-rule py-3.5 text-sm last:border-b-0 sm:grid-cols-[11rem_1fr]"
                  >
                    <dt className="label pt-0.5">{row.label}</dt>
                    <dd className="flex flex-col">
                      <span className="flex items-baseline justify-between gap-3">
                        <span className={clsx("font-medium text-ink", (row.label === "Part" || row.label === "Replacement") && "code")}>
                          {row.value}
                        </span>
                        <ProvenanceMark provenance={row.provenance} />
                      </span>
                      <span className="text-xs text-ink-3">{row.source}</span>
                    </dd>
                  </div>
                ))}
              </dl>
              <div className="mx-6 mt-4 mb-2 sm:mx-10">
                <ProvenanceLegend />
              </div>
              <dl className="mt-4 grid grid-cols-2 border-t border-rule sm:grid-cols-4">
                {STATS.map((stat) => (
                  <div key={stat.label} className="border-r border-rule px-6 py-4 last:border-r-0 sm:px-10 [&:nth-child(2)]:max-sm:border-r-0">
                    <dt className="label">{stat.label}</dt>
                    <dd className="tabular mt-1 text-lg font-medium text-ink">{stat.value}</dd>
                  </div>
                ))}
              </dl>
            </figure>
          </section>
        </div>

        <section id="new" className="mx-auto max-w-7xl scroll-mt-24 px-4 pb-16 sm:px-6">
          <div className="surface grid grid-cols-1 rounded-[var(--radius-panel)] lg:grid-cols-[minmax(0,28rem)_minmax(0,1fr)]">
            <div className="border-b border-rule p-6 sm:p-10 lg:border-r lg:border-b-0">
              <NewProject />
            </div>
            <div className="p-6 sm:p-10">
              <h2 className="text-3xl font-light tracking-[-0.04em]">Recent projects</h2>
              <div className="mt-6">
                {projects.isPending && (
                  <div className="flex flex-col gap-2">
                    <Skeleton className="h-14 w-full" />
                    <Skeleton className="h-14 w-full" />
                  </div>
                )}
                <ErrorNote error={projects.error} />
                {projects.data && projects.data.items.length === 0 && (
                  <p className="text-ink-2">No projects yet. Open the demo or start a new quote.</p>
                )}
                <ul className="flex flex-col border-t border-rule">
                  {projects.data?.items.map((p) => (
                    <li key={p.id}>
                      <Link
                        href={`/projects/${p.id}`}
                        className="flex items-center justify-between gap-4 border-b border-rule px-2 py-4 transition-colors hover:bg-mask-tint"
                      >
                        <span className="min-w-0">
                          <span className="block truncate font-medium text-ink">{p.name}</span>
                          {p.customer && <span className="block text-sm text-ink-3">{p.customer}</span>}
                        </span>
                        <span className="flex shrink-0 items-center gap-4">
                          <span className="label">{sentence(p.status ?? "DRAFT")}</span>
                          <span className="hidden text-sm text-ink-3 sm:inline">{dateTime(p.updated_at)}</span>
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}

function NewProject() {
  const router = useRouter();
  const [form, setForm] = useState<{
    name: string;
    customer: string;
    volumes: string;
    target: string;
    dataMode: "cache_first" | "live_first";
  }>({ name: "", customer: "", volumes: "100, 1000, 5000", target: "", dataMode: "cache_first" });
  const create = useMutation({
    mutationFn: () => {
      const build_quantities = form.volumes
        .split(/[,\s]+/)
        .filter(Boolean)
        .map(Number);
      return unwrap(
        api.POST("/api/v1/projects", {
          body: {
            name: form.name,
            customer: form.customer || null,
            build_quantities,
            target_ship_date: form.target || null,
            currency: "USD",
            data_mode: form.dataMode,
          },
        }),
      );
    },
    onSuccess: (project) => router.push(`/projects/${project.id}/upload`),
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        create.mutate();
      }}
      className="flex min-w-0 flex-col gap-4"
    >
      <h2 className="text-3xl font-light tracking-[-0.04em]">Start a new quote</h2>
      <Field label="Project name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
      <Field label="Customer" value={form.customer} onChange={(e) => setForm({ ...form, customer: e.target.value })} />
      <Field
        label="Build quantities"
        hint="Up to five volumes, comma separated. The first one is used for recommendations."
        value={form.volumes}
        onChange={(e) => setForm({ ...form, volumes: e.target.value })}
      />
      <Field
        label="Target ship date"
        type="date"
        hint="Used to flag lead times that would miss it."
        value={form.target}
        onChange={(e) => setForm({ ...form, target: e.target.value })}
      />
      <label className="flex flex-col gap-1 text-sm">
        <span className="label">Distributor prices</span>
        <select
          value={form.dataMode}
          onChange={(e) => setForm({ ...form, dataMode: e.target.value as typeof form.dataMode })}
          className="w-full min-w-0 rounded-md border border-rule-strong bg-silk px-3 py-2 text-base text-ink transition-colors hover:border-ink-3"
        >
          <option value="cache_first">Saved prices first, live lookup for parts we have no price for</option>
          <option value="live_first">Live lookup for every part (DigiKey, Mouser, element14)</option>
        </select>
        <span className="text-xs text-ink-3">Live lookups need distributor keys on the server.</span>
      </label>
      <ErrorNote error={create.error} />
      <div>
        <Button variant="primary" type="submit" disabled={create.isPending || !form.name}>
          Create project and upload BOM
        </Button>
      </div>
    </form>
  );
}
