"use client";

import { humanize } from "@/lib/format";

const STATE_LABEL: Record<string, string> = {
  pending: "Pending",
  awaiting_promise: "Awaiting promise",
  recovered: "Recovered",
  abandoned_uneconomic: "Uneconomic",
  exception: "Exception",
  stopped_by_policy: "Blocked by policy",
  control_untouched: "Control (untouched)",
};

const STATE_COLOR: Record<string, string> = {
  pending: "var(--color-neutral)",
  awaiting_promise: "var(--color-info)",
  recovered: "var(--color-good)",
  abandoned_uneconomic: "var(--color-warn)",
  exception: "var(--color-bad)",
  stopped_by_policy: "var(--color-policy)",
  control_untouched: "var(--color-muted)",
};

const ORDER = [
  "recovered",
  "awaiting_promise",
  "pending",
  "abandoned_uneconomic",
  "stopped_by_policy",
  "exception",
  "control_untouched",
];

export function RecoveryFunnel({ casesByState }: { casesByState: Record<string, number> }) {
  const total = Object.values(casesByState).reduce((a, b) => a + b, 0);
  if (total === 0) return null;

  const entries = Object.entries(casesByState)
    .filter(([, count]) => count > 0)
    .sort(([a], [b]) => ORDER.indexOf(a) - ORDER.indexOf(b));

  return (
    <div>
      <div className="flex h-3 w-full overflow-hidden rounded-full bg-[var(--color-neutral-bg)]" role="img" aria-label="Case resolution states, proportional to total case volume">
        {entries.map(([state, count], i) => {
          const pct = (count / total) * 100;
          return (
            <div
              key={state}
              title={`${STATE_LABEL[state] ?? humanize(state)}: ${count.toLocaleString("en-IN")} (${pct.toFixed(1)}%)`}
              className="h-full transition-[filter] hover:brightness-110"
              style={{
                width: `${pct}%`,
                background: STATE_COLOR[state] ?? "var(--color-neutral)",
                marginLeft: i === 0 ? 0 : "1px",
              }}
            />
          );
        })}
      </div>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5">
        {entries.map(([state, count]) => (
          <div key={state} className="flex items-center gap-1.5 text-xs">
            <span
              className="h-2 w-2 shrink-0 rounded-[2px]"
              style={{ background: STATE_COLOR[state] ?? "var(--color-neutral)" }}
            />
            <span className="text-[var(--color-ink-soft)]">{STATE_LABEL[state] ?? humanize(state)}</span>
            <span className="font-mono text-[var(--color-muted)]">{count.toLocaleString("en-IN")}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
