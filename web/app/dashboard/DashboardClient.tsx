"use client";

import { useCallback, useState } from "react";
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
import { exportUrl } from "@/lib/dashboard-api";

export function DashboardClient() {
  const [refreshKey, setRefreshKey] = useState(0);
  const bump = useCallback(() => setRefreshKey((k) => k + 1), []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <LiveIndicator onCaseUpdate={bump} />
        <div className="flex items-center gap-3">
          <a
            href={exportUrl("markdown")}
            className="text-sm text-[var(--color-accent)] hover:underline"
            target="_blank"
            rel="noreferrer"
          >
            Export batch report
          </a>
          <KillswitchControl onChanged={bump} />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6">
        <BatchSummaryPanel refreshKey={refreshKey} />
        <WorkQueuePanel refreshKey={refreshKey} />
        <ApprovalQueuePanel refreshKey={refreshKey} onChanged={bump} />
        <ExceptionQueuePanel refreshKey={refreshKey} />
        <CompliancePanel refreshKey={refreshKey} />
        <ModelTransparencyPanel />
        <GroundedQAPanel />
        <WhatIfPanel />
        <ChaosPanel />
      </div>
    </div>
  );
}
