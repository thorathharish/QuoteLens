"use client";

import { useMutation } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { FactValue } from "@/components/fact";
import { Button, ErrorNote, Field, PageSkeleton, Panel } from "@/components/ui";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useAssumptions, useImpact, useLines, useProject, useProjectMutation } from "@/lib/api/hooks";
import { money, quantity, toNumber } from "@/lib/format";

type LineImpact = Schemas["LineImpact"];

export default function ImpactPage() {
  const { id } = useParams<{ id: string }>();
  const project = useProject(id);
  const volumes = project.data?.build_quantities ?? [];
  const [volume, setVolume] = useState<number | undefined>(undefined);
  const firstVolume = volumes[0];
  useEffect(() => {
    if (volume === undefined && firstVolume) setVolume(firstVolume);
  }, [volume, firstVolume]);
  const impact = useImpact(id, volume);
  const lines = useLines(id);
  const [trace, setTrace] = useState<string | null>(null);
  const currency = project.data?.currency ?? "USD";

  const names = useMemo(
    () => new Map((lines.data?.items ?? []).map((l) => [l.id, l.mpn ?? l.refdes?.join(", ") ?? l.id])),
    [lines.data],
  );

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center gap-2" role="radiogroup" aria-label="Build quantity">
        <span className="text-sm text-ink-2">Build quantity</span>
        {volumes.map((v) => (
          <button
            key={v}
            role="radio"
            aria-checked={v === volume}
            onClick={() => setVolume(v)}
            className={
              v === volume
                ? "metal rounded-md px-3 py-1.5 text-sm font-semibold transition-colors"
                : "chip rounded-md px-3 py-1.5 text-sm text-ink transition-colors hover:text-mask active:translate-y-px"
            }
          >
            {quantity(v)} boards
          </button>
        ))}
      </div>

      {impact.isPending && <PageSkeleton />}
      <ErrorNote error={impact.error} />
      {impact.data && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_24rem]">
          <div className="flex flex-col gap-6">
            <Panel title="Where the money goes">
              <Waterfall steps={impact.data.waterfall} currency={currency} />
            </Panel>

            {impact.data.recommendations.length > 0 && (
              <Panel title="Cheaper order quantities">
                <ul className="flex flex-col gap-1 text-sm">
                  {impact.data.recommendations.slice(0, 6).map((r) => (
                    <li key={r.line_id + r.message} className="flex items-baseline justify-between gap-4 py-2">
                      <span>{r.message}</span>
                      <FactValue fact={r.saving} kind="money" currency={currency} />
                    </li>
                  ))}
                </ul>
              </Panel>
            )}

            <Panel title="Cost per line">
              <div className="relative max-h-[32rem] overflow-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Part</th>
                      <th className="num">Buy</th>
                      <th className="num">Unit price</th>
                      <th className="num">Extended</th>
                      <th className="num">MOQ excess</th>
                      <th className="num">Share</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {[...impact.data.lines]
                      .sort((a, b) => (toNumber(b.extended.value as string) ?? -1) - (toNumber(a.extended.value as string) ?? -1))
                      .map((line) => (
                        <ImpactRow
                          key={line.line_id}
                          line={line}
                          name={names.get(line.line_id) ?? line.line_id}
                          currency={currency}
                          open={trace === line.line_id}
                          onToggle={() => setTrace(trace === line.line_id ? null : line.line_id)}
                        />
                      ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          </div>

          <aside className="flex flex-col gap-6">
            <Panel title="Totals">
              <dl className="grid grid-cols-[1fr_auto] gap-y-1.5 text-sm">
                <dt>Material</dt>
                <dd className="text-right">
                  <FactValue fact={impact.data.totals.material} kind="money" currency={currency} />
                </dd>
                <dt>Adders</dt>
                <dd className="text-right">
                  <FactValue fact={impact.data.totals.adders} kind="money" currency={currency} />
                </dd>
                <dt className="font-semibold">Total</dt>
                <dd className="text-right font-semibold">
                  <FactValue fact={impact.data.totals.grand_total} kind="money" currency={currency} />
                </dd>
                <dt>Per board</dt>
                <dd className="text-right">
                  <FactValue fact={impact.data.totals.per_unit} kind="money" currency={currency} />
                </dd>
              </dl>
              {impact.data.unpriced_line_ids.length > 0 && (
                <p className="mt-3 text-sm text-ink-2">{impact.data.unpriced_line_ids.length} line(s) could not be priced and are excluded.</p>
              )}
            </Panel>
            {volume !== undefined && <WhatIf projectId={id} volume={volume} lines={impact.data.lines} names={names} currency={currency} />}
            <AssumptionsEditor projectId={id} />
          </aside>
        </div>
      )}
    </div>
  );
}

function Waterfall({ steps, currency }: { steps: Schemas["WaterfallStep"][]; currency: string }) {
  const total = toNumber(steps.at(-1)?.value.value as string) ?? 0;
  return (
    <ul className="flex flex-col gap-2">
      {steps.map((step) => {
        const value = toNumber(step.value.value as string) ?? 0;
        const width = total > 0 ? Math.max(1, (value / total) * 100) : 0;
        const isTotal = step.label === "Total";
        return (
          <li key={step.label} className="grid grid-cols-[10rem_1fr_9rem] items-center gap-3 text-sm">
            <span className={isTotal ? "font-semibold" : undefined}>{step.label}</span>
            <span className="h-3 rounded-sm bg-laminate">
              <span className={`block h-3 rounded-sm ${isTotal ? "bg-mask" : "bg-mask/55"}`} style={{ width: `${width}%` }} />
            </span>
            <span className="text-right">
              <FactValue fact={step.value} kind="money" currency={currency} />
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function ImpactRow({
  line,
  name,
  currency,
  open,
  onToggle,
}: {
  line: LineImpact;
  name: string;
  currency: string;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <>
      <tr>
        <td className="code">{name}</td>
        <td className="num">
          <FactValue fact={line.buy_qty} kind="qty" />
        </td>
        <td className="num">
          <FactValue fact={line.unit_price} kind="money" currency={currency} />
        </td>
        <td className="num">
          <FactValue fact={line.extended} kind="money" currency={currency} />
        </td>
        <td className="num">
          <FactValue fact={line.excess_cost} kind="money" currency={currency} />
        </td>
        <td className="num">
          <FactValue fact={line.contribution_pct} kind="pct" />
        </td>
        <td>
          <Button variant="quiet" className="text-sm font-semibold tracking-normal whitespace-nowrap normal-case" onClick={onToggle} aria-expanded={open}>
            {open ? "Hide steps" : "Show steps"}
          </Button>
        </td>
      </tr>
      {open && (
        <tr>
          <td colSpan={7} className="bg-laminate">
            <ol className="flex flex-col gap-1 py-1">
              {line.trace?.map((step, i) => (
                <li key={i} className="grid grid-cols-[12rem_1fr_auto] gap-3 text-xs">
                  <span className="font-semibold">{step.label}</span>
                  <span className="tabular text-ink-2">{step.formula}</span>
                  <FactValue fact={step.output} kind={step.label.includes("cost") || step.label.startsWith("Unit") ? "money" : step.label.startsWith("Scrap") ? "pct" : "qty"} currency={currency} />
                </li>
              ))}
            </ol>
          </td>
        </tr>
      )}
    </>
  );
}

function WhatIf({
  projectId,
  volume,
  lines,
  names,
  currency,
}: {
  projectId: string;
  volume: number;
  lines: LineImpact[];
  names: Map<string, string>;
  currency: string;
}) {
  const [lineId, setLineId] = useState("");
  const [scrap, setScrap] = useState("0");
  const simulate = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/projects/{pid}/impact/simulate", {
          params: { path: { pid: projectId } },
          body: { volume, overrides: lineId ? [{ line_id: lineId, scrap_pct: String(Number(scrap) / 100) }] : [] },
        }),
      ),
  });
  return (
    <Panel title="What if">
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          simulate.mutate();
        }}
      >
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-semibold text-ink-2">Line</span>
          <select value={lineId} onChange={(e) => setLineId(e.target.value)} className="rounded-md border border-rule-strong bg-silk px-2 py-1.5">
            <option value="">Choose a line</option>
            {lines.map((l) => (
              <option key={l.line_id} value={l.line_id}>
                {names.get(l.line_id)}
              </option>
            ))}
          </select>
        </label>
        <Field label="Scrap allowance (%)" type="number" min={0} max={100} step={0.5} value={scrap} onChange={(e) => setScrap(e.target.value)} />
        <Button type="submit" disabled={!lineId || simulate.isPending}>
          Calculate
        </Button>
        <ErrorNote error={simulate.error} />
        {simulate.data && (
          <p className="text-sm">
            Total changes by <FactValue fact={simulate.data.delta} kind="money" currency={currency} /> to{" "}
            {money(simulate.data.simulated.totals.grand_total.value as string, currency)}. Nothing is saved.
          </p>
        )}
      </form>
    </Panel>
  );
}

function AssumptionsEditor({ projectId }: { projectId: string }) {
  const assumptions = useAssumptions(projectId);
  const [form, setForm] = useState({ assembly: "", nre: "", overhead: "", margin: "", inr: "" });
  useEffect(() => {
    const a = assumptions.data?.adders;
    if (a)
      setForm({
        assembly: a.assembly_per_unit ?? "",
        nre: a.nre ?? "",
        overhead: a.overhead_pct ? String(Number(a.overhead_pct) * 100) : "",
        margin: a.margin_pct ? String(Number(a.margin_pct) * 100) : "",
        inr: assumptions.data?.fx_overrides?.["USD->INR"] ?? "",
      });
  }, [assumptions.data]);
  const save = useProjectMutation(projectId, () =>
    unwrap(
      api.PUT("/api/v1/projects/{pid}/assumptions", {
        params: { path: { pid: projectId } },
        body: {
          scrap_policy: assumptions.data?.scrap_policy,
          fx_overrides: (() => {
            const rates: Record<string, string> = { ...(assumptions.data?.fx_overrides ?? {}) };
            if (form.inr) rates["USD->INR"] = form.inr;
            else delete rates["USD->INR"];
            return rates;
          })(),
          adders: {
            assembly_per_unit: form.assembly || null,
            nre: form.nre || null,
            overhead_pct: form.overhead ? String(Number(form.overhead) / 100) : null,
            margin_pct: form.margin ? String(Number(form.margin) / 100) : null,
          },
        },
      }),
    ),
  );
  return (
    <Panel title="Quote adders and exchange rate">
      <form
        className="grid grid-cols-2 gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate(undefined);
        }}
      >
        <Field label="Assembly per board" inputMode="decimal" value={form.assembly} onChange={(e) => setForm({ ...form, assembly: e.target.value })} />
        <Field label="NRE" inputMode="decimal" value={form.nre} onChange={(e) => setForm({ ...form, nre: e.target.value })} />
        <Field label="Overhead %" inputMode="decimal" value={form.overhead} onChange={(e) => setForm({ ...form, overhead: e.target.value })} />
        <Field label="Margin %" inputMode="decimal" value={form.margin} onChange={(e) => setForm({ ...form, margin: e.target.value })} />
        <Field
          label="INR per 1 USD"
          inputMode="decimal"
          hint="Lets offers priced in INR (Mouser, element14 India) be compared and costed."
          value={form.inr}
          onChange={(e) => setForm({ ...form, inr: e.target.value })}
          className="col-span-2"
        />
        <p className="col-span-2 text-xs text-ink-3">Adders and exchange rates are your assumptions and are labelled as such everywhere.</p>
        <div className="col-span-2">
          <Button type="submit" disabled={save.isPending}>
            Save assumptions
          </Button>
          <ErrorNote error={save.error} />
        </div>
      </form>
    </Panel>
  );
}
