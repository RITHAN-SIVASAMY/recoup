"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Card, EmptyState, Table } from "@/components/ui";
import { fetchExceptionQueue, type ExceptionQueueItem } from "@/lib/dashboard-api";
import { formatDate, formatInr } from "@/lib/format";

export function ExceptionQueuePanel({ refreshKey }: { refreshKey: number }) {
  const [items, setItems] = useState<ExceptionQueueItem[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchExceptionQueue().then((data) => {
      if (!cancelled) setItems(data);
    });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  return (
    <Card title="Exception queue">
      {items === null ? (
        <EmptyState>Loading…</EmptyState>
      ) : items.length === 0 ? (
        <EmptyState>Empty — nothing has been lost or gone unhandled.</EmptyState>
      ) : (
        <Table columns={["Case", "Root cause", "At risk", "Reason", "When"]}>
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
              <td className="py-2 pr-4 text-black/60">{item.reason}</td>
              <td className="py-2 pr-4 text-black/40">{formatDate(item.occurred_at)}</td>
            </tr>
          ))}
        </Table>
      )}
    </Card>
  );
}
