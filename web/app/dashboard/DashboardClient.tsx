"use client";

import { useCallback, useEffect, useState } from "react";
import { ApprovalQueuePanel } from "./ApprovalQueuePanel";
import { BatchSummaryPanel } from "./BatchSummaryPanel";
import { ChaosPanel } from "./ChaosPanel";
import { CompliancePanel } from "./CompliancePanel";
import { ExceptionQueuePanel } from "./ExceptionQueuePanel";
import { GroundedQAPanel } from "./GroundedQAPanel";
import { KillswitchControl } from "./KillswitchControl";
import { LiveIndicator } from "./LiveIndicator";
import { ModelTransparencyPanel } from "./ModelTransparencyPanel";
import { WhatIfPanel } from "./WhatIfPanel";
import { WorkQueuePanel } from "./WorkQueuePanel";
import { Tabs, type TabDef } from "@/components/Tabs";
import { exportUrl, fetchApprovals, fetchExceptionQueue } from "@/lib/dashboard-api";

export function DashboardClient() {
  const [refreshKey, setRefreshKey] = useState(0);
  const [exceptionCount, setExceptionCount] = useState(0);
  const [approvalCount, setApprovalCount] = useState(0);
  const bump = useCallback(() => setRefreshKey((k) => k + 1), []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchExceptionQueue(), fetchApprovals()]).then(([exceptions, approvals]) => {
      if (cancelled) return;
      setExceptionCount(exceptions.length);
      setApprovalCount(approvals.length);
    });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  const tabs: TabDef[] = [
    {
      id: "overview",
      label: "Overview",
      badge: exceptionCount,
      content: (
        <div className="space-y-6">
          <WorkQueuePanel refreshKey={refreshKey} />
          <ExceptionQueuePanel refreshKey={refreshKey} />
        </div>
      ),
    },
    {
      id: "governance",
      label: "Governance",
      badge: approvalCount,
      content: (
        <div className="space-y-6">
          <ApprovalQueuePanel refreshKey={refreshKey} onChanged={bump} />
          <CompliancePanel refreshKey={refreshKey} />
        </div>
      ),
    },
    {
      id: "insights",
      label: "Insights",
      content: (
        <div className="space-y-6">
          <ModelTransparencyPanel />
          <GroundedQAPanel />
        </div>
      ),
    },
    {
      id: "simulate",
      label: "What-if & Chaos",
      content: (
        <div className="space-y-6">
          <WhatIfPanel />
          <ChaosPanel />
        </div>
      ),
    },
  ];

  return (
    <div>
      <header className="sticky top-0 z-20 border-b border-[var(--color-border)] bg-[var(--color-surface)]/90 backdrop-blur-sm">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-3.5">
          <div className="flex items-center gap-3">
            <span className="text-base font-semibold tracking-tight text-[var(--color-ink)]">
              Recoup
            </span>
            <LiveIndicator onCaseUpdate={bump} />
          </div>
          <div className="flex items-center gap-4">
            <a
              href={exportUrl("markdown")}
              className="text-sm font-medium text-[var(--color-accent)] hover:underline"
              target="_blank"
              rel="noreferrer"
            >
              Export report
            </a>
            <KillswitchControl onChanged={bump} />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-6">
        <BatchSummaryPanel refreshKey={refreshKey} />
        <div className="mt-6">
          <Tabs tabs={tabs} />
        </div>
      </main>
    </div>
  );
}
