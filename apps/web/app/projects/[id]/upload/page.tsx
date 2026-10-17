"use client";

import { useMutation } from "@tanstack/react-query";
import clsx from "clsx";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { Button, ErrorNote, Panel, Tag } from "@/components/ui";
import { api, getRole, unwrap, type Schemas } from "@/lib/api/client";
import { useInvalidateProject } from "@/lib/api/hooks";

type Preview = Schemas["UploadPreview"];
type FieldName = NonNullable<Schemas["MappingColumn"]["field"]>;

const FIELDS: { value: FieldName; label: string }[] = [
  { value: "mpn", label: "Manufacturer part number" },
  { value: "manufacturer", label: "Manufacturer" },
  { value: "qty_per", label: "Quantity per board" },
  { value: "refdes", label: "Reference designators" },
  { value: "description", label: "Description" },
  { value: "cpn", label: "Customer part number" },
  { value: "uom", label: "Unit of measure" },
  { value: "dnp", label: "Do not populate" },
  { value: "fitted", label: "Fitted (yes/no)" },
  { value: "unit_price", label: "Target unit price" },
  { value: "package", label: "Package" },
  { value: "value", label: "Value" },
  { value: "notes", label: "Notes" },
];

const METHOD_LABEL: Record<string, string> = {
  ALIAS: "Recognized header",
  LLM: "Suggested by AI",
  USER: "Set by you",
  NONE: "Not mapped",
};

export default function UploadPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const invalidate = useInvalidateProject(id);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [choices, setChoices] = useState<Record<number, FieldName | null>>({});

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const body = new FormData();
      body.append("file", file);
      const response = await fetch(`/api/v1/projects/${id}/bom`, {
        method: "POST",
        body,
        headers: { "X-Demo-Role": getRole() },
      });
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
      if (!preview) throw new Error("Upload a file first");
      const mapping = preview.proposed_mapping
        .filter((m) => (choices[m.column_index] ?? null) !== (m.field ?? null))
        .map((m) => ({ column_index: m.column_index, field: choices[m.column_index] ?? null }));
      return unwrap(
        api.PUT("/api/v1/projects/{pid}/bom/mapping", {
          params: { path: { pid: id } },
          body: { upload_id: preview.upload_id, mapping },
        }),
      );
    },
    onSuccess: async (accepted) => {
      await invalidate();
      router.push(`/projects/${id}?job=${accepted.job_id}`);
    },
  });

  const used = new Map<FieldName, number>();
  Object.entries(choices).forEach(([col, f]) => f && used.set(f, Number(col)));

  return (
    <div className="flex flex-col gap-6">
      <Panel title="Upload the customer BOM">
        <label
          className={clsx(
            "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-md px-6 py-12 text-center transition-colors focus-within:ring-2 focus-within:ring-mask",
            upload.isPending ? "bg-mask-tint" : "bg-laminate hover:bg-mask-tint",
          )}
        >
          <span className="font-semibold">{upload.isPending ? "Reading the file…" : "Choose an .xlsx, .csv or .tsv file"}</span>
          <span className="text-sm text-ink-2">Up to 5 MB. Title rows above the header are fine.</span>
          <input
            type="file"
            accept=".xlsx,.csv,.tsv"
            className="sr-only"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) upload.mutate(file);
            }}
          />
        </label>
        <div className="mt-3">
          <ErrorNote error={upload.error} />
        </div>
      </Panel>

      {preview && (
        <Panel
          title={`Map the columns of ${preview.filename}`}
          action={
            <span className="text-sm text-ink-2">
              Sheet {preview.selected_sheet}, header on row {preview.header_row}, {preview.data_rows} data rows
            </span>
          }
        >
          {preview.warnings.map((w) => (
            <p key={w} className="mb-3 rounded-md bg-medium-tint px-3 py-2 text-sm text-medium">
              {w}
            </p>
          ))}
          <div className="relative overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Column in your file</th>
                  <th>Means</th>
                  <th>How it was mapped</th>
                  <th>First values</th>
                </tr>
              </thead>
              <tbody>
                {preview.proposed_mapping.map((m) => {
                  const choice = choices[m.column_index] ?? null;
                  const changed = choice !== (m.field ?? null);
                  const clash = choice !== null && used.get(choice) !== m.column_index;
                  return (
                    <tr key={m.column_index}>
                      <td className="font-semibold">{m.header || `Column ${m.column_index + 1}`}</td>
                      <td>
                        <select
                          aria-label={`Field for ${m.header}`}
                          value={choice ?? ""}
                          onChange={(e) =>
                            setChoices({ ...choices, [m.column_index]: (e.target.value || null) as FieldName | null })
                          }
                          className={clsx(
                            "rounded-md border bg-silk px-2 py-1 text-sm",
                            clash ? "border-blocker" : "border-rule-strong",
                          )}
                        >
                          <option value="">Ignore this column</option>
                          {FIELDS.map((f) => (
                            <option key={f.value} value={f.value}>
                              {f.label}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        {changed ? (
                          <Tag tone="mask">Set by you</Tag>
                        ) : (
                          <span className="flex flex-col gap-0.5">
                            <Tag tone={m.method === "LLM" ? "gold" : "neutral"}>{METHOD_LABEL[m.method] ?? m.method}</Tag>
                            {m.reason && <span className="text-xs text-ink-3">{m.reason}</span>}
                          </span>
                        )}
                      </td>
                      <td className="max-w-xs truncate text-ink-2">
                        {preview.preview_rows
                          .slice(0, 3)
                          .map((row) => row[m.column_index])
                          .filter(Boolean)
                          .join(", ")}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="mt-4 flex items-center gap-4">
            <Button variant="primary" onClick={() => confirm.mutate()} disabled={confirm.isPending}>
              {confirm.isPending ? "Starting analysis…" : "Confirm mapping and analyze"}
            </Button>
            <span className="text-sm text-ink-2">Quantity and part number (or description) are required.</span>
          </div>
          <div className="mt-3">
            <ErrorNote error={confirm.error} />
          </div>
        </Panel>
      )}
    </div>
  );
}
