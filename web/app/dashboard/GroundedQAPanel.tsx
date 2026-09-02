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
    <Card title="Ask the audit log">
      <div className="space-y-2">
        <input
          value={caseId}
          onChange={(e) => setCaseId(e.target.value)}
          placeholder="case id"
          className="w-full rounded-md border border-black/15 px-3 py-1.5 text-sm"
        />
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder='e.g. "Why did we contact this account three times?"'
          className="w-full rounded-md border border-black/15 px-3 py-1.5 text-sm"
        />
        <Button onClick={ask} disabled={busy || !caseId || !question}>
          {busy ? "Asking…" : "Ask"}
        </Button>
      </div>
      {answer && (
        <div className="mt-4 rounded-md border border-black/10 bg-black/[0.02] p-3 text-sm">
          {answer.refused ? (
            <div>
              <Badge tone="warn">Refused</Badge>
              <p className="mt-2 text-black/70">{answer.refusal_reason}</p>
            </div>
          ) : (
            <div>
              <p className="whitespace-pre-wrap text-black/80">{answer.answer}</p>
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
            <div className="mt-2 text-xs text-amber-700">
              Degraded mode — the model was unavailable, so this is a plain event-log summary.
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
