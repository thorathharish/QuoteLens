import { describe, expect, it } from "vitest";
import { clashingColumns, mappingChanges } from "@/lib/mapping";

const proposed = [
  { column_index: 0, header: "Item", field: null, confidence: 0, method: "NONE" as const },
  { column_index: 1, header: "MPN", field: "mpn" as const, confidence: 1, method: "ALIAS" as const },
  { column_index: 2, header: "Qty", field: "qty_per" as const, confidence: 1, method: "ALIAS" as const },
];

describe("mapping", () => {
  it("sends only the columns the user changed", () => {
    expect(mappingChanges(proposed, { 0: null, 1: "mpn", 2: "qty_per" })).toEqual([]);
    expect(mappingChanges(proposed, { 0: "notes", 1: "mpn", 2: null })).toEqual([
      { column_index: 0, field: "notes" },
      { column_index: 2, field: null },
    ]);
  });

  it("flags a field chosen for two columns, keeping the first", () => {
    expect([...clashingColumns({ 0: "mpn", 1: "mpn", 2: "qty_per" })]).toEqual([1]);
    expect(clashingColumns({ 0: null, 1: "mpn", 2: null }).size).toBe(0);
  });
});
