import type { Schemas } from "@/lib/api/client";

/** Column-mapping labels shared by the new-quote panel and the project upload page. */

export type FieldName = NonNullable<Schemas["MappingColumn"]["field"]>;

export const FIELDS: { value: FieldName; label: string }[] = [
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

export const METHOD_LABEL: Record<string, string> = {
  ALIAS: "Recognized header",
  LLM: "Suggested by AI",
  USER: "Set by you",
  NONE: "Not mapped",
};

/** Only the columns the user changed are sent; the rest keep the proposed mapping. */
export function mappingChanges(
  proposed: Schemas["MappingColumn"][],
  choices: Record<number, FieldName | null>,
): { column_index: number; field: FieldName | null }[] {
  return proposed
    .filter((m) => (choices[m.column_index] ?? null) !== (m.field ?? null))
    .map((m) => ({ column_index: m.column_index, field: choices[m.column_index] ?? null }));
}

/** A field may be chosen for one column only: returns the columns that clash. */
export function clashingColumns(choices: Record<number, FieldName | null>): Set<number> {
  const firstColumn = new Map<FieldName, number>();
  const clashes = new Set<number>();
  for (const [index, field] of Object.entries(choices)) {
    if (!field) continue;
    const column = Number(index);
    const first = firstColumn.get(field);
    if (first === undefined) firstColumn.set(field, column);
    else clashes.add(column);
  }
  return clashes;
}
