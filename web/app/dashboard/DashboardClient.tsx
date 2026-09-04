"use client";

import { useCallback, useEffect, useState } from "react";
import { ApprovalQueuePanel } from "./ApprovalQueuePanel";
import { BatchSummaryPanel } from "./BatchSummaryPanel";
import { BreakdownChart } from "./BreakdownChart";
import { ChaosPanel } from "./ChaosPanel";
import { CompliancePanel } from "./CompliancePanel";
import { ExceptionQueuePanel } from "./ExceptionQueuePanel";
import { GroundedQAPanel } from "./GroundedQAPanel";
import { KillswitchControl } from "./KillswitchControl";
import { LiveIndicator } from "./LiveIndicator";
import { ModelTransparencyPanel } from "./ModelTransparencyPanel";
import { WhatIfPanel } from "./WhatIfPanel";
import { WorkQueuePanel } from "./WorkQueuePanel";
import { Card } from "@/components/ui";
import { CommandPalette } from "@/components/CommandPalette";
import { NAV_ICONS, Sidebar, type NavItem } from "@/components/Sidebar";
import { exportUrl, fetchApprovals, fetchBatchSummary, fetchExceptionQueue } from "@/lib/dashboard-api";

const SECTIONS: { id: string; label: string; description: string }[] = [
  { id: "overview", label: "Overview", description: "The work queue, ranked — and what's stuck needing a human" },
  { id: "governance", label: "Governance", description: "Sign-off, blocked actions, and the compliance ledger" },
  { id: "insights", label: "Insights", description: "What the models get right, wrong, and why" },
  { id: "simulate", label: "What-if & Chaos", description: "Replay history under new rules — or break it on purpose" },
];

export function DashboardClient() {
  const [refreshKey, setRefreshKey] = useState(0);
  const [exceptionCount, setExceptionCount] = useState(0);
  const [approvalCount, setApprovalCount] = useState(0);
  const [breakdowns, setBreakdowns] = useState<import("@/lib/dashboard-api").BreakdownRow[]>([]);
  const [activeId, setActiveId] = useState("overview");
  const [paletteOpen, setPaletteOpen] = useState(false);
  const bump = useCallback(() => setRefreshKey((k) => k + 1), []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchExceptionQueue(), fetchApprovals(), fetchBatchSummary()]).then(
      ([exceptions, approvals, summary]) => {
        if (cancelled) return;
        setExceptionCount(exceptions.length);
        setApprovalCount(approvals.length);
        setBreakdowns(summary.batch_report?.breakdowns ?? []);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen(true);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const navItems: NavItem[] = [
    { id: "overview", label: "Overview", icon: NAV_ICONS.overview, badge: exceptionCount },
    { id: "governance", label: "Governance", icon: NAV_ICONS.governance, badge: approvalCount },
    { id: "insights", label: "Insights", icon: NAV_ICONS.insights },
    { id: "simulate", label: "What-if & Chaos", icon: NAV_ICONS.simulate },
  ];

  const active = SECTIONS.find((s) => s.id === activeId) ?? SECTIONS[0];

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--color-bg)]">
      <Sidebar
        navItems={navItems}
        activeId={activeId}
        onSelect={setActiveId}
        footer={
          <button
            onClick={() => setPaletteOpen(true)}
            className="flex w-full items-center justify-between rounded-lg border border-[var(--color-rail-border)] bg-white/[0.03] px-3 py-2 text-xs text-[var(--color-rail-muted)] transition hover:bg-white/[0.06] hover:text-[var(--color-rail-text)]"
          >
            <span>Jump to case…</span>
            <kbd className="rounded border border-[var(--color-rail-border)] bg-black/30 px-1.5 py-0.5 font-mono text-[10px]">
              ⌘K
            </kbd>
          </button>
        }
      />

      <div className="flex min-w-0 flex-1 flex-col overflow-y-auto">
        <header className="sticky top-0 z-20 flex items-center justify-between gap-4 border-b border-[var(--color-border)] bg-[var(--color-surface)]/85 px-8 py-4 backdrop-blur-sm">
          <div className="min-w-0">
            <h1 className="font-display text-lg font-semibold text-[var(--color-ink)]">{active.label}</h1>
            <p className="text-xs text-[var(--color-muted)]">{active.description}</p>
          </div>
          <div className="flex shrink-0 items-center gap-4 whitespace-nowrap">
            <LiveIndicator onCaseUpdate={bump} />
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
        </header>

        <main className="mx-auto w-full max-w-6xl flex-1 px-8 py-6">
          <BatchSummaryPanel refreshKey={refreshKey} />

          <div key={activeId} className="animate-in mt-6 space-y-6">
            {activeId === "overview" && (
              <>
                <WorkQueuePanel refreshKey={refreshKey} />
                <ExceptionQueuePanel refreshKey={refreshKey} />
              </>
            )}
            {activeId === "governance" && (
              <>
                <ApprovalQueuePanel refreshKey={refreshKey} onChanged={bump} />
                <CompliancePanel refreshKey={refreshKey} />
              </>
            )}
            {activeId === "insights" && (
              <>
                <Card
                  title="Lift by segment"
                  description="Where the incremental recovery is actually coming from — and where it isn't"
                >
                  <BreakdownChart breakdowns={breakdowns} />
                </Card>
                <ModelTransparencyPanel />
                <GroundedQAPanel />
              </>
            )}
            {activeId === "simulate" && (
              <>
                <WhatIfPanel />
                <ChaosPanel />
              </>
            )}
          </div>
        </main>
      </div>

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        sections={SECTIONS}
        onNavigate={(id) => {
          setActiveId(id);
          setPaletteOpen(false);
        }}
      />
    </div>
  );
}
