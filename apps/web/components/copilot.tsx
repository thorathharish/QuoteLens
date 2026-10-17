"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { useEffect, useRef, useState } from "react";
import { api, getRole, unwrap } from "@/lib/api/client";
import { streamEvents } from "@/lib/sse";
import { useEvidence } from "./fact";
import { Button, ErrorNote } from "./ui";

type Citation = { evidence_id: string; label: string };
type Turn = {
  role: "user" | "assistant";
  content: string;
  tools: string[];
  citations: Citation[];
  grounded: boolean | null;
  unverified: string[];
  pending?: boolean;
  error?: string;
};

const TOOL_LABELS: Record<string, string> = {
  get_project_summary: "Read project summary",
  search_lines: "Searched BOM lines",
  get_line: "Read line details",
  get_offers: "Compared distributor offers",
  list_risks: "Read risks",
  get_impact: "Calculated cost impact",
  simulate: "Ran a what-if",
  get_evidence: "Opened a source record",
};

const STARTERS = [
  "Which parts block this quote and why?",
  "Which parts threaten delivery by the target date?",
  "What is the cost at 1000 boards and how much is MOQ excess?",
];

export function CopilotDrawer({ projectId, open, onClose }: { projectId: string; open: boolean; onClose: () => void }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const scroller = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);

  // Opening the drawer puts the cursor in the question box (after the frame in which it
  // stops being invisible: hidden elements cannot take focus).
  useEffect(() => {
    if (!open) return;
    const frame = requestAnimationFrame(() => input.current?.focus());
    return () => cancelAnimationFrame(frame);
  }, [open]);
  const evidence = useEvidence();

  const session = useQuery({
    queryKey: ["chat-session", projectId],
    enabled: open,
    staleTime: Infinity,
    queryFn: () => unwrap(api.POST("/api/v1/projects/{pid}/chat/sessions", { params: { path: { pid: projectId } }, body: {} })),
  });

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight });
  }, [turns]);

  const ask = useMutation({
    mutationFn: async (text: string) => {
      const sid = session.data?.id;
      if (!sid) throw new Error("The chat session is not ready yet");
      setTurns((t) => [
        ...t,
        { role: "user", content: text, tools: [], citations: [], grounded: null, unverified: [] },
        { role: "assistant", content: "", tools: [], citations: [], grounded: null, unverified: [], pending: true },
      ]);
      const response = await fetch(`/api/v1/projects/${projectId}/chat/sessions/${sid}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Demo-Role": getRole() },
        body: JSON.stringify({ content: text }),
      });
      const update = (patch: (turn: Turn) => Turn) =>
        setTurns((t) => [...t.slice(0, -1), patch(t[t.length - 1] as Turn)]);
      if (!response.ok) {
        const body = (await response.json().catch(() => ({}))) as { error?: { message?: string } };
        update((turn) => ({ ...turn, pending: false, error: body.error?.message ?? `Request failed (${response.status})` }));
        return;
      }
      for await (const { event, data } of streamEvents(response)) {
        if (event === "tool_start") update((turn) => ({ ...turn, tools: [...turn.tools, String(data.name)] }));
        else if (event === "token") update((turn) => ({ ...turn, content: turn.content + String(data.text ?? "") }));
        else if (event === "citations") update((turn) => ({ ...turn, citations: (data.items as Citation[]) ?? [] }));
        else if (event === "done")
          update((turn) => ({
            ...turn,
            pending: false,
            grounded: Boolean(data.grounded),
            unverified: (data.unverified_numbers as string[]) ?? [],
          }));
        else if (event === "error") update((turn) => ({ ...turn, pending: false, error: String(data.message ?? "Copilot error") }));
      }
    },
  });

  const submit = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || ask.isPending) return;
    setQuestion("");
    ask.mutate(trimmed);
  };

  return (
    // inert (not aria-hidden) keeps the closed drawer out of the tab order too.
    <aside
      aria-label="Copilot"
      inert={!open}
      className={clsx(
        "fixed inset-y-0 right-0 z-40 flex w-full max-w-md flex-col border-l border-rule bg-silk",
        // Visible at once when opening (so focus can land); hidden only after the slide-out.
        open
          ? "visible translate-x-0 shadow-[var(--shadow-overlay)] [transition:transform_200ms]" // taste-skill-ignore: open drawer floats
          : "invisible translate-x-full [transition:transform_200ms,visibility_0s_200ms]",
      )}
    >
      <header className="flex items-start justify-between gap-4 border-b border-rule px-5 py-4">
        <div>
          <h2 className="text-lg font-semibold">Copilot</h2>
          <p className="text-sm text-ink-2">Answers only from this project&apos;s data, with sources.</p>
        </div>
        <button
          onClick={onClose}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-2xl leading-none text-ink-3 transition-colors hover:bg-laminate hover:text-ink"
          aria-label="Close copilot"
        >
          ×
        </button>
      </header>

      <div ref={scroller} className="relative flex-1 space-y-5 overflow-y-auto px-5 py-5">
        <ErrorNote error={session.error} />
        {turns.length === 0 && (
          <div className="space-y-2">
            <p className="text-sm text-ink-2">Ask about parts, prices, risks, alternates or cost. Try:</p>
            {STARTERS.map((s) => (
              <button
                key={s}
                onClick={() => submit(s)}
                className="block w-full rounded-md bg-laminate px-3 py-2.5 text-left text-sm transition-colors hover:bg-mask-tint hover:text-mask active:translate-y-px"
              >
                {s}
              </button>
            ))}
          </div>
        )}
        {turns.map((turn, i) =>
          turn.role === "user" ? (
            <p key={i} className="ml-8 rounded-md bg-mask-tint px-3 py-2 text-sm">
              {turn.content}
            </p>
          ) : (
            <article key={i} className="space-y-2 text-sm">
              {turn.tools.length > 0 && (
                <ul className="flex flex-wrap gap-1.5" aria-label="Data the copilot looked at">
                  {turn.tools.map((tool, j) => (
                    <li key={j} className="rounded-sm bg-low-tint px-1.5 py-0.5 text-xs text-ink-2">
                      {TOOL_LABELS[tool] ?? tool}
                    </li>
                  ))}
                </ul>
              )}
              {turn.pending && !turn.content && <p className="text-ink-3">Checking the project data…</p>}
              {turn.content && <p className="whitespace-pre-wrap leading-relaxed">{stripCitations(turn.content)}</p>}
              {turn.error && <ErrorNote error={turn.error} />}
              {turn.grounded === false && (
                <p className="rounded-md bg-medium-tint px-2.5 py-1.5 text-xs text-medium">
                  Not verified: {turn.unverified.join(", ")} could not be traced to project data. Check before relying on it.
                </p>
              )}
              {turn.citations.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {turn.citations.map((c) => (
                    <button
                      key={c.evidence_id}
                      onClick={() => evidence.open({ evidence_ids: [c.evidence_id] })}
                      className="rounded-sm bg-mask-tint px-1.5 py-0.5 text-xs font-semibold text-mask transition-colors hover:bg-mask hover:text-on-fill"
                    >
                      {c.label}
                    </button>
                  ))}
                </div>
              )}
            </article>
          ),
        )}
      </div>

      <form
        className="flex gap-2 border-t border-rule px-5 py-4"
        onSubmit={(e) => {
          e.preventDefault();
          submit(question);
        }}
      >
        <label className="sr-only" htmlFor="copilot-question">
          Question
        </label>
        <input
          ref={input}
          id="copilot-question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask about this BOM"
          className="min-w-0 flex-1 rounded-md border border-rule-strong bg-silk px-3 py-2"
        />
        <Button variant="primary" type="submit" disabled={ask.isPending || !question.trim() || !session.data}>
          Ask
        </Button>
      </form>
    </aside>
  );
}

/** Citation markers are shown as source chips below the answer instead of inline ids. */
export function stripCitations(text: string): string {
  return text.replace(/\s?\[E:[^\]]+\]/g, "");
}
