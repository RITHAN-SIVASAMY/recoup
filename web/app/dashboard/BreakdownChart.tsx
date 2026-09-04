"use client";

import type { BreakdownRow } from "@/lib/dashboard-api";
import { EmptyState } from "@/components/ui";
import { humanize } from "@/lib/format";

const DIMENSION_LABEL: Record<string, string> = {
  root_cause: "Root cause",
  channel: "Channel",
  segment: "Uplift segment",
  value_band: "Value band",
};

export function BreakdownChart({ breakdowns }: { breakdowns: BreakdownRow[] }) {
  if (breakdowns.length === 0) {
    return <EmptyState>No per-segment breakdown in this batch yet.</EmptyState>;
  }

  const maxAbs = Math.max(1, ...breakdowns.map((b) => Math.abs(b.lift_pp)));
  const groups = new Map<string, BreakdownRow[]>();
  for (const row of breakdowns) {
    const list = groups.get(row.dimension) ?? [];
    list.push(row);
    groups.set(row.dimension, list);
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4 text-xs text-[var(--color-muted)]">
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-[2px] bg-[var(--color-good)]" /> lift over control
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-[2px] bg-[var(--color-bad)]" /> below control
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-[2px] border border-dashed border-[var(--color-muted)]" /> not significant
        </span>
      </div>

      {[...groups.entries()].map(([dimension, rows]) => (
        <div key={dimension}>
          <div className="mb-2 text-[11px] font-medium uppercase tracking-wider text-[var(--color-muted)]">
            {DIMENSION_LABEL[dimension] ?? humanize(dimension)}
          </div>
          <div className="space-y-2.5">
            {rows.map((row) => {
              const halfWidth = (Math.abs(row.lift_pp) / maxAbs) * 50;
              const positive = row.lift_pp >= 0;
              const color = positive ? "var(--color-good)" : "var(--color-bad)";
              return (
                <div key={`${dimension}-${row.key}`} className="grid grid-cols-[120px_1fr_88px] items-center gap-3">
                  <span className="truncate text-xs text-[var(--color-ink-soft)]" title={humanize(row.key)}>
                    {humanize(row.key)}
                  </span>
                  <div className="relative h-5">
                    <div className="absolute inset-y-0 left-1/2 w-px bg-[var(--color-border)]" />
                    <div
                      className="absolute inset-y-1 rounded-sm"
                      style={{
                        width: `${halfWidth}%`,
                        left: positive ? "50%" : `${50 - halfWidth}%`,
                        background: color,
                        opacity: row.significant ? 1 : 0.35,
                        border: row.significant ? "none" : `1px dashed ${color}`,
                      }}
                      title={`${row.key}: ${row.lift_pp >= 0 ? "+" : ""}${row.lift_pp.toFixed(1)}pp, p=${row.p_value.toFixed(3)}, n_t=${row.n_treated} n_c=${row.n_control}`}
                    />
                  </div>
                  <span className="text-right font-mono text-xs tabular-nums text-[var(--color-ink)]">
                    {row.lift_pp >= 0 ? "+" : ""}
                    {row.lift_pp.toFixed(1)}pp
                    {!row.significant && <span className="ml-1 text-[var(--color-muted)]">n.s.</span>}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
