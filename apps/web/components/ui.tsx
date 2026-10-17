"use client";

import clsx from "clsx";
import { forwardRef, useEffect, useRef } from "react";

/** One radius (6px) for controls; panels use 10px. Press feedback on every variant. */
export function Button({
  variant = "secondary",
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "quiet" | "danger" }) {
  return (
    <button
      {...props}
      className={clsx(
        "inline-flex items-center justify-center gap-1.5 rounded-md px-3.5 py-2 text-sm font-semibold transition-[background-color,color,transform] duration-200 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-50 disabled:active:translate-y-0",
        variant === "primary" && "bg-mask text-silk hover:bg-mask-2",
        variant === "secondary" && "bg-laminate-2 text-ink hover:bg-mask-tint hover:text-mask",
        variant === "quiet" && "px-1.5 text-mask hover:bg-mask-tint",
        variant === "danger" && "px-2 text-blocker hover:bg-blocker-tint",
        className,
      )}
    />
  );
}

export const Field = forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string }
>(function Field({ label, hint, className, ...props }, ref) {
  return (
    <label className={clsx("flex flex-col gap-1 text-sm", className)}>
      <span className="font-semibold text-ink-2">{label}</span>
      <input
        ref={ref}
        {...props}
        className="rounded-md border border-rule-strong bg-silk px-3 py-2 text-base text-ink transition-colors placeholder:text-ink-3 hover:border-ink-3"
      />
      {hint && <span className="text-xs text-ink-3">{hint}</span>}
    </label>
  );
});

export function TextArea({
  label,
  ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="font-semibold text-ink-2">{label}</span>
      <textarea
        {...props}
        className="min-h-20 rounded-md border border-rule-strong bg-silk px-3 py-2 text-base text-ink transition-colors placeholder:text-ink-3 hover:border-ink-3"
      />
    </label>
  );
}

const SEVERITY_STYLE: Record<string, string> = {
  BLOCKER: "bg-blocker text-silk",
  HIGH: "bg-high-tint text-high",
  MEDIUM: "bg-medium-tint text-medium",
  LOW: "bg-low-tint text-low",
};

/** Square flags, filled; a blocker is the one solid red on the page. */
export function SeverityTag({ severity }: { severity: string }) {
  const label = { BLOCKER: "Blocker", HIGH: "High", MEDIUM: "Medium", LOW: "Low" }[severity] ?? severity;
  return (
    <span className={clsx("inline-flex rounded-sm px-1.5 py-0.5 text-xs font-semibold", SEVERITY_STYLE[severity])}>
      {label}
    </span>
  );
}

export function Tag({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "mask" | "gold" }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-sm px-1.5 py-0.5 text-xs font-semibold",
        tone === "neutral" && "bg-low-tint text-ink-2",
        tone === "mask" && "bg-mask-tint text-mask",
        tone === "gold" && "bg-gold-tint text-gold",
      )}
    >
      {children}
    </span>
  );
}

/** A silk surface on the laminate ground: the tone step separates it, no outline. */
export function Panel({
  title,
  action,
  children,
  className,
}: {
  title?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={clsx("min-w-0 rounded-[var(--radius-panel)] bg-silk", className)}>
      {(title || action) && (
        <header className="flex items-center justify-between gap-4 px-5 pt-4">
          <h2 className="text-base font-semibold">{title}</h2>
          {action}
        </header>
      )}
      <div className={clsx("px-5 pb-5", title || action ? "pt-3" : "pt-5")}>{children}</div>
    </section>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <span role="status" className="inline-flex items-center gap-2 text-sm text-ink-3">
      <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-rule-strong border-t-mask" aria-hidden />
      {label}
    </span>
  );
}

/** A tone block the shape of the content that is loading. */
export function Skeleton({ className }: { className?: string }) {
  return <span aria-hidden className={clsx("block animate-pulse rounded-md bg-laminate-2", className)} />;
}

/** Page-level loading state: a heading band and a few panel-shaped blocks. */
export function PageSkeleton({ rows = 6, label = "Loading" }: { rows?: number; label?: string }) {
  return (
    <div role="status" aria-label={label} className="flex flex-col gap-6">
      <Skeleton className="h-20 w-full" />
      <div className="rounded-[var(--radius-panel)] bg-silk p-5">
        <Skeleton className="mb-5 h-5 w-48" />
        <div className="flex flex-col gap-3">
          {Array.from({ length: rows }, (_, i) => (
            <Skeleton key={i} className={clsx("h-4", i % 3 === 2 ? "w-2/3" : "w-full")} />
          ))}
        </div>
      </div>
      <span className="sr-only">{label}</span>
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof Error ? error.message : String(error);
  return (
    <p role="alert" className="rounded-md bg-blocker-tint px-3 py-2 text-sm text-blocker">
      {message}
    </p>
  );
}

/** An empty state says what is missing and offers the next step. */
export function Empty({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="rounded-[var(--radius-panel)] bg-laminate-2 px-6 py-10 sm:px-10">
      <p className="text-xl font-semibold">{title}</p>
      {children && <div className="mt-2 max-w-prose text-ink-2">{children}</div>}
    </div>
  );
}

/** Native <dialog> with focus handling and Escape-to-close for free. */
export function Dialog({
  open,
  onClose,
  title,
  children,
  wide = false,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      onClose={onClose}
      className={clsx(
        "m-auto w-[calc(100%-2rem)] rounded-[var(--radius-panel)] bg-silk p-0 text-ink shadow-[var(--shadow-overlay)]", // taste-skill-ignore: a dialog floats
        wide ? "max-w-3xl" : "max-w-lg",
      )}
    >
      <header className="flex items-center justify-between gap-4 px-6 pt-5 pb-2">
        <h2 className="text-lg font-semibold">{title}</h2>
        <button
          onClick={onClose}
          className="flex h-9 w-9 items-center justify-center rounded-md text-xl leading-none text-ink-3 transition-colors hover:bg-laminate-2 hover:text-ink"
          aria-label="Close"
        >
          ×
        </button>
      </header>
      <div className="relative max-h-[75vh] overflow-y-auto px-6 pt-2 pb-6">{open && children}</div>
    </dialog>
  );
}
