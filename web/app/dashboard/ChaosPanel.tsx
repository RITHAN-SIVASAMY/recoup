"use client";

import { useEffect, useState } from "react";
import { Badge, Button, Card } from "@/components/ui";
import { fetchChaosScenarios, runChaosScenario, type ChaosResult } from "@/lib/dashboard-api";

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
    <Card title="Break it — live failure injection" className="col-span-full">
      {!scenarios ? (
        <div className="text-sm text-black/50">Loading…</div>
      ) : (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {Object.entries(scenarios).map(([name, description]) => {
            const disabled = NOT_LIVE_RUNNABLE.has(name) || running !== null;
            return (
              <div key={name} className="rounded-md border border-black/10 p-3">
                <div className="text-sm font-medium">{name.replace(/_/g, " ")}</div>
                <p className="mt-1 text-xs text-black/50">{description}</p>
                <div className="mt-2">
                  <Button
                    variant="danger"
                    onClick={() => breakIt(name)}
                    disabled={disabled}
                  >
                    {running === name ? "Running…" : NOT_LIVE_RUNNABLE.has(name) ? "Proven by test suite" : "Break it"}
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}
      {result && (
        <div className="mt-4 rounded-md border border-black/10 p-3">
          <div className="mb-2 flex items-center gap-2">
            <Badge tone={result.passed ? "good" : "bad"}>
              {result.passed ? "recovered gracefully" : "FAILED"}
            </Badge>
            <span className="text-xs text-black/50">case {result.case_id.slice(-8)}</span>
          </div>
          <ol className="list-inside list-decimal space-y-1 text-sm text-black/70">
            {result.narrative.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ol>
          <div className="mt-2 space-y-1">
            {result.outcomes.map((outcome) => (
              <div key={outcome.label} className="flex items-start gap-2 text-xs">
                <Badge tone={outcome.passed ? "good" : "bad"}>{outcome.passed ? "✓" : "✗"}</Badge>
                <span className="text-black/70">
                  {outcome.label} — <span className="text-black/50">{outcome.detail}</span>
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}
