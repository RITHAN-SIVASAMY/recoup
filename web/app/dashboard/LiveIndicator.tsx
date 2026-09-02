"use client";

import { useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui";
import { streamUrl } from "@/lib/dashboard-api";

/** FR-15.9: a genuinely live connection to the SSE stream. The dot pulses on
 * every case_update event, which is the demo's own "prove it's live" beat. */
export function LiveIndicator({ onCaseUpdate }: { onCaseUpdate: () => void }) {
  const [connected, setConnected] = useState(false);
  const [pulse, setPulse] = useState(false);
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    const source = new EventSource(streamUrl());
    sourceRef.current = source;
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.addEventListener("case_update", () => {
      setPulse(true);
      onCaseUpdate();
      setTimeout(() => setPulse(false), 600);
    });
    return () => source.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex items-center gap-1.5">
      <span
        className={`inline-block h-2 w-2 rounded-full transition-transform ${
          connected ? (pulse ? "scale-150 bg-[var(--color-good)]" : "bg-[var(--color-good)]") : "bg-black/20"
        }`}
      />
      <Badge tone={connected ? "good" : "neutral"}>{connected ? "live" : "connecting…"}</Badge>
    </div>
  );
}
