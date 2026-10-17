"use client";

import { useMutation } from "@tanstack/react-query";
import clsx from "clsx";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ProvenanceLegend, ProvenanceMark, type Provenance } from "@/components/fact";
import { RoleSwitcher } from "@/components/role";
import { Button, ErrorNote, Field, Skeleton } from "@/components/ui";
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

export default function Home() {
  const router = useRouter();
  const projects = useProjects();
  const demo = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/demo/projects", { body: { scenario: "motor_controller" } })),
    onSuccess: (seeded) => router.push(`/projects/${seeded.project_id}?job=${seeded.job_id}`),
  });

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-5">
        <span className="text-xl font-bold tracking-tight text-mask">QuoteLens</span>
        <RoleSwitcher />
      </header>

      <main id="main" className="flex-1">
        <section className="mx-auto grid max-w-6xl grid-cols-1 items-center gap-12 px-6 pt-10 pb-20 lg:grid-cols-[minmax(0,1fr)_minmax(0,29rem)] lg:pt-16 lg:pb-28">
          <div>
            <h1 className="text-display max-w-[11ch] font-bold text-ink">Quotes you can defend, line by line.</h1>
            <p className="mt-6 max-w-[34rem] text-lg leading-relaxed text-ink-2 sm:text-xl">
              Upload a customer BOM. QuoteLens prices every part across distributors, shows the evidence behind
              each risk and works out MOQ and scrap cost per build, while a person approves every decision.
            </p>
            <div className="mt-9 flex flex-wrap items-center gap-x-5 gap-y-3">
              <Button variant="primary" className="px-5 py-3 text-base" onClick={() => demo.mutate()} disabled={demo.isPending}>
                {demo.isPending ? "Preparing the demo…" : "Open the demo project"}
              </Button>
              <a href="#new" className="rounded-md px-1 py-2 font-semibold text-mask hover:underline">
                Start a new quote
              </a>
            </div>
            <div className="mt-3">
              <ErrorNote error={demo.error} />
            </div>
          </div>

          {/* A real interface fragment: how one line of the demo BOM is explained. */}
          <figure data-ui className="rounded-[var(--radius-panel)] bg-silk p-2">
            <figcaption className="px-4 pt-3 pb-2 text-sm font-semibold text-ink-2">How QuoteLens shows one BOM line</figcaption>
            <dl>
              {SPECIMEN.map((row, i) => (
                <div
                  key={row.label}
                  className={clsx(
                    "grid grid-cols-[8.5rem_1fr] gap-3 rounded-md px-4 py-3 text-sm sm:grid-cols-[9.5rem_1fr]",
                    i % 2 === 0 && "bg-laminate",
                  )}
                >
                  <dt className="text-ink-2">{row.label}</dt>
                  <dd className="flex flex-col">
                    <span className="flex items-baseline justify-between gap-3">
                      <span className={clsx("font-semibold", (row.label === "Part" || row.label === "Replacement") && "code")}>
                        {row.value}
                      </span>
                      <ProvenanceMark provenance={row.provenance} />
                    </span>
                    <span className="text-xs text-ink-3">{row.source}</span>
                  </dd>
                </div>
              ))}
            </dl>
            <div className="px-4 pt-3 pb-2">
              <ProvenanceLegend />
            </div>
          </figure>
        </section>

        <section id="new" className="scroll-mt-4 bg-laminate-2">
          <div className="mx-auto grid max-w-6xl grid-cols-1 gap-x-14 gap-y-12 px-6 py-16 lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)] lg:py-20">
            <NewProject />
            <div>
              <h2 className="text-2xl font-semibold">Recent projects</h2>
              <div className="mt-5">
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
                <ul className="flex flex-col gap-1.5">
                  {projects.data?.items.map((p) => (
                    <li key={p.id}>
                      <Link
                        href={`/projects/${p.id}`}
                        className="flex items-center justify-between gap-4 rounded-md bg-silk px-4 py-3.5 transition-colors hover:bg-mask-tint"
                      >
                        <span className="min-w-0">
                          <span className="block truncate font-semibold">{p.name}</span>
                          {p.customer && <span className="block text-sm text-ink-2">{p.customer}</span>}
                        </span>
                        <span className="flex shrink-0 items-center gap-4 text-sm text-ink-2">
                          <span>{sentence(p.status ?? "DRAFT")}</span>
                          <span className="hidden sm:inline">{dateTime(p.updated_at)}</span>
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
      <h2 className="text-2xl font-semibold">Start a new quote</h2>
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
        <span className="font-semibold text-ink-2">Distributor prices</span>
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
