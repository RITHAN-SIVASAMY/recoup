"use client";

import { useEffect, useState } from "react";
import { Badge, Card, EmptyState, Stat } from "@/components/ui";
import { fetchBatchSummary, type BatchSummary } from "@/lib/dashboard-api";
import { formatInr, formatPercent } from "@/lib/format";

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

  if (loading) return <Card title="Batch summary">Loading…</Card>;
  if (error) return <Card title="Batch summary">Could not load: {error}</Card>;
  if (!summary) return null;

  const report = summary.batch_report;

  return (
    <Card title="Batch summary" className="col-span-full">
      {!report ? (
        <EmptyState>
          No batch has run yet. Run <code className="rounded bg-black/5 px-1">make demo</code> to
          produce one.
        </EmptyState>
      ) : (
        <div className="space-y-4">
          <div className="text-xs text-black/40">
            batch {report.batch_id} · seed {report.seed} · {report.n_cases_total} cases
          </div>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
            <Stat label="At risk" value={formatInr(report.at_risk_inr)} />
            <Stat
              label="Raw recovered"
              value={formatInr(report.raw_recovered_inr)}
              sub="overstates our impact"
              tone="warn"
            />
            <Stat
              label="Incremental recovered"
              value={formatInr(report.incremental_inr)}
              sub={`95% CI ${formatInr(report.ci_low_inr)} – ${formatInr(report.ci_high_inr)}`}
              tone={report.significant ? "good" : "neutral"}
            />
            <Stat
              label="Lift"
              value={formatPercent(report.lift_pp)}
              sub={`z=${report.z.toFixed(2)}, p=${report.p_value.toFixed(4)}`}
            />
            <Stat
              label="CUPED-adjusted"
              value={formatInr(report.cuped_adjusted_inr)}
              sub="unadjusted shown alongside"
            />
            <Stat
              label="Cost per ₹ recovered"
              value={report.cost_per_inr_recovered ? `₹ ${report.cost_per_inr_recovered}` : "undefined"}
            />
            <Stat
              label="₹ saved by not contacting"
              value={formatInr(report.saved_by_not_contacting_inr)}
              sub="sure things + sleeping dogs + EV floor"
            />
            <Stat
              label="MDE"
              value={formatPercent(report.mde_pp)}
              sub={`n_t=${report.n_treated} n_c=${report.n_control}`}
            />
          </div>
          {!report.significant && (
            <div className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">
              This result is <strong>not statistically significant</strong> at this batch size —
              the MDE above is the honest bound, not the number to lead with.
            </div>
          )}
          <div className="flex flex-wrap gap-2 pt-1">
            <Badge tone={summary.audit_chain_verified ? "good" : "bad"}>
              audit chain {summary.audit_chain_verified ? "verified" : "BROKEN"}
            </Badge>
            <Badge tone={summary.replay_equality_passed ? "good" : "bad"}>
              replay {summary.replay_equality_passed ? "PASS" : "FAIL"}
            </Badge>
            {Object.entries(summary.cases_by_state).map(([state, count]) => (
              <Badge key={state} tone="info">
                {state}: {count}
              </Badge>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}
