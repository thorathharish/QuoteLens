"use client";

import { useMutation } from "@tanstack/react-query";
import clsx from "clsx";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ProvenanceLegend, ProvenanceMark, type Provenance } from "@/components/fact";
import { RoleSwitcher } from "@/components/role";
import { ThemeSelect } from "@/components/theme";
import { Button, ErrorNote } from "@/components/ui";
import { Brand } from "@/components/workspace";
import { api, unwrap } from "@/lib/api/client";

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
  const demo = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/demo/projects", { body: { scenario: "motor_controller" } })),
    onSuccess: (seeded) => router.push(`/projects/${seeded.project_id}?job=${seeded.job_id}`),
  });

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-30 border-b border-rule bg-[var(--header-bg)] backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
          <Brand href="/" />
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <ThemeSelect />
            <RoleSwitcher />
            <Link href="/projects" className="text-sm font-semibold text-mask hover:underline">
              Your quotes
            </Link>
          </div>
        </div>
      </header>

      <main id="main" className="flex-1">
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:py-8">
          <section className="surface frame grid grid-cols-1 rounded-[var(--radius-panel)] lg:grid-cols-[0.92fr_1.08fr]">
            <div className="flex flex-col border-b border-rule p-6 sm:p-10 lg:border-r lg:border-b-0">
              <p className="label">Motor controller · 59 lines · 3 blockers</p>
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
                <Link
                  href="/projects?new=1"
                  className="chip inline-flex min-h-11 items-center rounded-lg px-5 text-xs font-semibold tracking-[0.12em] text-ink uppercase transition-colors hover:text-mask active:translate-y-px"
                >
                  Start a new quote
                </Link>
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

      </main>
    </div>
  );
}
