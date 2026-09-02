"use client";

import { useEffect, useState } from "react";
import { Badge, Card, EmptyState, Stat } from "@/components/ui";
import { fetchBatchSummary, type BatchSummary } from "@/lib/dashboard-api";
import { formatInr, formatPercent } from "@/lib/format";

const STATE_TONE: Record<string, "good" | "bad" | "warn" | "info" | "neutral"> = {
  recovered: "good",
  abandoned_uneconomic: "warn",
  exception: "bad",
  awaiting_promise: "info",
  pending: "neutral",
  stopped_by_policy: "warn",
  control_untouched: "neutral",
};

export function BatchSummaryPanel({ refreshKey }: { refreshKey: number }) {
  const [summary, setSummary] = useState<BatchSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchBatchSummary()
      .then((data) => {
        if (!cancelled) setSummary(data);
      })
      .catch((e) => {
        if (!cancelled) setError(String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  if (loading) {
    return (
      <Card>
        <div className="h-24 animate-pulse rounded-lg bg-black/[0.03]" />
      </Card>
    );
  }
  if (error) return <Card>Could not load batch summary: {error}</Card>;
  if (!summary) return null;

  const report = summary.batch_report;

  if (!report) {
    return (
      <Card title="Batch summary">
        <EmptyState>
          No batch has run yet. Run <code className="rounded bg-black/5 px-1.5 py-0.5">make demo</code>{" "}
          to produce one.
        </EmptyState>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card padded={false} className="overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border)] bg-black/[0.015] px-5 py-3">
          <div className="text-xs text-[var(--color-muted)]">
            batch <span className="font-mono text-[var(--color-ink-soft)]">{report.batch_id}</span>{" "}
            · seed {report.seed} · {report.n_cases_total} cases
          </div>
          <div className="flex gap-2">
            <Badge tone={summary.audit_chain_verified ? "good" : "bad"} dot>
              audit chain {summary.audit_chain_verified ? "verified" : "BROKEN"}
            </Badge>
            <Badge tone={summary.replay_equality_passed ? "good" : "bad"} dot>
              replay {summary.replay_equality_passed ? "pass" : "FAIL"}
            </Badge>
          </div>
        </div>

        <div className="grid grid-cols-1 divide-y divide-[var(--color-border)] sm:grid-cols-3 sm:divide-x sm:divide-y-0">
          <div className="p-5">
            <Stat label="Revenue at risk" value={formatInr(report.at_risk_inr)} size="lg" />
          </div>
          <div className="p-5">
            <Stat
              label="Raw recovered"
              value={formatInr(report.raw_recovered_inr)}
              sub="overstates our impact"
              tone="warn"
              size="lg"
            />
          </div>
          <div className="bg-[var(--color-accent-soft)] p-5">
            <Stat
              label="Incremental recovered"
              value={formatInr(report.incremental_inr)}
              sub={`95% CI ${formatInr(report.ci_low_inr)} – ${formatInr(report.ci_high_inr)}`}
              tone={report.significant ? "good" : "neutral"}
              size="lg"
            />
          </div>
        </div>

        {!report.significant && (
          <div className="border-t border-[var(--color-warn-bg)] bg-[var(--color-warn-bg)] px-5 py-2.5 text-sm text-[var(--color-warn)]">
            <strong>Not statistically significant</strong> at this batch size — the MDE below is
            the honest bound, not the number to lead with.
          </div>
        )}

        <div className="grid grid-cols-2 gap-4 border-t border-[var(--color-border)] px-5 py-4 sm:grid-cols-4 lg:grid-cols-6">
          <Stat
            label="Lift"
            value={formatPercent(report.lift_pp)}
            sub={`z=${report.z.toFixed(2)}, p=${report.p_value.toFixed(4)}`}
            size="sm"
          />
          <Stat label="MDE" value={formatPercent(report.mde_pp)} sub={`n_t=${report.n_treated} n_c=${report.n_control}`} size="sm" />
          <Stat label="CUPED-adjusted" value={formatInr(report.cuped_adjusted_inr)} size="sm" />
          <Stat
            label="Cost per ₹ recovered"
            value={report.cost_per_inr_recovered ? `₹${report.cost_per_inr_recovered}` : "—"}
            size="sm"
          />
          <Stat label="₹ saved, not contacting" value={formatInr(report.saved_by_not_contacting_inr)} size="sm" />
          <Stat label="Spend on contact" value={formatInr(report.spend_on_contact_inr)} size="sm" />
        </div>
      </Card>

      <div className="flex flex-wrap gap-2">
        {Object.entries(summary.cases_by_state).map(([state, count]) => (
          <Badge key={state} tone={STATE_TONE[state] ?? "neutral"}>
            {state.replace(/_/g, " ")}: {count}
          </Badge>
        ))}
      </div>
    </div>
  );
}
