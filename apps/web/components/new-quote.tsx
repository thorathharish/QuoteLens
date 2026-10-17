"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { useRouter } from "next/navigation";
import { forwardRef, useState } from "react";
import { api, getRole, unwrap, type Schemas } from "@/lib/api/client";
import { FIELDS, METHOD_LABEL, clashingColumns, mappingChanges, type FieldName } from "@/lib/mapping";
import { Button, ErrorNote, Field } from "./ui";

type Preview = Schemas["UploadPreview"];
type DataMode = "cache_first" | "live_first";
type Step = "details" | "columns";

const STEPS = ["Details", "BOM", "Columns", "Analysis"] as const;
const ACCEPT = ".xlsx,.csv,.tsv";
const MAX_BYTES = 5 * 1024 * 1024;

/**
 * Start a quote without leaving the projects page: project details and the customer BOM
 * first, then the column mapping preview, then the analysis runs in the new workspace.
 */
export const NewQuotePanel = forwardRef<HTMLInputElement>(function NewQuotePanel(_, firstField) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ name: "", customer: "", volumes: "100, 1000, 5000", target: "", dataMode: "cache_first" as DataMode });
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [choices, setChoices] = useState<Record<number, FieldName | null>>({});
  const step: Step = preview ? "columns" : "details";

  const volumes = form.volumes
    .split(/[,\s]+/)
    .filter(Boolean)
    .map(Number);
  const volumesValid = volumes.length > 0 && volumes.length <= 5 && volumes.every((v) => Number.isInteger(v) && v > 0);

  const pick = (candidate: File | undefined) => {
    if (!candidate) return;
    const ext = candidate.name.toLowerCase().split(".").pop() ?? "";
    if (!["xlsx", "csv", "tsv"].includes(ext)) return setFileError("Choose an .xlsx, .csv or .tsv file.");
    if (candidate.size > MAX_BYTES) return setFileError("The file is larger than 5 MB.");
    setFileError(null);
    setFile(candidate);
  };

  // Create the project once, then upload; a failed upload keeps the project so the user
  // can pick another file without creating a duplicate.
  const start = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("Add the customer BOM first");
      let pid = projectId;
      if (!pid) {
        const project = await unwrap(
          api.POST("/api/v1/projects", {
            body: {
              name: form.name.trim(),
              customer: form.customer.trim() || null,
              build_quantities: volumes,
              target_ship_date: form.target || null,
              currency: "USD",
              data_mode: form.dataMode,
            },
          }),
        );
        pid = project.id;
        setProjectId(pid);
        void queryClient.invalidateQueries({ queryKey: ["projects"] });
      }
      const body = new FormData();
      body.append("file", file);
      const response = await fetch(`/api/v1/projects/${pid}/bom`, { method: "POST", body, headers: { "X-Demo-Role": getRole() } });
      const json = await response.json();
      if (!response.ok) throw new Error(json?.error?.message ?? "Upload failed");
      return json as Preview;
    },
    onSuccess: (data) => {
      setPreview(data);
      setChoices(Object.fromEntries(data.proposed_mapping.map((m) => [m.column_index, m.field ?? null])));
    },
  });

  const confirm = useMutation({
    mutationFn: () => {
      if (!preview || !projectId) throw new Error("Upload the BOM first");
      return unwrap(
        api.PUT("/api/v1/projects/{pid}/bom/mapping", {
          params: { path: { pid: projectId } },
          body: { upload_id: preview.upload_id, mapping: mappingChanges(preview.proposed_mapping, choices) },
        }),
      );
    },
    onSuccess: (accepted) => {
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      router.push(`/projects/${projectId}?job=${accepted.job_id}`);
    },
  });

  const clashes = clashingColumns(choices);
  const mapped = Object.values(choices).filter(Boolean).length;
  const hasMpn = Object.values(choices).includes("mpn");
  const hasQty = Object.values(choices).includes("qty_per");
  const current = step === "details" ? (file ? 1 : 0) : 2;

  return (
    <section aria-labelledby="new-quote-title" className="flex min-h-0 flex-1 flex-col">
      <header className="flex items-center gap-3 border-b border-rule px-5 py-3.5">
        <span className="chip flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-mask">
          <svg aria-hidden viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round">
            <path d="M12 5v14M5 12h14" />
          </svg>
        </span>
        <div>
          <h2 id="new-quote-title" className="text-[0.9375rem] font-semibold">
            New quote
          </h2>
          <p className="text-xs text-ink-3">From a customer BOM: details, file, columns</p>
        </div>
      </header>

      <ol className="flex flex-wrap items-center gap-x-2 gap-y-1 px-5 pt-4" aria-label="New quote steps">
        {STEPS.map((label, i) => (
          <li key={label} className="flex items-center gap-2" aria-current={i === current ? "step" : undefined}>
            {i > 0 && <span aria-hidden className="h-px w-4 bg-rule-strong" />}
            <span
              className={clsx(
                "text-[0.6875rem] font-semibold tracking-[0.1em] uppercase",
                i < current ? "text-ink-2" : i === current ? "text-mask" : "text-ink-3",
              )}
            >
              {i + 1} {label}
            </span>
          </li>
        ))}
      </ol>

      {step === "details" ? (
        <form
          className="flex min-h-0 flex-1 flex-col"
          onSubmit={(e) => {
            e.preventDefault();
            start.mutate();
          }}
        >
          <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-5 py-4">
            <Field
              ref={firstField}
              label="Project name"
              required
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              disabled={projectId !== null}
            />
            <Field label="Customer" value={form.customer} onChange={(e) => setForm({ ...form, customer: e.target.value })} disabled={projectId !== null} />
            <Field
              label="Build quantities"
              hint={volumesValid ? "Up to five, comma separated. The first one drives recommendations." : "Enter one to five whole numbers, e.g. 100, 1000, 5000."}
              value={form.volumes}
              onChange={(e) => setForm({ ...form, volumes: e.target.value })}
              aria-invalid={!volumesValid}
              disabled={projectId !== null}
            />
            <Field
              label="Target ship date"
              type="date"
              hint="Lead times that would miss it are flagged."
              value={form.target}
              onChange={(e) => setForm({ ...form, target: e.target.value })}
              disabled={projectId !== null}
            />
            <label className="flex flex-col gap-1 text-sm">
              <span className="label">Distributor prices</span>
              <select
                value={form.dataMode}
                onChange={(e) => setForm({ ...form, dataMode: e.target.value as DataMode })}
                disabled={projectId !== null}
                className="w-full min-w-0 rounded-md border border-rule-strong bg-silk px-3 py-2 text-base text-ink"
              >
                <option value="cache_first">Saved prices first, live lookup for the rest</option>
                <option value="live_first">Live lookup for every part</option>
              </select>
            </label>

            <DropZone file={file} onPick={pick} />
            {fileError && <ErrorNote error={fileError} />}
            {projectId && !start.isPending && (
              <p className="text-xs text-ink-3">The project is created. Choose another file to try the upload again.</p>
            )}
            <ErrorNote error={start.error} />
          </div>
          <div className="border-t border-rule px-5 pt-3 pb-4">
            <Button
              variant="primary"
              type="submit"
              className="min-h-11 w-full"
              disabled={start.isPending || !form.name.trim() || !file || !volumesValid}
            >
              {start.isPending ? "Reading the BOM…" : projectId ? "Upload the BOM" : "Create and upload"}
            </Button>
            <p className="mt-2 text-center text-xs text-ink-3">Next you check how its columns map, then the analysis runs.</p>
          </div>
        </form>
      ) : (
        preview && (
          <div className="flex min-h-0 flex-1 flex-col">
            <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-5 py-4">
              <div className="flex items-center gap-3 rounded-md border border-mask/45 bg-mask-tint px-3.5 py-3">
                <FileIcon />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold">{preview.filename}</p>
                  <p className="text-xs text-ink-3">
                    Sheet “{preview.selected_sheet}” · header on row {preview.header_row} · {preview.data_rows} rows
                  </p>
                </div>
              </div>
              {preview.warnings.map((w) => (
                <p key={w} className="rounded-md bg-medium-tint px-3 py-2 text-sm text-medium">
                  {w}
                </p>
              ))}

              <div className="flex items-baseline justify-between gap-3">
                <p className="label">Check how the columns map</p>
                <span className="text-xs text-ink-3">
                  {mapped} of {preview.proposed_mapping.length} mapped
                </span>
              </div>
              <ul className="flex flex-col">
                {preview.proposed_mapping.map((m) => {
                  const choice = choices[m.column_index] ?? null;
                  const sample = preview.preview_rows.map((row) => row[m.column_index]).find(Boolean);
                  const changed = choice !== (m.field ?? null);
                  return (
                    <li key={m.column_index} className="flex flex-col gap-1.5 border-b border-rule py-2.5 last:border-b-0">
                      <div className="flex items-baseline justify-between gap-3">
                        <span className="truncate text-sm font-semibold">{m.header || `Column ${m.column_index + 1}`}</span>
                        <span
                          className={clsx(
                            "shrink-0 rounded-sm px-1.5 py-0.5 text-[0.625rem] font-semibold tracking-[0.1em] uppercase",
                            changed ? "bg-mask-tint text-mask" : m.method === "LLM" ? "bg-gold-tint text-gold" : "bg-low-tint text-ink-2",
                          )}
                          title={m.reason ?? undefined}
                        >
                          {changed ? METHOD_LABEL.USER : (METHOD_LABEL[m.method] ?? m.method)}
                        </span>
                      </div>
                      <select
                        aria-label={`Field for ${m.header || `column ${m.column_index + 1}`}`}
                        value={choice ?? ""}
                        onChange={(e) => setChoices({ ...choices, [m.column_index]: (e.target.value || null) as FieldName | null })}
                        className={clsx(
                          "w-full rounded-md border bg-silk px-2.5 py-1.5 text-sm",
                          clashes.has(m.column_index) ? "border-blocker" : choice ? "border-rule-strong text-mask" : "border-rule-strong text-ink-3",
                        )}
                      >
                        <option value="">Ignore this column</option>
                        {FIELDS.map((f) => (
                          <option key={f.value} value={f.value}>
                            {f.label}
                          </option>
                        ))}
                      </select>
                      {sample && <span className="truncate text-xs text-ink-3">e.g. {sample}</span>}
                    </li>
                  );
                })}
              </ul>
              {clashes.size > 0 && <ErrorNote error="Two columns are mapped to the same field. Choose one." />}
              {(!hasMpn || !hasQty) && (
                <p className="rounded-md bg-medium-tint px-3 py-2 text-sm text-medium">
                  Map {!hasMpn && "a part number column"}
                  {!hasMpn && !hasQty && " and "}
                  {!hasQty && "a quantity column"} to price the BOM.
                </p>
              )}
              <ErrorNote error={confirm.error} />
            </div>
            <div className="flex flex-col gap-2 border-t border-rule px-5 pt-3 pb-4">
              <Button
                variant="primary"
                className="min-h-11 w-full"
                onClick={() => confirm.mutate()}
                disabled={confirm.isPending || clashes.size > 0 || !hasMpn || !hasQty}
              >
                {confirm.isPending ? "Starting the analysis…" : "Confirm and analyze"}
              </Button>
              <Button variant="quiet" onClick={() => setPreview(null)} disabled={confirm.isPending}>
                Use a different file
              </Button>
            </div>
          </div>
        )
      )}
    </section>
  );
});

function DropZone({ file, onPick }: { file: File | null; onPick: (file: File | undefined) => void }) {
  const [over, setOver] = useState(false);
  return (
    <label
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        onPick(e.dataTransfer.files[0]);
      }}
      className={clsx(
        "flex cursor-pointer flex-col items-center gap-1.5 rounded-lg border border-dashed px-4 py-5 text-center transition-colors focus-within:ring-2 focus-within:ring-mask",
        file || over ? "border-mask bg-mask-tint" : "border-mask/50 bg-mask-tint/50 hover:bg-mask-tint",
      )}
    >
      {file ? <FileIcon /> : <UploadIcon />}
      <span className="text-sm font-semibold text-mask">{file ? file.name : "Drop the customer BOM here"}</span>
      <span className="text-xs text-ink-3">
        {file ? `${(file.size / 1024).toFixed(0)} KB · click to choose another` : "or click to choose · .xlsx .csv .tsv · up to 5 MB"}
      </span>
      <input type="file" accept={ACCEPT} className="sr-only" onChange={(e) => onPick(e.target.files?.[0])} />
    </label>
  );
}

function UploadIcon() {
  return (
    <svg aria-hidden viewBox="0 0 24 24" className="h-7 w-7 text-mask" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 16V4M7 9l5-5 5 5M4 16v4h16v-4" />
    </svg>
  );
}

function FileIcon() {
  return (
    <svg aria-hidden viewBox="0 0 24 24" className="h-5 w-5 shrink-0 text-mask" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinejoin="round">
      <path d="M6 2h9l5 5v15H6z" />
      <path d="M14 2v6h6" />
    </svg>
  );
}
