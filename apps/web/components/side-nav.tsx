"use client";

import clsx from "clsx";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { Schemas } from "@/lib/api/client";
import { useAlternatives, useOverview } from "@/lib/api/hooks";
import { STAGES, stageIndex } from "./workspace";

type Status = Schemas["Project"]["status"];
type Tone = "neutral" | "blocker" | "gold";

type Item = {
  href: string;
  label: string;
  description: string;
  icon: keyof typeof ICONS;
  count?: { value: number; tone: Tone; title: string };
};

/**
 * Project navigation: a slim icon rail that opens into a full panel on hover or keyboard
 * focus, and folds back once a section is picked. On phones the same list is a drawer.
 */
export function SideNav({ projectId, status }: { projectId: string; status: Status }) {
  const groups = useGroups(projectId);
  const [open, setOpen] = useState(false);
  // After a pick, stay folded until the pointer leaves, so it does not spring back open.
  const [suppressed, setSuppressed] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const root = useRef<HTMLElement>(null);

  const clear = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  };
  useEffect(() => clear, []);

  const close = () => {
    clear();
    setOpen(false);
  };
  const picked = () => {
    close();
    setSuppressed(true);
    (document.activeElement as HTMLElement | null)?.blur();
  };

  return (
    <nav
      ref={root}
      aria-label="Project sections"
      className="sticky top-[61px] z-20 hidden h-[calc(100dvh-61px)] w-16 shrink-0 self-start lg:block"
      onMouseEnter={() => {
        if (suppressed) return;
        clear();
        timer.current = setTimeout(() => setOpen(true), 150); // ignore a pointer passing by
      }}
      onMouseLeave={() => {
        setSuppressed(false);
        close();
      }}
      onFocus={() => !suppressed && setOpen(true)}
      onBlur={(e) => {
        if (!root.current?.contains(e.relatedTarget as Node | null)) close();
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          close();
          (document.activeElement as HTMLElement | null)?.blur();
        }
      }}
    >
      {/* The panel overlays the page when open, so the content never shifts. */}
      <div
        className={clsx(
          "absolute inset-y-0 left-0 flex flex-col overflow-hidden border-r border-rule bg-laminate-2/95 backdrop-blur-xl transition-[width,box-shadow] duration-200",
          open ? "w-72 shadow-[var(--shadow-overlay)]" : "w-16",
        )}
      >
        <NavBody groups={groups} status={status} expanded={open} onPick={picked} projectId={projectId} />
      </div>
    </nav>
  );
}

/** Phones and tablets: a menu button that opens the same list as a drawer. */
export function MobileNav({ projectId, status }: { projectId: string; status: Status }) {
  const groups = useGroups(projectId);
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <div className="lg:hidden">
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-expanded={open}
        aria-label="Open project menu"
        className="chip flex h-10 w-10 items-center justify-center rounded-lg text-ink"
      >
        <Icon name="menu" />
      </button>
      {/* Portalled to <body>: the frosted header (backdrop-filter) would otherwise become
          the containing block of this fixed layer and clip it to the header's height. */}
      {open &&
        createPortal(
        <div className="fixed inset-0 z-50">
          <button type="button" aria-label="Close menu" className="absolute inset-0 bg-[var(--backdrop)]" onClick={() => setOpen(false)} />
          <nav
            aria-label="Project sections"
            className="absolute inset-y-0 left-0 flex w-80 max-w-[85vw] flex-col border-r border-rule bg-laminate-2 shadow-[var(--shadow-overlay)]"
          >
            <NavBody groups={groups} status={status} expanded onPick={() => setOpen(false)} projectId={projectId} />
          </nav>
        </div>,
          document.body,
        )}
    </div>
  );
}

function NavBody({
  groups,
  status,
  expanded,
  onPick,
  projectId,
}: {
  groups: { title: string; items: Item[] }[];
  status: Status;
  expanded: boolean;
  onPick: () => void;
  projectId: string;
}) {
  const pathname = usePathname();
  const base = `/projects/${projectId}`;
  const step = stageIndex(status);

  return (
    <>
      <div className={clsx("px-4 pt-5", !expanded && "sr-only")}>
        <p className="label whitespace-nowrap">
          Step {step + 1} of {STAGES.length}: {STAGES[step]?.label}
        </p>
        <div className="mt-2 h-1 overflow-hidden rounded-full bg-rule">
          <span className="block h-full bg-mask" style={{ width: `${((step + 1) / STAGES.length) * 100}%` }} />
        </div>
      </div>
      <div className="flex-1 overflow-x-hidden overflow-y-auto px-2 pt-3 pb-4">
        {groups.map((group, g) => (
          <div key={group.title}>
            {expanded ? (
              <p className="label px-3 pt-4 pb-1.5 whitespace-nowrap">{group.title}</p>
            ) : (
              g > 0 && <span aria-hidden className="mx-3 my-3 block h-px bg-rule" />
            )}
            <ul className="flex flex-col gap-0.5">
              {group.items.map((item) => {
                const href = base + item.href;
                const active = item.href === "" ? pathname === base : pathname.startsWith(href);
                return (
                  <li key={item.label}>
                    <Link
                      href={href}
                      onClick={onPick}
                      aria-current={active ? "page" : undefined}
                      title={expanded ? undefined : item.count ? `${item.label} · ${item.count.title}` : item.label}
                      className={clsx(
                        "relative flex min-h-11 items-start gap-3 rounded-md px-3 py-2.5 transition-colors",
                        active ? "bg-mask-tint text-ink" : "text-ink-2 hover:bg-mask-tint/60 hover:text-ink",
                        !expanded && "justify-center px-0",
                      )}
                    >
                      {active && <span aria-hidden className="absolute inset-y-2 -left-2 w-0.5 rounded-full bg-mask" />}
                      <Icon name={item.icon} className={clsx("mt-0.5", active && "text-mask")} />
                      <span className={clsx("min-w-0 flex-1", !expanded && "sr-only")}>
                        <span className="block text-sm font-semibold whitespace-nowrap text-ink">{item.label}</span>
                        <span className="block text-xs leading-snug text-ink-3">{item.description}</span>
                      </span>
                      {item.count &&
                        (expanded ? (
                          <span
                            className={clsx(
                              "shrink-0 rounded-full px-2 py-0.5 text-[0.6875rem] font-bold",
                              item.count.tone === "blocker" && "bg-blocker text-on-fill",
                              item.count.tone === "gold" && "bg-gold-tint text-gold",
                              item.count.tone === "neutral" && "chip text-ink-2",
                            )}
                          >
                            {item.count.value}
                          </span>
                        ) : (
                          item.count.tone === "blocker" && (
                            <span aria-hidden className="status-dot absolute top-2 right-3.5 text-blocker" />
                          )
                        ))}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
    </>
  );
}

function useGroups(projectId: string): { title: string; items: Item[] }[] {
  const overview = useOverview(projectId);
  const alternatives = useAlternatives(projectId);
  const o = overview.data;
  const blockers = o?.risks.unresolved_by_severity?.BLOCKER ?? 0;
  const proposed = alternatives.data?.items.filter((a) => a.status === "PROPOSED").length ?? 0;

  return [
    {
      title: "Understand",
      items: [
        { href: "", label: "Overview", description: "Where the quote stands", icon: "overview" },
        {
          href: "/bom",
          label: "BOM",
          description: "Parts, quantities, data issues",
          icon: "bom",
          count: o ? { value: o.lines, tone: "neutral", title: `${o.lines} lines` } : undefined,
        },
      ],
    },
    {
      title: "Decide",
      items: [
        {
          href: "/risks",
          label: "Risks",
          description: "Why a part could hurt the quote",
          icon: "risks",
          count: blockers
            ? { value: blockers, tone: "blocker", title: `${blockers} blocker${blockers === 1 ? "" : "s"}` }
            : undefined,
        },
        {
          href: "/alternatives",
          label: "Alternatives",
          description: "Replacements to approve",
          icon: "alternatives",
          count: proposed ? { value: proposed, tone: "gold", title: `${proposed} to review` } : undefined,
        },
      ],
    },
    {
      title: "Deliver",
      items: [
        { href: "/impact", label: "Cost impact", description: "MOQ, scrap, price breaks", icon: "cost" },
        { href: "/quote", label: "Quote", description: "Versions, sign-off, Excel", icon: "quote" },
      ],
    },
    {
      title: "History",
      items: [{ href: "/activity", label: "Activity", description: "Who decided what, and why", icon: "activity" }],
    },
  ];
}

const ICONS = {
  overview: "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z",
  bom: "M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01",
  risks: "M12 3 2 20h20L12 3zM12 10v4M12 17h.01",
  alternatives: "M7 4 3 8l4 4M3 8h14M17 12l4 4-4 4M21 16H7",
  cost: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  quote: "M6 2h9l5 5v15H6zM14 2v6h6M9 13h8M9 17h5",
  activity: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v5l3 2",
  menu: "M4 6h16M4 12h16M4 18h16",
};

function Icon({ name, className }: { name: keyof typeof ICONS; className?: string }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      className={clsx("h-[18px] w-[18px] shrink-0", className)}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={ICONS[name]} />
    </svg>
  );
}
