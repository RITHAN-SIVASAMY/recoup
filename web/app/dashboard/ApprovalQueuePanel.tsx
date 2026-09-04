"use client";

import { useEffect, useState } from "react";
import { Badge, Button, Card, EmptyState, Table, Td, Tr } from "@/components/ui";
import {
  cancelStagedAction,
  fetchApprovals,
  grantApproval,
  rejectApproval,
  type Approval,
} from "@/lib/dashboard-api";
import { formatInr, humanize } from "@/lib/format";

export function ApprovalQueuePanel({
  refreshKey,
  onChanged,
}: {
  refreshKey: number;
  onChanged: () => void;
}) {
  const [approvals, setApprovals] = useState<Approval[] | null>(null);
  const [lastStagedActionId, setLastStagedActionId] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchApprovals().then((data) => {
      if (!cancelled) setApprovals(data);
    });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  async function act(approvalId: string, action: "grant" | "reject") {
    setBusy(approvalId);
    try {
      if (action === "grant") {
        const result = await grantApproval(approvalId);
        setLastStagedActionId(result.staged_action_id);
      } else {
        await rejectApproval(approvalId);
      }
      onChanged();
    } finally {
      setBusy(null);
    }
  }

  async function cancelLastStaged() {
    if (!lastStagedActionId) return;
    setBusy(lastStagedActionId);
    try {
      await cancelStagedAction(lastStagedActionId);
      setLastStagedActionId(null);
      onChanged();
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card title="Approval queue" description="Actions above the threshold, awaiting sign-off">
      {lastStagedActionId && (
        <div className="mb-4 flex items-center justify-between rounded-xl bg-[var(--color-info-bg)] px-4 py-3 text-sm text-[var(--color-info)]">
          <span>Action staged — still inside its undo window.</span>
          <Button variant="secondary" size="sm" onClick={cancelLastStaged} disabled={busy === lastStagedActionId}>
            Cancel before it sends
          </Button>
        </div>
      )}
      {approvals === null ? (
        <div className="h-24 animate-pulse rounded-lg bg-black/[0.03]" />
      ) : approvals.length === 0 ? (
        <EmptyState>Nothing awaiting sign-off.</EmptyState>
      ) : (
        <Table columns={["Case", "Action", "EV", "Rule", "Reason", ""]}>
          {approvals.map((a) => (
            <Tr key={a.approval_id}>
              <Td className="font-mono text-xs">{a.case_id.slice(-8)}</Td>
              <Td>
                {humanize(a.action_type)}
                {a.channel ? ` · ${humanize(a.channel)}` : ""}
              </Td>
              <Td>
                <span className="font-medium">{formatInr(a.expected_value_inr)}</span>
              </Td>
              <Td>
                <Badge tone="warn">{a.rule_id}</Badge>
              </Td>
              <Td muted>{a.reason}</Td>
              <Td>
                <div className="flex gap-2">
                  <Button size="sm" onClick={() => act(a.approval_id, "grant")} disabled={busy === a.approval_id}>
                    Approve
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => act(a.approval_id, "reject")}
                    disabled={busy === a.approval_id}
                  >
                    Reject
                  </Button>
                </div>
              </Td>
            </Tr>
          ))}
        </Table>
      )}
    </Card>
  );
}
