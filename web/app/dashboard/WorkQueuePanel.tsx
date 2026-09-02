"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Card, EmptyState, Table } from "@/components/ui";
import { fetchWorkQueue, type WorkQueueItem } from "@/lib/dashboard-api";
import { formatInr } from "@/lib/format";

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
    <Card title="Work queue — ranked by expected incremental value">
      {items === null ? (
        <EmptyState>Loading…</EmptyState>
      ) : items.length === 0 ? (
        <EmptyState>No scored, pending treatment cases right now.</EmptyState>
      ) : (
        <Table columns={["Case", "Root cause", "At risk", "Expected value", "Reason"]}>
          {items.map((item) => (
            <tr key={item.case_id}>
              <td className="py-2 pr-4">
                <Link
                  href={`/dashboard/cases/${item.case_id}`}
                  className="text-[var(--color-accent)] hover:underline"
                >
                  {item.case_id.slice(-8)}
                </Link>
              </td>
              <td className="py-2 pr-4">{item.root_cause ?? "—"}</td>
              <td className="py-2 pr-4 tabular-nums">{formatInr(item.amount_at_risk)}</td>
              <td className="py-2 pr-4 tabular-nums">
                {item.expected_value_inr ? formatInr(item.expected_value_inr) : "—"}
              </td>
              <td className="py-2 pr-4 text-black/60">{item.reason}</td>
            </tr>
          ))}
        </Table>
      )}
    </Card>
  );
}
