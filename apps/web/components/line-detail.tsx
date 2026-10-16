"use client";

import { useMutation } from "@tanstack/react-query";
import clsx from "clsx";
import Link from "next/link";
import { useState } from "react";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useInvalidateProject, useLine } from "@/lib/api/hooks";
import { dateTime, money, quantity, sentence } from "@/lib/format";
import { FactValue, ProvenanceMark, useEvidence } from "./fact";
import { Button, Dialog, ErrorNote, Field, SeverityTag, Spinner, Tag } from "./ui";

type Offer = Schemas["Offer"];

export function LineDialog({ projectId, lineId, onClose }: { projectId: string; lineId: string | null; onClose: () => void }) {
  return (
    <Dialog open={lineId !== null} onClose={onClose} title="BOM line" wide>
      {lineId && <LineDetailBody projectId={projectId} lineId={lineId} />}
    </Dialog>
  );
}

function LineDetailBody({ projectId, lineId }: { projectId: string; lineId: string }) {
  const detail = useLine(projectId, lineId);
  const evidence = useEvidence();
  if (detail.isPending) return <Spinner />;
  if (detail.error) return <ErrorNote error={detail.error} />;
  const { line, component, offers, recommendation, risks, alternatives } = detail.data;
  const notFound = line.match?.status === "NOT_FOUND";

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="code text-lg font-bold">{line.mpn ?? "No part number"}</p>
          <p className="text-ink-2">
            {line.manufacturer ?? "Manufacturer not given"}
            {line.description && <span className="text-ink-3">, {line.description}</span>}
          </p>
          {line.substituted_from && (
            <p className="mt-1 text-sm">
              <Tag tone="mask">Replaces</Tag> <span className="code">{line.substituted_from}</span>
            </p>
          )}
        </div>
        <dl className="grid grid-cols-[auto_auto] gap-x-4 gap-y-1 text-sm">
          <dt className="text-ink-3">Qty per board</dt>
          <dd>
            <FactValue fact={line.qty_per} kind="qty" />
          </dd>
          <dt className="text-ink-3">Designators</dt>
          <dd className="max-w-56 truncate" title={line.refdes?.join(", ")}>
            {line.refdes?.join(", ") || "—"}
          </dd>
          <dt className="text-ink-3">Lifecycle</dt>
          <dd>
            {component ? (
              <button className="hover:underline" onClick={() => evidence.open({ evidence_ids: component.evidence_id ? [component.evidence_id] : [] })}>
                {sentence(component.lifecycle ?? "UNKNOWN")}
                {component.ltb_date && `, last-time-buy ${component.ltb_date}`}
              </button>
            ) : (
              "—"
            )}
          </dd>
        </dl>
      </section>

      {line.validation && line.validation.length > 0 && (
        <ul className="flex flex-col gap-1">
          {line.validation.map((issue, i) => (
            <li key={i} className="rounded border border-medium/30 bg-medium-tint px-3 py-1.5 text-sm text-medium">
              {issue.message}
            </li>
          ))}
        </ul>
      )}

      {notFound && (
        <MpnFix projectId={projectId} lineId={line.id} candidates={line.match?.candidates ?? []} />
      )}

      {recommendation && (
        <section>
          <h3 className="mb-2 font-bold">Recommended source</h3>
          <ul className="space-y-1 text-sm">
            {recommendation.reasons.map((reason) => (
              <li key={reason} className="flex gap-2">
                <ProvenanceMark provenance={recommendation.offer_id ? "RECOMMENDED" : "UNAVAILABLE"} />
                <span>{reason}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {offers.length > 0 && (
        <OffersTable
          projectId={projectId}
          lineId={line.id}
          offers={offers}
          selected={line.selected_offer_id ?? null}
          recommended={recommendation?.offer_id ?? null}
        />
      )}

      {risks.length > 0 && (
        <section>
          <h3 className="mb-2 font-bold">Risks on this line</h3>
          <ul className="space-y-2">
            {risks.map((risk) => (
              <li key={risk.id} className="text-sm">
                <span className="mr-2">
                  <SeverityTag severity={risk.severity} />
                </span>
                <span className="font-bold">{risk.title}.</span> {risk.why}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="flex flex-wrap items-center gap-3 border-t border-rule pt-4">
        {alternatives.length > 0 ? (
          <Link href={`/projects/${projectId}/alternatives?line=${line.id}`} className="text-sm font-bold text-mask hover:underline">
            {alternatives.length} alternate(s) investigated
          </Link>
        ) : (
          <FindAlternates projectId={projectId} lineId={line.id} />
        )}
        <EditLine projectId={projectId} line={line} />
      </section>
    </div>
  );
}

function OffersTable({
  projectId,
  lineId,
  offers,
  selected,
  recommended,
}: {
  projectId: string;
  lineId: string;
  offers: Offer[];
  selected: string | null;
  recommended: string | null;
}) {
  const evidence = useEvidence();
  const invalidate = useInvalidateProject(projectId);
  const [choosing, setChoosing] = useState<Offer | null>(null);
  const [reason, setReason] = useState("");
  const select = useMutation({
    mutationFn: (offer: Offer) =>
      unwrap(
        api.PUT("/api/v1/projects/{pid}/lines/{lid}/selected-offer", {
          params: { path: { pid: projectId, lid: lineId } },
          body: { offer_id: offer.id, reason },
        }),
      ),
    onSuccess: () => {
      setChoosing(null);
      setReason("");
      void invalidate();
    },
  });

  return (
    <section>
      <h3 className="mb-2 font-bold">Distributor offers</h3>
      <div className="overflow-x-auto rounded border border-rule">
        <table className="data-table">
          <thead>
            <tr>
              <th>Distributor</th>
              <th className="num">Stock</th>
              <th className="num">MOQ</th>
              <th className="num">Lead time</th>
              <th>Price breaks</th>
              <th>Source</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {offers.map((offer) => (
              <tr key={offer.id} className={clsx(offer.id === selected && "bg-mask-tint")}>
                <td>
                  <span className="font-bold">{offer.distributor}</span>
                  {!offer.authorized && <span className="ml-2 text-xs text-blocker">unauthorized</span>}
                  {offer.id === recommended && (
                    <span className="ml-2">
                      <ProvenanceMark provenance="RECOMMENDED" withLabel />
                    </span>
                  )}
                </td>
                <td className="num">{quantity(offer.stock)}</td>
                <td className="num">{quantity(offer.moq)}</td>
                <td className="num">{offer.lead_time_days === null || offer.lead_time_days === undefined ? "—" : `${offer.lead_time_days} d`}</td>
                <td className="tabular text-xs">
                  {offer.price_breaks?.map((b) => `${quantity(b.qty)}: ${money(b.unit_price, offer.currency, 2)}`).join("  ")}
                </td>
                <td>
                  <button
                    onClick={() => evidence.open({ evidence_ids: [offer.evidence_id], provenance: "ACTUAL" })}
                    className="text-xs text-mask hover:underline"
                    title={dateTime(offer.fetched_at)}
                  >
                    {offer.mode === "DEMO_SNAPSHOT" ? "Demo snapshot" : sentence(offer.mode)}
                  </button>
                </td>
                <td>
                  {offer.id === selected ? (
                    <span className="text-xs font-bold text-mask">Selected</span>
                  ) : (
                    offer.authorized && (
                      <Button variant="quiet" onClick={() => setChoosing(offer)}>
                        Use this
                      </Button>
                    )
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {choosing && (
        <form
          className="mt-3 flex flex-wrap items-end gap-3 rounded border border-rule bg-laminate p-3"
          onSubmit={(e) => {
            e.preventDefault();
            select.mutate(choosing);
          }}
        >
          <Field
            label={`Why use ${choosing.distributor}?`}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="min-w-64 flex-1"
            required
            minLength={3}
          />
          <Button variant="primary" type="submit" disabled={select.isPending || reason.trim().length < 3}>
            Use {choosing.distributor}
          </Button>
          <Button type="button" onClick={() => setChoosing(null)}>
            Cancel
          </Button>
          <ErrorNote error={select.error} />
        </form>
      )}
    </section>
  );
}

function MpnFix({ projectId, lineId, candidates }: { projectId: string; lineId: string; candidates: string[] }) {
  const invalidate = useInvalidateProject(projectId);
  const [mpn, setMpn] = useState(candidates[0] ?? "");
  const [reason, setReason] = useState(candidates.length ? "Accepted the suggested part number" : "");
  const fix = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/projects/{pid}/lines/{lid}/match", {
          params: { path: { pid: projectId, lid: lineId } },
          body: { mpn, reason },
        }),
      ),
    onSuccess: () => invalidate(),
  });
  return (
    <section className="rounded border border-high/40 bg-high-tint p-3">
      <h3 className="font-bold text-high">This part number was not found</h3>
      {candidates.length > 0 && (
        <p className="mt-1 text-sm">
          Closest known: {candidates.map((c) => <span key={c} className="code mr-2">{c}</span>)}
        </p>
      )}
      <form
        className="mt-3 flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          fix.mutate();
        }}
      >
        <Field label="Correct part number" value={mpn} onChange={(e) => setMpn(e.target.value)} required />
        <Field label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} required minLength={3} className="flex-1" />
        <Button variant="primary" type="submit" disabled={fix.isPending || !mpn || reason.trim().length < 3}>
          Use this part number
        </Button>
      </form>
      <ErrorNote error={fix.error} />
    </section>
  );
}

function FindAlternates({ projectId, lineId }: { projectId: string; lineId: string }) {
  const invalidate = useInvalidateProject(projectId);
  const search = useMutation({
    mutationFn: async () => {
      const accepted = await unwrap(
        api.POST("/api/v1/projects/{pid}/lines/{lid}/alternatives/search", {
          params: { path: { pid: projectId, lid: lineId } },
          body: {},
        }),
      );
      for (let i = 0; i < 40; i++) {
        const job = await unwrap(api.GET("/api/v1/jobs/{job_id}", { params: { path: { job_id: accepted.job_id } } }));
        if (job.status === "SUCCEEDED" || job.status === "FAILED") return job;
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
      throw new Error("The alternates search is taking longer than expected");
    },
    onSuccess: () => invalidate(),
  });
  return (
    <span className="flex items-center gap-3">
      <Button onClick={() => search.mutate()} disabled={search.isPending}>
        {search.isPending ? "Investigating alternates…" : "Find alternates"}
      </Button>
      {search.data?.warnings?.map((w) => (
        <span key={w} className="text-sm text-ink-2">
          {w}
        </span>
      ))}
      <ErrorNote error={search.error} />
    </span>
  );
}

function EditLine({ projectId, line }: { projectId: string; line: Schemas["BomLine"] }) {
  const invalidate = useInvalidateProject(projectId);
  const [open, setOpen] = useState(false);
  const [qty, setQty] = useState(line.qty_per.value ? String(line.qty_per.value) : "");
  const [maker, setMaker] = useState(line.manufacturer ?? "");
  const [reason, setReason] = useState("");
  const save = useMutation({
    mutationFn: () => {
      const changes: Schemas["LineChangesIn"] = {};
      if (qty && qty !== String(line.qty_per.value ?? "")) changes.qty_per = qty;
      if (maker && maker !== (line.manufacturer ?? "")) changes.manufacturer = maker;
      return unwrap(
        api.PATCH("/api/v1/projects/{pid}/lines/{lid}", {
          params: { path: { pid: projectId, lid: line.id } },
          body: { changes, reason },
        }),
      );
    },
    onSuccess: () => {
      setOpen(false);
      void invalidate();
    },
  });
  if (!open) return <Button onClick={() => setOpen(true)}>Correct this line</Button>;
  return (
    <form
      className="flex w-full flex-wrap items-end gap-3 rounded border border-rule bg-laminate p-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <Field label="Qty per board" value={qty} onChange={(e) => setQty(e.target.value)} inputMode="decimal" className="w-32" />
      <Field label="Manufacturer" value={maker} onChange={(e) => setMaker(e.target.value)} />
      <Field label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} required minLength={3} className="flex-1" />
      <Button variant="primary" type="submit" disabled={save.isPending || reason.trim().length < 3}>
        Save correction
      </Button>
      <Button type="button" onClick={() => setOpen(false)}>
        Cancel
      </Button>
      <div className="w-full">
        <ErrorNote error={save.error} />
      </div>
    </form>
  );
}
