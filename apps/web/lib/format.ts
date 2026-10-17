/** Display formatting. Decimal strings from the API are formatted without float rounding
 * surprises for the precision shown. */

export function toNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

/** Cents for amounts of one unit or more ($524.89); sub-unit part prices keep up to four
 * decimals ($0.0047), where the extra digits change a quote. */
export function money(value: string | number | null | undefined, currency = "USD", digits = 2): string {
  const n = toNumber(value);
  if (n === null) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: digits,
    maximumFractionDigits: Math.abs(n) >= 1 ? digits : Math.max(digits, 4),
  }).format(n);
}

export function quantity(value: string | number | null | undefined): string {
  const n = toNumber(value);
  if (n === null) return "—";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 3 }).format(n);
}

export function percent(fraction: string | number | null | undefined, digits = 0): string {
  const n = toNumber(fraction);
  if (n === null) return "—";
  return `${(n * 100).toFixed(digits)}%`;
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export function sentence(value: string): string {
  const lower = value.replaceAll("_", " ").toLowerCase();
  return lower.charAt(0).toUpperCase() + lower.slice(1);
}
