"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { usePathname } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, getRole, unwrap } from "@/lib/api/client";
import { streamEvents } from "@/lib/sse";
import { useEvidence } from "./fact";
import { Button, ErrorNote } from "./ui";

type Citation = { evidence_id: string; label: string };
type Turn = {
  role: "user" | "assistant";
  content: string;
  about?: string;
  tools: string[];
  citations: Citation[];
  grounded: boolean | null;
  unverified: string[];
  pending?: boolean;
  error?: string;
};

/** Something on the page the user pressed "Ask" on: it frames the next questions. */
export type AskContext = {
  key: string;
  label: string;
  detail?: string;
  suggestions: string[];
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

/** Suggested questions for the page the user is on (the copilot can answer all of them). */
const PAGE_SUGGESTIONS: [RegExp, string[]][] = [
  [/\/bom$/, ["Which lines have data problems I must fix before quoting?", "Which lines are single-sourced?"]],
  [/\/risks$/, ["Which blocker can I clear fastest?", "Which parts threaten delivery by the target date?"]],
  [/\/impact$/, ["What is the cost at 1000 boards and how much is MOQ excess?", "Where would ordering more save money?"]],
  [/\/alternatives$/, ["Which alternates are drop-in replacements?", "Which risky parts have no alternate yet?"]],
  [/\/quote$/, ["What still blocks finalizing this quote?", "Which risks were waived and why?"]],
  [/\/activity$/, ["Which risks were waived and why?", "Which parts block this quote and why?"]],
  [/.*/, ["Which parts block this quote and why?", "Why is 1,000 boards cheaper per board?"]],
];

const COLLAPSED_KEY = "quotelens.copilot.collapsed";

// ── Shared state: lets any card on the page send its context to the pane ─────────
type CopilotState = {
  context: AskContext | null;
  askAbout: (context: AskContext) => void;
  clearContext: () => void;
  collapsed: boolean;
  setCollapsed: (collapsed: boolean) => void;
  mobileOpen: boolean;
  setMobileOpen: (open: boolean) => void;
  focusToken: number;
};

const CopilotContext = createContext<CopilotState | null>(null);

export function useCopilot(): CopilotState {
  const state = useContext(CopilotContext);
  if (!state) throw new Error("useCopilot must be used inside CopilotProvider");
  return state;
}

export function CopilotProvider({ children }: { children: React.ReactNode }) {
  const [context, setContext] = useState<AskContext | null>(null);
  const [collapsed, setCollapsedState] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [focusToken, setFocusToken] = useState(0);

  useEffect(() => {
    try {
      setCollapsedState(localStorage.getItem(COLLAPSED_KEY) === "1");
    } catch {
      // Storage blocked: start expanded.
    }
  }, []);

  const setCollapsed = useCallback((next: boolean) => {
    setCollapsedState(next);
    try {
      localStorage.setItem(COLLAPSED_KEY, next ? "1" : "0");
    } catch {
      // Storage blocked: the choice lasts for this page view.
    }
  }, []);

  const askAbout = useCallback(
    (next: AskContext) => {
      setContext(next);
      setCollapsed(false);
      setMobileOpen(true);
      setFocusToken((n) => n + 1);
    },
    [setCollapsed],
  );

  return (
    <CopilotContext.Provider
      value={{
        context,
        askAbout,
        clearContext: () => setContext(null),
        collapsed,
        setCollapsed,
        mobileOpen,
        setMobileOpen,
        focusToken,
      }}
    >
      {children}
    </CopilotContext.Provider>
  );
}

/** "Ask" on a card: sends that item to the copilot pane as the subject of the next questions. */
export function AskButton({ context, onAsk }: { context: AskContext; onAsk?: () => void }) {
  const copilot = useCopilot();
  const active = copilot.context?.key === context.key;
  return (
    <button
      type="button"
      onClick={() => {
        copilot.askAbout(context);
        onAsk?.();
      }}
      aria-pressed={active}
      title={`Ask the copilot about ${context.label}`}
      className={clsx(
        "inline-flex min-h-8 items-center gap-1.5 rounded-full border px-3 text-[0.6875rem] font-semibold tracking-[0.12em] uppercase transition-colors active:translate-y-px",
        active ? "border-gold/50 bg-gold-tint text-gold" : "border-mask/35 bg-mask-tint text-mask hover:border-mask/70",
      )}
    >
      <svg aria-hidden viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinejoin="round">
        <path d="M4 5h16v11H9l-5 4z" />
      </svg>
      {active ? "Asking" : "Ask"}
    </button>
  );
}

// ── The pane ────────────────────────────────────────────────────────────────────

/**
 * The copilot, docked on the right of every project page (large screens). It can fold to
 * a slim strip; "Ask" on any card opens it again. On smaller screens a floating button
 * opens the same conversation as a full-height layer.
 */
export function CopilotPane({ projectId }: { projectId: string }) {
  const copilot = useCopilot();
  const chat = useChat(projectId);

  return (
    <>
      <aside
        aria-label="Copilot"
        className={clsx(
          "sticky top-[61px] z-10 hidden h-[calc(100dvh-61px)] shrink-0 self-start border-l border-rule lg:flex",
          copilot.collapsed ? "w-14" : "w-[360px] xl:w-[400px]",
        )}
        style={{ background: "var(--panel-bg)" }}
      >
        {copilot.collapsed ? (
          <button
            type="button"
            onClick={() => copilot.setCollapsed(false)}
            aria-label="Open the copilot"
            className="flex w-full flex-col items-center gap-3 pt-5 text-mask transition-colors hover:bg-mask-tint/50"
          >
            <SparkIcon />
            <span className="label [writing-mode:vertical-rl]">Ask copilot</span>
          </button>
        ) : (
          <Conversation chat={chat} onCollapse={() => copilot.setCollapsed(true)} />
        )}
      </aside>

      <div className="lg:hidden">
        {!copilot.mobileOpen && (
          <button
            type="button"
            onClick={() => copilot.setMobileOpen(true)}
            className="metal fixed right-4 bottom-4 z-40 inline-flex min-h-12 items-center gap-2 rounded-full px-5 text-xs font-semibold tracking-[0.12em] uppercase"
          >
            <SparkIcon /> Ask copilot
          </button>
        )}
        {copilot.mobileOpen &&
          typeof document !== "undefined" &&
          createPortal(
            // lg:hidden on the layer itself: a portal escapes the wrapper's lg:hidden.
            <div className="fixed inset-0 z-50 flex flex-col bg-silk lg:hidden" role="dialog" aria-label="Copilot">
              <Conversation chat={chat} onCollapse={() => copilot.setMobileOpen(false)} closeLabel="Close the copilot" />
            </div>,
            document.body,
          )}
      </div>
    </>
  );
}

function useChat(projectId: string) {
  const copilot = useCopilot();
  const queryClient = useQueryClient();
  const [turns, setTurns] = useState<Turn[]>([]);

  const session = useQuery({
    queryKey: ["chat-session", projectId],
    staleTime: Infinity,
    queryFn: () => unwrap(api.POST("/api/v1/projects/{pid}/chat/sessions", { params: { path: { pid: projectId } }, body: {} })),
  });

  const ask = useMutation({
    mutationFn: async ({ text, about }: { text: string; about: AskContext | null }) => {
      const sid = session.data?.id;
      if (!sid) throw new Error("The chat session is not ready yet");
      setTurns((t) => [
        ...t,
        { role: "user", content: text, about: about?.label, tools: [], citations: [], grounded: null, unverified: [] },
        { role: "assistant", content: "", tools: [], citations: [], grounded: null, unverified: [], pending: true },
      ]);
      // The subject travels with the question, so the copilot looks up the right part.
      const content = about ? `About ${about.label}${about.detail ? ` (${about.detail})` : ""}: ${text}` : text;
      const response = await fetch(`/api/v1/projects/${projectId}/chat/sessions/${sid}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Demo-Role": getRole() },
        body: JSON.stringify({ content }),
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
    ask.mutate({ text: trimmed, about: copilot.context });
  };

  const reset = () => {
    setTurns([]);
    copilot.clearContext();
    void queryClient.invalidateQueries({ queryKey: ["chat-session", projectId] });
  };

  return { turns, session, ask, submit, reset };
}

type Chat = ReturnType<typeof useChat>;

function Conversation({ chat, onCollapse, closeLabel = "Fold the copilot" }: { chat: Chat; onCollapse: () => void; closeLabel?: string }) {
  const copilot = useCopilot();
  const evidence = useEvidence();
  const pathname = usePathname();
  const [question, setQuestion] = useState("");
  const scroller = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const { turns, session, ask } = chat;

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight });
  }, [turns]);

  // "Ask" on a card puts the cursor in the question box.
  useEffect(() => {
    if (copilot.focusToken === 0) return;
    const frame = requestAnimationFrame(() => input.current?.focus());
    return () => cancelAnimationFrame(frame);
  }, [copilot.focusToken]);

  const suggestions =
    copilot.context?.suggestions ?? PAGE_SUGGESTIONS.find(([pattern]) => pattern.test(pathname))?.[1] ?? [];
  const send = (text: string) => {
    chat.submit(text);
    setQuestion("");
  };

  return (
    <div className="flex min-h-0 w-full flex-1 flex-col">
      <header className="flex items-center justify-between gap-3 border-b border-rule px-4 py-3.5">
        <div className="flex min-w-0 items-center gap-3">
          <span className="chip flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-mask">
            <SparkIcon />
          </span>
          <div className="min-w-0">
            <h2 className="text-[0.9375rem] font-semibold">Copilot</h2>
            <p className="truncate text-xs text-ink-3">Answers only from this project, with sources</p>
          </div>
        </div>
        <div className="flex shrink-0 gap-1">
          <button
            type="button"
            onClick={chat.reset}
            title="New conversation"
            aria-label="New conversation"
            className="chip flex h-8 w-8 items-center justify-center rounded-md text-ink-3 hover:text-ink"
          >
            <svg aria-hidden viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round">
              <path d="M12 5v14M5 12h14" />
            </svg>
          </button>
          <button
            type="button"
            onClick={onCollapse}
            title={closeLabel}
            aria-label={closeLabel}
            className="chip flex h-8 w-8 items-center justify-center rounded-md text-ink-3 hover:text-ink"
          >
            <svg aria-hidden viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="4" width="18" height="16" rx="2" />
              <path d="M15 4v16M8 10l2 2-2 2" />
            </svg>
          </button>
        </div>
      </header>

      <div ref={scroller} className="relative min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-4">
        <ErrorNote error={session.error} />
        {turns.length === 0 && !copilot.context && (
          <p className="text-sm text-ink-2">
            Ask about parts, prices, risks, alternates or cost. Press <span className="font-semibold text-mask">Ask</span> on any risk,
            line or alternate to bring it here.
          </p>
        )}
        {turns.map((turn, i) =>
          turn.role === "user" ? (
            <div key={i} className="ml-8 flex flex-col items-end gap-1">
              {turn.about && <span className="text-[0.6875rem] text-ink-3">About {turn.about}</span>}
              <p className="rounded-[10px_10px_2px_10px] border border-mask/25 bg-mask-tint px-3 py-2 text-sm">{turn.content}</p>
            </div>
          ) : (
            <article key={i} className="space-y-2 text-sm">
              {turn.tools.length > 0 && (
                <ul className="flex flex-wrap gap-1.5" aria-label="Data the copilot looked at">
                  {turn.tools.map((tool, j) => (
                    <li key={j} className="rounded-sm bg-low-tint px-1.5 py-0.5 text-xs text-ink-3">
                      {TOOL_LABELS[tool] ?? tool}
                    </li>
                  ))}
                </ul>
              )}
              {turn.pending && !turn.content && <p className="text-ink-3">Checking the project data…</p>}
              {turn.content && <AnswerText text={stripCitations(turn.content)} />}
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
              {turn.grounded && (
                <p className="flex items-center gap-1.5 text-[0.6875rem] text-ink-3">
                  <svg
                    aria-hidden
                    viewBox="0 0 24 24"
                    className="h-3.5 w-3.5 text-mask"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth={2.2}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="m5 12 5 5 9-10" />
                  </svg>
                  Every number checked against project data
                </p>
              )}
            </article>
          ),
        )}
      </div>

      <div className="border-t border-rule px-4 pt-3 pb-4">
        {copilot.context && (
          <span className="mb-2.5 inline-flex max-w-full items-center gap-2 rounded-md border border-gold/40 bg-gold-tint px-2.5 py-1 text-xs text-gold">
            <span className="truncate">
              About <b>{copilot.context.label}</b>
              {copilot.context.detail && <span className="opacity-80"> · {copilot.context.detail}</span>}
            </span>
            <button
              type="button"
              onClick={copilot.clearContext}
              aria-label="Stop asking about this"
              className="shrink-0 text-base leading-none opacity-70 hover:opacity-100"
            >
              ×
            </button>
          </span>
        )}
        {suggestions.length > 0 && (
          <div className="mb-3 flex flex-col gap-1.5">
            <p className="label">{copilot.context ? "About this item" : "Ask about this page"}</p>
            {suggestions.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => send(s)}
                disabled={ask.isPending || !session.data}
                className="chip rounded-md px-3 py-2 text-left text-sm text-ink transition-colors hover:text-mask active:translate-y-px disabled:opacity-50"
              >
                {s}
              </button>
            ))}
          </div>
        )}
        <form
          className="flex items-center gap-2 rounded-[10px] border border-rule-strong bg-silk p-1.5 pl-3 focus-within:border-mask"
          onSubmit={(e) => {
            e.preventDefault();
            send(question);
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
            placeholder={copilot.context ? `Ask about ${copilot.context.label}…` : "Ask about this BOM…"}
            className="min-w-0 flex-1 bg-transparent py-1 text-sm text-ink outline-none placeholder:text-ink-3"
          />
          <Button variant="primary" type="submit" className="min-h-8 px-3" disabled={ask.isPending || !question.trim() || !session.data}>
            Ask
          </Button>
        </form>
      </div>
    </div>
  );
}

/**
 * Answers arrive as light markdown: paragraphs, "* " or "- " bullets and **bold**. Render
 * just that (no HTML from the model is ever injected).
 */
function AnswerText({ text }: { text: string }) {
  const blocks: { list: boolean; lines: string[] }[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();
    const bullet = /^\s*[*-]\s+/.exec(line);
    const last = blocks[blocks.length - 1];
    if (!line.trim()) {
      blocks.push({ list: false, lines: [] });
    } else if (bullet) {
      const item = line.slice(bullet[0].length);
      if (last?.list) last.lines.push(item);
      else blocks.push({ list: true, lines: [item] });
    } else if (last && !last.list && last.lines.length) {
      last.lines.push(line);
    } else {
      blocks.push({ list: false, lines: [line] });
    }
  }
  return (
    <div className="space-y-2 leading-relaxed">
      {blocks
        .filter((b) => b.lines.length)
        .map((b, i) =>
          b.list ? (
            <ul key={i} className="list-disc space-y-1 pl-5 marker:text-ink-3">
              {b.lines.map((l, j) => (
                <li key={j}>{inline(l)}</li>
              ))}
            </ul>
          ) : (
            <p key={i}>{inline(b.lines.join(" "))}</p>
          ),
        )}
    </div>
  );
}

function inline(text: string): React.ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") && part.length > 4 ? (
      <strong key={i} className="font-semibold">
        {part.slice(2, -2)}
      </strong>
    ) : (
      part
    ),
  );
}

function SparkIcon() {
  return (
    <svg aria-hidden viewBox="0 0 24 24" className="h-[18px] w-[18px] shrink-0" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round">
      <path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6" />
    </svg>
  );
}

/** Citation markers are shown as source chips below the answer instead of inline ids. */
export function stripCitations(text: string): string {
  return text.replace(/\s?\[E:[^\]]+\]/g, "");
}
