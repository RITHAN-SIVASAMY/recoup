"use client";

import { useEffect, useState } from "react";
import { Badge, Card, EmptyState } from "@/components/ui";
import { fetchComplianceView, type ComplianceView } from "@/lib/dashboard-api";
import { humanize } from "@/lib/format";

const LABELS: Record<string, string> = {
  quiet_hours: "Quiet hours (REG-COMM-01)",
  opt_out: "Opt-out honoured (REG-COMM-03)",
  cap: "Contact-fatigue cap (REG-COMM-06)",
  mandate: "Mandate retry prevented (REG-MAND)",
  control_cohort: "Control cohort protected (RULE-CTRL-001)",
  exposure_cap: "Exposure cap",
  terminal: "Case already resolved",
  ladder: "Ladder rule",
  no_consent: "No recorded consent",
  kill_switch: "Kill switch engaged",
  duplicate: "Duplicate suppressed",
  approval_required: "Required human approval",
  other: "Other",
};

export function CompliancePanel({ refreshKey }: { refreshKey: number }) {
  const [view, setView] = useState<ComplianceView | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchComplianceView().then((data) => {
      if (!cancelled) setView(data);
    });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  return (
    <Card
      title="Compliance"
      description="Every action policy has blocked, named by rule — nothing silently skipped"
    >
      {view === null ? (
        <div className="h-16 animate-pulse rounded-lg bg-black/[0.03]" />
      ) : view.total_blocked === 0 ? (
        <EmptyState>No actions have been blocked yet.</EmptyState>
      ) : (
        <div className="space-y-3">
          <div className="text-sm text-[var(--color-ink-soft)]">
            <span className="font-semibold text-[var(--color-ink)]">{view.total_blocked}</span>{" "}
            actions blocked by policy
          </div>
          <div className="flex flex-wrap gap-2">
            {Object.entries(view.blocked_by_category)
              .sort(([, a], [, b]) => b - a)
              .map(([category, count]) => (
                <Badge key={category} tone="warn">
                  {LABELS[category] ?? humanize(category)}: {count}
                </Badge>
              ))}
          </div>
        </div>
      )}
    </Card>
  );
}
