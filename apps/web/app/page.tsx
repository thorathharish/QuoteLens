const CAPABILITIES = [
  "BOM upload & quick quote",
  "Distributor pricing & component details",
  "Explainable BOM risk",
  "Manufacturing impact",
  "Evidence-backed copilot",
  "Alternative-part investigation",
] as const;

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center gap-8 px-6 py-16">
      <header className="space-y-3">
        <p className="text-sm font-medium uppercase tracking-wide text-neutral-500">
          AI Builder Cup 2026 · Manufacturing
        </p>
        <h1 className="text-4xl font-semibold tracking-tight">QuoteLens</h1>
        <p className="text-lg text-neutral-600 dark:text-neutral-400">
          Turn a BOM into a quote you can defend. Every number is labelled Actual, Calculated,
          Assumed, Unavailable or Recommended, and linked to its evidence.
        </p>
      </header>
      <ul className="grid gap-2 sm:grid-cols-2">
        {CAPABILITIES.map((capability) => (
          <li
            key={capability}
            className="rounded-md border border-neutral-200 px-4 py-3 text-sm dark:border-neutral-800"
          >
            {capability}
          </li>
        ))}
      </ul>
      <p className="text-sm text-neutral-500">Workspace coming in Phase 8.</p>
    </main>
  );
}
