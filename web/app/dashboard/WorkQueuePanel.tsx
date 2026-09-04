"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Badge, Card, EmptyState, Table, Td, Tr } from "@/components/ui";
import { fetchWorkQueue, type WorkQueueItem } from "@/lib/dashboard-api";
import { formatInr, humanize } from "@/lib/format";

export function WorkQueuePanel({ refreshKey }: { refreshKey: number }) {
  const [items, setItems] = useState<WorkQueueItem[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchWorkQueue(20).then((data) => {
      if (!cancelled) setItems(data);
    });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  return (
    <Card
      title="Work queue"
      description="Ranked by expected incremental value — the customers worth chasing, in order"
    >
      {items === null ? (
        <div className="h-32 animate-pulse rounded-lg bg-black/[0.03]" />
      ) : items.length === 0 ? (
        <EmptyState>No scored, pending treatment cases right now.</EmptyState>
      ) : (
        <Table columns={["Case", "Root cause", "At risk", "Expected value", "Reason"]}>
          {items.map((item) => (
            <Tr key={item.case_id}>
              <Td>
                <Link
                  href={`/dashboard/cases/${item.case_id}`}
                  className="font-mono text-xs text-[var(--color-accent)] hover:underline"
                >
                  {item.case_id.slice(-8)}
                </Link>
              </Td>
              <Td muted>
                <Badge tone="neutral">{humanize(item.root_cause)}</Badge>
              </Td>
              <Td>{formatInr(item.amount_at_risk)}</Td>
              <Td>
                <span className="font-medium text-[var(--color-good)]">
                  {item.expected_value_inr ? formatInr(item.expected_value_inr) : "—"}
                </span>
              </Td>
              <Td muted>{item.reason}</Td>
            </Tr>
          ))}
        </Table>
      )}
    </Card>
  );
}
