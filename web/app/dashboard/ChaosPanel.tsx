"use client";

import { useEffect, useState } from "react";
import { Badge, Button, Card } from "@/components/ui";
import { fetchChaosScenarios, runChaosScenario, type ChaosResult } from "@/lib/dashboard-api";
import { humanize } from "@/lib/format";

const NOT_LIVE_RUNNABLE = new Set(["malformed_payload", "clock_skew"]);

export function ChaosPanel() {
  const [scenarios, setScenarios] = useState<Record<string, string> | null>(null);
  const [running, setRunning] = useState<string | null>(null);
  const [result, setResult] = useState<ChaosResult | null>(null);

  useEffect(() => {
    fetchChaosScenarios().then(setScenarios);
  }, []);

  async function breakIt(scenario: string) {
    setRunning(scenario);
    setResult(null);
    try {
      setResult(await runChaosScenario(scenario));
    } finally {
      setRunning(null);
    }
  }

  return (
    <Card title="Break it" description="Live failure injection — proves the system recovers, doesn't just claim to">
      {!scenarios ? (
        <div className="h-24 animate-pulse rounded-lg bg-black/[0.03]" />
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Object.entries(scenarios).map(([name, description]) => {
            const disabled = NOT_LIVE_RUNNABLE.has(name) || running !== null;
            return (
              <div key={name} className="rounded-xl border border-[var(--color-border)] p-4">
                <div className="text-sm font-semibold text-[var(--color-ink)]">
                  {humanize(name)}
                </div>
                <p className="mt-1 text-xs text-[var(--color-muted)]">{description}</p>
                <div className="mt-3">
                  <Button variant="danger" size="sm" onClick={() => breakIt(name)} disabled={disabled}>
                    {running === name
                      ? "Running…"
                      : NOT_LIVE_RUNNABLE.has(name)
                        ? "Proven by test suite"
                        : "Break it"}
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}
      {result && (
        <div className="mt-4 rounded-xl border border-[var(--color-border)] p-4">
          <div className="mb-3 flex items-center gap-2">
            <Badge tone={result.passed ? "good" : "bad"}>
              {result.passed ? "recovered gracefully" : "FAILED"}
            </Badge>
            <span className="text-xs text-[var(--color-muted)]">case {result.case_id.slice(-8)}</span>
          </div>
          <ol className="list-inside list-decimal space-y-1 text-sm text-[var(--color-ink-soft)]">
            {result.narrative.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ol>
          <div className="mt-3 space-y-1.5 border-t border-[var(--color-border)] pt-3">
            {result.outcomes.map((outcome) => (
              <div key={outcome.label} className="flex items-start gap-2 text-xs">
                <Badge tone={outcome.passed ? "good" : "bad"}>{outcome.passed ? "✓" : "✗"}</Badge>
                <span className="text-[var(--color-ink-soft)]">
                  {outcome.label} — <span className="text-[var(--color-muted)]">{outcome.detail}</span>
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}
