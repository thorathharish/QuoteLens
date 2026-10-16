"use client";

import clsx from "clsx";
import { forwardRef, useEffect, useRef } from "react";

export function Button({
  variant = "secondary",
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "quiet" | "danger" }) {
  return (
    <button
      {...props}
      className={clsx(
        "inline-flex items-center justify-center gap-1.5 rounded px-3 py-1.5 text-sm font-bold transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" && "bg-mask text-silk hover:bg-mask-2",
        variant === "secondary" && "border border-rule-strong bg-silk text-ink hover:border-mask hover:text-mask",
        variant === "quiet" && "text-mask hover:underline",
        variant === "danger" && "border border-blocker bg-silk text-blocker hover:bg-blocker-tint",
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
      <span className="font-bold text-ink-2">{label}</span>
      <input
        ref={ref}
        {...props}
        className="rounded border border-rule-strong bg-silk px-2.5 py-1.5 text-base text-ink placeholder:text-ink-3"
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
      <span className="font-bold text-ink-2">{label}</span>
      <textarea
        {...props}
        className="min-h-20 rounded border border-rule-strong bg-silk px-2.5 py-1.5 text-base text-ink placeholder:text-ink-3"
      />
    </label>
  );
}

const SEVERITY_STYLE: Record<string, string> = {
  BLOCKER: "bg-blocker-tint text-blocker border-blocker/40",
  HIGH: "bg-high-tint text-high border-high/40",
  MEDIUM: "bg-medium-tint text-medium border-medium/40",
  LOW: "bg-low-tint text-low border-low/30",
};

export function SeverityTag({ severity }: { severity: string }) {
  const label = { BLOCKER: "Blocker", HIGH: "High", MEDIUM: "Medium", LOW: "Low" }[severity] ?? severity;
  return (
    <span className={clsx("inline-flex rounded-sm border px-1.5 py-0.5 text-xs font-bold", SEVERITY_STYLE[severity])}>
      {label}
    </span>
  );
}

export function Tag({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "mask" | "gold" }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-sm px-1.5 py-0.5 text-xs font-bold",
        tone === "neutral" && "bg-low-tint text-ink-2",
        tone === "mask" && "bg-mask-tint text-mask",
        tone === "gold" && "bg-gold-tint text-gold",
      )}
    >
      {children}
    </span>
  );
}

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
    <section className={clsx("rounded-md border border-rule bg-silk", className)}>
      {(title || action) && (
        <header className="flex items-center justify-between gap-4 border-b border-rule px-4 py-2.5">
          <h2 className="text-base font-bold">{title}</h2>
          {action}
        </header>
      )}
      <div className="p-4">{children}</div>
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

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof Error ? error.message : String(error);
  return (
    <p role="alert" className="rounded border border-blocker/40 bg-blocker-tint px-3 py-2 text-sm text-blocker">
      {message}
    </p>
  );
}

export function Empty({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="rounded-md border border-dashed border-rule-strong px-6 py-10 text-center">
      <p className="font-bold">{title}</p>
      {children && <div className="mt-2 text-sm text-ink-2">{children}</div>}
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
        "m-auto w-[calc(100%-2rem)] rounded-md border border-rule-strong bg-silk p-0 text-ink shadow-xl",
        wide ? "max-w-3xl" : "max-w-lg",
      )}
    >
      <header className="flex items-center justify-between border-b border-rule px-5 py-3">
        <h2 className="text-lg font-bold">{title}</h2>
        <button onClick={onClose} className="rounded px-2 text-xl leading-none text-ink-3 hover:text-ink" aria-label="Close">
          ×
        </button>
      </header>
      <div className="max-h-[75vh] overflow-y-auto px-5 py-4">{open && children}</div>
    </dialog>
  );
}
