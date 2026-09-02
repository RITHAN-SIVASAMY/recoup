"use client";

import { useEffect, useState } from "react";
import { Badge, Button, Card, EmptyState, Table } from "@/components/ui";
import {
  cancelStagedAction,
  fetchApprovals,
  grantApproval,
  rejectApproval,
  type Approval,
} from "@/lib/dashboard-api";
import { formatInr } from "@/lib/format";

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
    <Card title="Approval queue">
      {lastStagedActionId && (
        <div className="mb-3 flex items-center justify-between rounded-md bg-indigo-50 px-3 py-2 text-sm text-indigo-900">
          <span>Action staged — still inside its undo window.</span>
          <Button variant="secondary" onClick={cancelLastStaged} disabled={busy === lastStagedActionId}>
            Cancel before it sends
          </Button>
        </div>
      )}
      {approvals === null ? (
        <EmptyState>Loading…</EmptyState>
      ) : approvals.length === 0 ? (
        <EmptyState>Nothing awaiting sign-off.</EmptyState>
      ) : (
        <Table columns={["Case", "Action", "EV", "Rule", "Reason", ""]}>
          {approvals.map((a) => (
            <tr key={a.approval_id}>
              <td className="py-2 pr-4">{a.case_id.slice(-8)}</td>
              <td className="py-2 pr-4">
                {a.action_type}
                {a.channel ? ` · ${a.channel}` : ""}
              </td>
              <td className="py-2 pr-4 tabular-nums">{formatInr(a.expected_value_inr)}</td>
              <td className="py-2 pr-4">
                <Badge tone="warn">{a.rule_id}</Badge>
              </td>
              <td className="py-2 pr-4 text-black/60">{a.reason}</td>
              <td className="py-2 pr-4">
                <div className="flex gap-2">
                  <Button
                    onClick={() => act(a.approval_id, "grant")}
                    disabled={busy === a.approval_id}
                  >
                    Approve
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => act(a.approval_id, "reject")}
                    disabled={busy === a.approval_id}
                  >
                    Reject
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </Table>
      )}
    </Card>
  );
}
