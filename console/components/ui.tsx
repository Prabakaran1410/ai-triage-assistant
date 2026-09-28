import type { ReactNode } from "react";

/**
 * Shared visual vocabulary. Kept in one place so a status looks the same in
 * the queue as it does on the detail page - a reviewer scanning the list
 * should not have to relearn the colours when they click into an item.
 */

const STATUS_STYLES: Record<string, { label: string; className: string }> = {
  needs_review: {
    label: "Needs review",
    className: "bg-hold-tint text-hold border-hold-line",
  },
  draft_ready: {
    label: "Draft ready",
    className: "bg-brand-50 text-brand-700 border-brand-200",
  },
  approved: { label: "Approved", className: "bg-go-tint text-go border-go-line" },
  edited: { label: "Edited", className: "bg-go-tint text-go border-go-line" },
  sent: { label: "Sent", className: "bg-go-tint text-go border-go-line" },
  rejected: { label: "Rejected", className: "bg-stop-tint text-stop border-stop-line" },
};

export function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] ?? {
    label: status.replace(/_/g, " "),
    className: "bg-canvas text-muted border-line",
  };
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${style.className}`}
    >
      {style.label}
    </span>
  );
}

export function Card({
  title,
  children,
  className = "",
}: {
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-xl border border-line bg-surface shadow-[0_1px_2px_rgba(16,24,40,0.04)] ${className}`}
    >
      {title ? (
        <h2 className="border-b border-line px-5 py-3 text-xs font-semibold uppercase tracking-wider text-muted">
          {title}
        </h2>
      ) : null}
      <div className="p-5">{children}</div>
    </section>
  );
}

export const buttonStyles = {
  base: "inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors duration-150 disabled:opacity-50",
  primary: "bg-brand-600 text-white hover:bg-brand-700 active:bg-brand-800",
  affirm: "bg-go text-white hover:brightness-110",
  secondary:
    "border border-line-strong bg-surface text-ink-soft hover:bg-canvas hover:border-muted",
  quiet: "text-muted hover:text-ink underline-offset-4 hover:underline",
};

export function Field({
  label,
  hint,
  htmlFor,
  children,
}: {
  label: string;
  hint?: string;
  htmlFor: string;
  children: ReactNode;
}) {
  return (
    <div>
      <label htmlFor={htmlFor} className="block text-sm font-medium text-ink">
        {label}
      </label>
      {children}
      {hint ? <p className="mt-1.5 text-xs text-muted">{hint}</p> : null}
    </div>
  );
}

export const inputStyles =
  "mt-1.5 w-full rounded-lg border border-line-strong bg-surface px-3 py-2 text-sm text-ink transition-colors placeholder:text-muted focus:border-brand-500 focus:outline-none";

export function Alert({ tone = "stop", children }: { tone?: "stop" | "hold"; children: ReactNode }) {
  const className =
    tone === "hold"
      ? "border-hold-line bg-hold-tint text-hold"
      : "border-stop-line bg-stop-tint text-stop";
  return (
    <p role="alert" className={`rounded-lg border px-3.5 py-2.5 text-sm ${className}`}>
      {children}
    </p>
  );
}
