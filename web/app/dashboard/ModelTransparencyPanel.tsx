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

  if (!data) return <Card title="Model transparency">Loading…</Card>;

  return (
    <Card title="Model transparency" className="col-span-full">
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
        {Object.entries(data.models).map(([name, info]) => (
          <div key={name} className="rounded-md border border-black/10 p-3">
            <h4 className="mb-2 text-sm font-semibold">{TITLE[name] ?? name}</h4>
            {!info.available ? (
              <EmptyState>Not trained yet — run `make train`.</EmptyState>
            ) : (
              <>
                <img
                  src={`${API_BASE_URL}/artifacts/${CURVE_IMAGE[name]}`}
                  alt={`${name} curve`}
                  className="mb-2 w-full rounded border border-black/5"
                />
                <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-black/60">
                  {typeof info.metrics?.macro_f1 === "number" && (
                    <>
                      <dt>macro-F1</dt>
                      <dd className="tabular-nums">{info.metrics.macro_f1.toFixed(3)}</dd>
                    </>
                  )}
                  {typeof info.metrics?.brier_score === "number" && (
                    <>
                      <dt>Brier score</dt>
                      <dd className="tabular-nums">{info.metrics.brier_score.toFixed(3)}</dd>
                    </>
                  )}
                  {typeof info.metrics?.auc === "number" && (
                    <>
                      <dt>AUC</dt>
                      <dd className="tabular-nums">{info.metrics.auc.toFixed(3)}</dd>
                    </>
                  )}
                  {typeof info.metrics?.qini_coefficient === "number" && (
                    <>
                      <dt>Qini</dt>
                      <dd className="tabular-nums">{info.metrics.qini_coefficient.toFixed(3)}</dd>
                    </>
                  )}
                </dl>
                {info.known_failure_modes.length > 0 && (
                  <div className="mt-2">
                    <div className="text-xs font-medium text-black/50">Known failure modes</div>
                    <ul className="mt-1 list-inside list-disc text-xs text-black/60">
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
    </Card>
  );
}
