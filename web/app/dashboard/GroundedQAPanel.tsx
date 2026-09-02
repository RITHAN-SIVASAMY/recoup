"use client";

import { useState } from "react";
import { Badge, Button, Card } from "@/components/ui";
import { askGroundedQuestion, type QAResponse } from "@/lib/dashboard-api";

export function GroundedQAPanel() {
  const [caseId, setCaseId] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<QAResponse | null>(null);
  const [busy, setBusy] = useState(false);

  async function ask() {
    if (!caseId || !question) return;
    setBusy(true);
    setAnswer(null);
    try {
      setAnswer(await askGroundedQuestion(caseId, question));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Ask the audit log" description="Answers cite only retrieved events — refuses rather than guess">
      <div className="space-y-2">
        <input
          value={caseId}
          onChange={(e) => setCaseId(e.target.value)}
          placeholder="case id"
          className="w-full rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-sm outline-none focus:border-[var(--color-accent)]"
        />
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder='e.g. "Why did we contact this account three times?"'
          className="w-full rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-sm outline-none focus:border-[var(--color-accent)]"
        />
        <Button onClick={ask} disabled={busy || !caseId || !question}>
          {busy ? "Asking…" : "Ask"}
        </Button>
      </div>
      {answer && (
        <div className="mt-4 rounded-xl border border-[var(--color-border)] bg-black/[0.015] p-4 text-sm">
          {answer.refused ? (
            <div>
              <Badge tone="warn">Refused</Badge>
              <p className="mt-2 text-[var(--color-ink-soft)]">{answer.refusal_reason}</p>
            </div>
          ) : (
            <div>
              <p className="whitespace-pre-wrap text-[var(--color-ink)]">{answer.answer}</p>
              {answer.citations.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {answer.citations.map((c) => (
                    <Badge key={c} tone="info">
                      {c.slice(-8)}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          )}
          {answer.degraded_mode && (
            <div className="mt-2 text-xs text-[var(--color-warn)]">
              Degraded mode — the model was unavailable, so this is a plain event-log summary.
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
