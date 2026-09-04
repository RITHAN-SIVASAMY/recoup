"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Card, EmptyState, Table, Td, Tr } from "@/components/ui";
import { fetchExceptionQueue, type ExceptionQueueItem } from "@/lib/dashboard-api";
import { formatDate, formatInr, humanize } from "@/lib/format";

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
    <Card
      title="Exception queue"
      description="Cases needing human handling — nothing here has been silently dropped"
    >
      {items === null ? (
        <div className="h-32 animate-pulse rounded-lg bg-black/[0.03]" />
      ) : items.length === 0 ? (
        <EmptyState>Empty — nothing has been lost or gone unhandled.</EmptyState>
      ) : (
        <div className="max-h-96 overflow-y-auto">
          <Table columns={["Case", "Root cause", "At risk", "Reason", "When"]}>
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
                <Td muted>{humanize(item.root_cause)}</Td>
                <Td>{formatInr(item.amount_at_risk)}</Td>
                <Td muted>{item.reason}</Td>
                <Td muted>{formatDate(item.occurred_at)}</Td>
              </Tr>
            ))}
          </Table>
        </div>
      )}
    </Card>
  );
}
