"use client";

import { useMutation } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ProvenanceLegend, ProvenanceMark, type Provenance } from "@/components/fact";
import { RoleSwitcher } from "@/components/role";
import { Button, ErrorNote, Field, Spinner } from "@/components/ui";
import { api, unwrap } from "@/lib/api/client";
import { useProjects } from "@/lib/api/hooks";
import { dateTime, sentence } from "@/lib/format";

/** One real line from the demo BOM, shown the way QuoteLens explains it. */
const SPECIMEN: { label: string; value: string; provenance: Provenance; source: string }[] = [
  { label: "Part", value: "A1101ELHLT-T", provenance: "ACTUAL", source: "BOM row 11" },
  { label: "Lifecycle", value: "Obsolete, last-time-buy 2026-03-31", provenance: "ACTUAL", source: "Catalog" },
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
    <div className="min-h-screen">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
        <span className="text-xl font-bold tracking-tight text-mask">QuoteLens</span>
        <RoleSwitcher />
      </header>

      <main className="mx-auto max-w-6xl px-6 pb-20">
        <section className="grid items-start gap-10 py-10 lg:grid-cols-[1fr_minmax(0,30rem)]">
          <div className="max-w-xl pt-4">
            <h1 className="text-3xl leading-tight font-bold">Quotes you can defend, line by line.</h1>
            <p className="mt-4 text-lg text-ink-2">
              Upload a customer BOM. QuoteLens prices every part across distributors, explains each risk with
              its evidence, works out MOQ and scrap cost per build volume, and keeps a person in charge of
              every decision.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Button variant="primary" onClick={() => demo.mutate()} disabled={demo.isPending}>
                {demo.isPending ? "Preparing the demo…" : "Open the demo project"}
              </Button>
              <a href="#new" className="text-sm font-bold text-mask hover:underline">
                Start a new quote
              </a>
            </div>
            <div className="mt-3">
              <ErrorNote error={demo.error} />
            </div>
          </div>

          <figure className="rounded-md border border-rule-strong bg-silk">
            <figcaption className="border-b border-rule px-4 py-2.5 text-sm text-ink-2">
              How QuoteLens shows one BOM line
            </figcaption>
            <dl className="divide-y divide-rule">
              {SPECIMEN.map((row) => (
                <div key={row.label} className="grid grid-cols-[9.5rem_1fr] gap-3 px-4 py-2.5 text-sm">
                  <dt className="text-ink-3">{row.label}</dt>
                  <dd className="flex flex-col">
                    <span className="flex items-baseline justify-between gap-3">
                      <span className={row.label === "Part" || row.label === "Replacement" ? "code" : undefined}>
                        {row.value}
                      </span>
                      <ProvenanceMark provenance={row.provenance} />
                    </span>
                    <span className="text-xs text-ink-3">{row.source}</span>
                  </dd>
                </div>
              ))}
            </dl>
            <div className="border-t border-rule px-4 py-3">
              <ProvenanceLegend />
            </div>
          </figure>
        </section>

        <section id="new" className="grid gap-8 border-t border-rule pt-10 lg:grid-cols-[minmax(0,26rem)_1fr]">
          <NewProject />
          <div>
            <h2 className="text-lg font-bold">Recent projects</h2>
            {projects.isPending && <Spinner />}
            <ErrorNote error={projects.error} />
            {projects.data && projects.data.items.length === 0 && (
              <p className="mt-2 text-sm text-ink-2">No projects yet. Open the demo or start a new quote.</p>
            )}
            <ul className="mt-3 divide-y divide-rule rounded-md border border-rule bg-silk">
              {projects.data?.items.map((p) => (
                <li key={p.id}>
                  <Link href={`/projects/${p.id}`} className="flex items-center justify-between gap-4 px-4 py-3 hover:bg-mask-tint">
                    <span>
                      <span className="font-bold">{p.name}</span>
                      {p.customer && <span className="ml-2 text-sm text-ink-3">{p.customer}</span>}
                    </span>
                    <span className="flex items-center gap-4 text-sm text-ink-2">
                      <span>{sentence(p.status ?? "DRAFT")}</span>
                      <span className="hidden sm:inline">{dateTime(p.updated_at)}</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </section>
      </main>
    </div>
  );
}

function NewProject() {
  const router = useRouter();
  const [form, setForm] = useState({ name: "", customer: "", volumes: "100, 1000, 5000", target: "" });
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
            data_mode: "cache_first",
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
      className="flex flex-col gap-4"
    >
      <h2 className="text-lg font-bold">Start a new quote</h2>
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
      <ErrorNote error={create.error} />
      <div>
        <Button variant="primary" type="submit" disabled={create.isPending || !form.name}>
          Create project and upload BOM
        </Button>
      </div>
    </form>
  );
}
