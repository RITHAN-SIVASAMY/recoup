"use client";

import { useEffect, useRef, useState } from "react";

/** Animates toward `target`, purely cosmetic — callers still render the
 * authoritative formatted string once settled, since this hook parses through
 * a JS number and shouldn't be trusted with precision.
 *
 * Animates from whatever was on screen, not from zero, and does nothing at all
 * when the target hasn't moved. The dashboard re-fetches on every SSE
 * `case_update`, so a hook that restarted from zero on each render left the
 * headline figures permanently mid-animation and unreadable under live
 * traffic. */
export function useCountUp(target: number, durationMs = 900): number {
  const [value, setValue] = useState(target);
  const valueRef = useRef(target);
  const settledTargetRef = useRef(target);

  useEffect(() => {
    valueRef.current = value;
  }, [value]);

  useEffect(() => {
    if (!Number.isFinite(target)) {
      setValue(target);
      return;
    }
    // Same number as last time: leave it alone rather than replay the count-up.
    if (settledTargetRef.current === target) return;

    const from = Number.isFinite(valueRef.current) ? valueRef.current : 0;
    settledTargetRef.current = target;
    let start: number | null = null;
    let frame = 0;

    function tick(now: number) {
      if (start === null) start = now;
      const t = Math.min(1, (now - start) / durationMs);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(from + (target - from) * eased);
      if (t < 1) frame = requestAnimationFrame(tick);
    }
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, durationMs]);

  return value;
}
