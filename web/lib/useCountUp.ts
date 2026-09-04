"use client";

import { useEffect, useRef, useState } from "react";

/** Animates from 0 to `target` over `durationMs`, purely cosmetic — callers
 * still render the authoritative formatted string once settled, since this
 * hook parses through a JS number and shouldn't be trusted with precision. */
export function useCountUp(target: number, durationMs = 900): number {
  const [value, setValue] = useState(0);
  const startRef = useRef<number | null>(null);
  const fromRef = useRef(0);

  useEffect(() => {
    if (!Number.isFinite(target)) {
      setValue(target);
      return;
    }
    fromRef.current = 0;
    startRef.current = null;
    let frame: number;

    function tick(now: number) {
      if (startRef.current === null) startRef.current = now;
      const elapsed = now - startRef.current;
      const t = Math.min(1, elapsed / durationMs);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(fromRef.current + (target - fromRef.current) * eased);
      if (t < 1) frame = requestAnimationFrame(tick);
    }
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, durationMs]);

  return value;
}
