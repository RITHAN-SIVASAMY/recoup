"use client";

import { useEffect, useState } from "react";
import { Badge, Card, EmptyState } from "@/components/ui";
import { fetchCaseTimeline, type CaseEventRow, type CaseTimeline } from "@/lib/dashboard-api";
import { formatDate, formatInr, humanize } from "@/lib/format";

const EVENT_TONE: Record<string, "good" | "bad" | "warn" | "info" | "neutral"> = {
  "payment.recovered": "good",
  "case.exception": "bad",
  "policy.denied": "warn",
  "case.abandoned_uneconomic": "warn",
  "action.sent": "info",
  "action.engaged": "info",
  "case.cohort_assigned": "neutral",
};

function summaryLine(event: CaseEventRow): string {
  const p = event.payload;
  switch (event.event_type) {
    case "case.created":
      return `Case created — ${humanize(String(p.source_type ?? ""))} — ${formatInr(String(p.amount_at_risk ?? ""))} at risk`;
    case "case.cohort_assigned":
      return `Cohort assigned: ${humanize(String(p.cohort ?? ""))}${p.excluded_from_control ? " (excluded from control)" : ""}`;
    case "case.classified":
      return `Classified: ${humanize(String(p.root_cause ?? ""))} (confidence ${Number(p.confidence).toFixed(2)})`;
    case "case.scored":
      return `Scored: uplift ${Number(p.uplift).toFixed(3)}, segment ${humanize(String(p.uplift_segment ?? ""))}`;
    case "ev.computed":
      return `EV computed for ${humanize(String(p.action_type ?? ""))}${p.channel ? " / " + humanize(String(p.channel)) : ""}: ${formatInr(String(p.ev_inr ?? ""))}`;
    case "policy.evaluated":
      return `Policy evaluated: ${p.decision} (${p.rule_id})`;
    case "policy.denied":
      return `Denied — ${p.rule_id}: ${p.reason}`;
    case "action.staged":
      return `Staged: ${humanize(String(p.action_type ?? ""))}${p.channel ? " / " + humanize(String(p.channel)) : ""}`;
    case "action.sent":
      return `Sent via ${humanize(String(p.channel ?? ""))}`;
    case "action.delivered":
      return "Delivered";
    case "action.engaged":
      return "Customer engaged";
    case "action.cancelled":
      return `Cancelled — ${p.reason ?? ""}`;
    case "case.abandoned_uneconomic":
      return `Abandoned — below EV floor (${formatInr(String(p.ev_floor_inr ?? ""))})`;
    case "payment.recovered":
      return `Payment recovered (via ${p.via ?? "unknown"})`;
    case "case.exception":
      return `Exception at ${p.stage ? humanize(String(p.stage)) : "?"}: ${p.error ?? p.reason ?? "unspecified"}`;
    case "case.measurement_resolved":
      return `Measurement resolution: ${p.resolved ? "resolved" : "not resolved"}`;
    case "ptp.captured":
      return `Promise to pay captured: ${formatInr(String(p.amount ?? ""))} by ${p.promised_date}`;
    default:
      return event.event_type;
  }
}

export function CaseTimelineClient({ caseId }: { caseId: string }) {
  const [data, setData] = useState<CaseTimeline | "not_found" | null>(null);

  useEffect(() => {
    fetchCaseTimeline(caseId)
      .then(setData)
      .catch(() => setData("not_found"));
  }, [caseId]);

  if (data === null) return <EmptyState>Loading…</EmptyState>;
  if (data === "not_found") return <EmptyState>Case not found.</EmptyState>;

  const { case: c, events } = data;

  return (
    <div className="space-y-6">
      <Card>
        <div className="flex flex-wrap gap-2">
          <Badge tone="info">{humanize(c.source_type)}</Badge>
          <Badge dot>{humanize(c.resolution_state)}</Badge>
          {c.cohort && (
            <Badge tone={c.cohort === "control" ? "warn" : "good"}>{humanize(c.cohort)}</Badge>
          )}
          {c.root_cause && <Badge tone="neutral">{humanize(c.root_cause)}</Badge>}
          <Badge tone="neutral">{formatInr(c.amount_at_risk)}</Badge>
        </div>
      </Card>

      <Card title={`Timeline`} description={`${events.length} events, oldest to newest`}>
        <ol className="relative space-y-5 border-l border-[var(--color-border)] pl-5">
          {events.map((event) => (
            <li key={event.event_id} className="relative">
              <span className="absolute -left-[25px] top-1 h-2.5 w-2.5 rounded-full border-2 border-[var(--color-surface)] bg-[var(--color-accent)]" />
              <div className="flex flex-wrap items-baseline gap-2">
                <Badge tone={EVENT_TONE[event.event_type] ?? "neutral"}>{event.event_type}</Badge>
                <span className="text-xs text-[var(--color-muted)]">{formatDate(event.occurred_at)}</span>
                <span className="text-xs text-[var(--color-muted)]">seq {event.seq}</span>
              </div>
              <p className="mt-1 text-sm text-[var(--color-ink-soft)]">{summaryLine(event)}</p>
              <details className="mt-1">
                <summary className="cursor-pointer text-xs text-[var(--color-muted)] hover:text-[var(--color-ink-soft)]">
                  raw payload
                </summary>
                <pre className="scrollbar-thin mt-1 overflow-x-auto rounded-lg bg-black/[0.03] p-2 text-xs text-[var(--color-ink-soft)]">
                  {JSON.stringify(event.payload, null, 2)}
                </pre>
              </details>
            </li>
          ))}
        </ol>
      </Card>
    </div>
  );
}
