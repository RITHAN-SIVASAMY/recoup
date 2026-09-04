import type { ReactNode } from "react";

export function Card({
  title,
  description,
  action,
  children,
  className = "",
  padded = true,
}: {
  title?: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  padded?: boolean;
}) {
  return (
    <section
      className={`rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-[0_1px_2px_rgba(16,19,34,0.04)] ${className}`}
    >
      {(title || action) && (
        <div className="flex items-start justify-between gap-4 border-b border-[var(--color-border)] px-5 py-4">
          <div>
            {title && <h3 className="font-display text-[15px] font-semibold text-[var(--color-ink)]">{title}</h3>}
            {description && (
              <p className="mt-0.5 text-xs text-[var(--color-muted)]">{description}</p>
            )}
          </div>
          {action}
        </div>
      )}
      <div className={padded ? "p-5" : ""}>{children}</div>
    </section>
  );
}

export function Stat({
  label,
  value,
  sub,
  tone = "neutral",
  size = "md",
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: "neutral" | "good" | "bad" | "warn";
  size?: "sm" | "md" | "lg";
}) {
  const toneClass = {
    neutral: "text-[var(--color-ink)]",
    good: "text-[var(--color-good)]",
    bad: "text-[var(--color-bad)]",
    warn: "text-[var(--color-warn)]",
  }[tone];
  const sizeClass = { sm: "text-lg", md: "text-2xl", lg: "text-[28px] sm:text-3xl" }[size];
  return (
    <div className="min-w-0">
      <div className="text-[11px] font-medium uppercase tracking-wider text-[var(--color-muted)]">
        {label}
      </div>
      <div
        className={`mt-1 whitespace-nowrap font-mono font-semibold tabular-nums tracking-tight ${sizeClass} ${toneClass}`}
      >
        {value}
      </div>
      {sub && <div className="mt-1 text-xs text-[var(--color-muted)]">{sub}</div>}
    </div>
  );
}

const BADGE_TONE = {
  neutral: "bg-black/[0.05] text-[var(--color-ink-soft)]",
  good: "bg-[var(--color-good-bg)] text-[var(--color-good)]",
  bad: "bg-[var(--color-bad-bg)] text-[var(--color-bad)]",
  warn: "bg-[var(--color-warn-bg)] text-[var(--color-warn)]",
  info: "bg-[var(--color-info-bg)] text-[var(--color-info)]",
};

export function Badge({
  children,
  tone = "neutral",
  dot = false,
}: {
  children: ReactNode;
  tone?: keyof typeof BADGE_TONE;
  dot?: boolean;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-medium ${BADGE_TONE[tone]}`}
    >
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}

export function Button({
  children,
  onClick,
  variant = "primary",
  disabled = false,
  type = "button",
  size = "md",
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "danger" | "ghost";
  disabled?: boolean;
  type?: "button" | "submit";
  size?: "sm" | "md";
}) {
  const variantClass = {
    primary: "bg-[var(--color-accent)] text-white hover:bg-[#4338ca] shadow-sm",
    secondary:
      "bg-white text-[var(--color-ink-soft)] border border-[var(--color-border)] hover:bg-black/[0.02]",
    danger: "bg-[var(--color-bad)] text-white hover:bg-[#c22540] shadow-sm",
    ghost: "text-[var(--color-ink-soft)] hover:bg-black/[0.04]",
  }[variant];
  const sizeClass = size === "sm" ? "px-2.5 py-1 text-xs" : "px-3.5 py-1.5 text-sm";
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`whitespace-nowrap rounded-lg font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${sizeClass} ${variantClass}`}
    >
      {children}
    </button>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-[var(--color-border)] py-10 text-center text-sm text-[var(--color-muted)]">
      {children}
    </div>
  );
}

export function Table({ columns, children }: { columns: string[]; children: ReactNode }) {
  return (
    <div className="scrollbar-thin overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="text-[11px] uppercase tracking-wider text-[var(--color-muted)]">
            {columns.map((col) => (
              <th key={col} className="border-b border-[var(--color-border)] py-2.5 pr-4 font-medium">
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--color-border)]">{children}</tbody>
      </table>
    </div>
  );
}

export function Tr({ children }: { children: ReactNode }) {
  return <tr className="transition hover:bg-black/[0.015]">{children}</tr>;
}

export function Td({
  children,
  muted = false,
  className = "",
}: {
  children: ReactNode;
  muted?: boolean;
  className?: string;
}) {
  return (
    <td
      className={`py-2.5 pr-4 ${muted ? "text-[var(--color-muted)]" : "text-[var(--color-ink)]"} ${className}`}
    >
      {children}
    </td>
  );
}
