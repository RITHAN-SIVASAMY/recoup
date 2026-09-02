"use client";

import { useEffect, useState } from "react";
import { API_BASE_URL } from "@/lib/api";
import { Card, EmptyState } from "@/components/ui";
import { fetchModelTransparency, type ModelTransparency } from "@/lib/dashboard-api";

const CURVE_IMAGE: Record<string, string> = {
  classifier: "classifier/confusion_matrix.png",
  propensity_baseline: "propensity_baseline/roc_curve.png",
  propensity_treated: "propensity_treated/roc_curve.png",
  uplift: "uplift/qini_curve.png",
};

const TITLE: Record<string, string> = {
  classifier: "Root-cause classifier",
  propensity_baseline: "Baseline propensity",
  propensity_treated: "Treated propensity",
  uplift: "Uplift (τ)",
};

export function ModelTransparencyPanel() {
  const [data, setData] = useState<ModelTransparency | null>(null);

  useEffect(() => {
    fetchModelTransparency().then(setData);
  }, []);

  return (
    <Card title="Model transparency" description="What each model gets wrong, in its own numbers">
      {!data ? (
        <div className="h-32 animate-pulse rounded-lg bg-black/[0.03]" />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {Object.entries(data.models).map(([name, info]) => (
            <div
              key={name}
              className="rounded-xl border border-[var(--color-border)] p-4"
            >
              <h4 className="mb-2 text-sm font-semibold text-[var(--color-ink)]">
                {TITLE[name] ?? name}
              </h4>
              {!info.available ? (
                <EmptyState>
                  Not trained yet — run <code className="rounded bg-black/5 px-1 py-0.5">make train</code>.
                </EmptyState>
              ) : (
                <>
                  <img
                    src={`${API_BASE_URL}/artifacts/${CURVE_IMAGE[name]}`}
                    alt={`${name} curve`}
                    className="mb-3 w-full rounded-lg border border-[var(--color-border)]"
                  />
                  <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs text-[var(--color-ink-soft)]">
                    {typeof info.metrics?.macro_f1 === "number" && (
                      <>
                        <dt className="text-[var(--color-muted)]">macro-F1</dt>
                        <dd className="tabular-nums font-medium">{info.metrics.macro_f1.toFixed(3)}</dd>
                      </>
                    )}
                    {typeof info.metrics?.brier_score === "number" && (
                      <>
                        <dt className="text-[var(--color-muted)]">Brier score</dt>
                        <dd className="tabular-nums font-medium">{info.metrics.brier_score.toFixed(3)}</dd>
                      </>
                    )}
                    {typeof info.metrics?.auc === "number" && (
                      <>
                        <dt className="text-[var(--color-muted)]">AUC</dt>
                        <dd className="tabular-nums font-medium">{info.metrics.auc.toFixed(3)}</dd>
                      </>
                    )}
                    {typeof info.metrics?.qini_coefficient === "number" && (
                      <>
                        <dt className="text-[var(--color-muted)]">Qini</dt>
                        <dd className="tabular-nums font-medium">{info.metrics.qini_coefficient.toFixed(3)}</dd>
                      </>
                    )}
                  </dl>
                  {info.known_failure_modes.length > 0 && (
                    <div className="mt-3 border-t border-[var(--color-border)] pt-2">
                      <div className="text-[11px] font-medium uppercase tracking-wider text-[var(--color-muted)]">
                        Known failure modes
                      </div>
                      <ul className="mt-1 list-inside list-disc space-y-0.5 text-xs text-[var(--color-ink-soft)]">
                        {info.known_failure_modes.map((mode) => (
                          <li key={mode}>{mode}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
