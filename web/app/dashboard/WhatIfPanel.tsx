"use client";

import { useState } from "react";
import { Badge, Button, Card } from "@/components/ui";
import { runWhatIf, type WhatIfProjection } from "@/lib/dashboard-api";

export function WhatIfPanel() {
  const [evFloor, setEvFloor] = useState("");
  const [channelCost, setChannelCost] = useState("");
  const [approvalThreshold, setApprovalThreshold] = useState("");
  const [maxContacts, setMaxContacts] = useState("");
  const [result, setResult] = useState<WhatIfProjection | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true);
    try {
      const projection = await runWhatIf({
        ev_floor_inr: evFloor || undefined,
        channel_cost_inr: channelCost || undefined,
        approval_threshold_inr: approvalThreshold || undefined,
        max_contacts: maxContacts ? Number(maxContacts) : undefined,
      });
      setResult(projection);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      title="What-if simulator"
      description="Replays the historical log under different policy settings"
    >
      <p className="mb-4 rounded-lg bg-[var(--color-info-bg)] px-3 py-2 text-xs text-[var(--color-info)]">
        A projection over the historical log, never a measurement — it never estimates a
        projected ₹ recovered, since a case&apos;s real-world counterfactual isn&apos;t something
        replaying the log can supply.
      </p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <label className="text-xs font-medium text-[var(--color-ink-soft)]">
          EV floor (₹)
          <input
            value={evFloor}
            onChange={(e) => setEvFloor(e.target.value)}
            placeholder="5.00"
            className="mt-1 w-full rounded-lg border border-[var(--color-border)] px-2 py-1.5 text-sm outline-none focus:border-[var(--color-accent)]"
          />
        </label>
        <label className="text-xs font-medium text-[var(--color-ink-soft)]">
          Channel cost (₹)
          <input
            value={channelCost}
            onChange={(e) => setChannelCost(e.target.value)}
            placeholder="0.20"
            className="mt-1 w-full rounded-lg border border-[var(--color-border)] px-2 py-1.5 text-sm outline-none focus:border-[var(--color-accent)]"
          />
        </label>
        <label className="text-xs font-medium text-[var(--color-ink-soft)]">
          Approval threshold (₹)
          <input
            value={approvalThreshold}
            onChange={(e) => setApprovalThreshold(e.target.value)}
            placeholder="15000"
            className="mt-1 w-full rounded-lg border border-[var(--color-border)] px-2 py-1.5 text-sm outline-none focus:border-[var(--color-accent)]"
          />
        </label>
        <label className="text-xs font-medium text-[var(--color-ink-soft)]">
          Max contacts
          <input
            value={maxContacts}
            onChange={(e) => setMaxContacts(e.target.value)}
            placeholder="3"
            className="mt-1 w-full rounded-lg border border-[var(--color-border)] px-2 py-1.5 text-sm outline-none focus:border-[var(--color-accent)]"
          />
        </label>
      </div>
      <div className="mt-4">
        <Button onClick={run} disabled={busy}>
          {busy ? "Replaying…" : "Replay history with these settings"}
        </Button>
      </div>
      {result && (
        <div className="mt-4 flex flex-wrap gap-2 border-t border-[var(--color-border)] pt-4">
          <Badge tone="info">projection, not a measurement</Badge>
          <Badge>considered: {result.cases_considered}</Badge>
          <Badge tone="neutral">
            would contact: {result.baseline_would_contact} → {result.projected_would_contact}
          </Badge>
          <Badge tone="good">newly contactable: {result.newly_contactable}</Badge>
          <Badge tone="warn">newly uneconomic: {result.newly_uneconomic}</Badge>
          <Badge tone="warn">newly needs approval: {result.newly_requires_approval}</Badge>
          <Badge tone="good">no longer needs approval: {result.no_longer_requires_approval}</Badge>
          <Badge tone="warn">newly over contact cap: {result.newly_over_contact_cap}</Badge>
        </div>
      )}
    </Card>
  );
}
