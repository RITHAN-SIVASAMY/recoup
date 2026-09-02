"use client";

import { useEffect, useState } from "react";
import { Badge, Button } from "@/components/ui";
import { disengageKillswitch, engageKillswitch, fetchKillswitchStatus } from "@/lib/dashboard-api";

export function KillswitchControl({ onChanged }: { onChanged: () => void }) {
  const [engaged, setEngaged] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchKillswitchStatus().then((s) => setEngaged(s.engaged));
  }, []);

  async function toggle() {
    setBusy(true);
    try {
      if (engaged) {
        const result = await disengageKillswitch();
        setEngaged(result.engaged);
      } else {
        const result = await engageKillswitch();
        setEngaged(result.engaged);
      }
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-2">
      <Badge tone={engaged ? "bad" : "good"} dot>
        kill switch {engaged === null ? "…" : engaged ? "ENGAGED" : "off"}
      </Badge>
      <Button
        variant={engaged ? "secondary" : "danger"}
        size="sm"
        onClick={toggle}
        disabled={busy || engaged === null}
      >
        {engaged ? "Disengage" : "Engage kill switch"}
      </Button>
    </div>
  );
}
