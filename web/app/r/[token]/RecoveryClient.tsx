"use client";

import { useState } from "react";
import { createPayment, optOut, remindLater, type RecoveryContext } from "@/lib/api";

type Status = "idle" | "working" | "done" | "error";

const MIN_REMIND_AT = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
const MAX_REMIND_AT = new Date(Date.now() + 89 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);

export function RecoveryClient({
  token,
  context,
}: {
  token: string;
  context: RecoveryContext;
}) {
  const [payStatus, setPayStatus] = useState<Status>("idle");
  const [optOutStatus, setOptOutStatus] = useState<Status>("idle");
  const [remindStatus, setRemindStatus] = useState<Status>("idle");
  const [remindAt, setRemindAt] = useState(MIN_REMIND_AT);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [showRemindForm, setShowRemindForm] = useState(false);

  async function handlePay() {
    setPayStatus("working");
    setErrorMessage(null);
    const result = await createPayment(token);
    if (!result.ok) {
      setPayStatus("error");
      setErrorMessage(result.error.detail);
      return;
    }
    window.location.href = result.data.checkout_url;
  }

  async function handleOptOut() {
    setOptOutStatus("working");
    setErrorMessage(null);
    const result = await optOut(token);
    if (!result.ok) {
      setOptOutStatus("error");
      setErrorMessage(result.error.detail);
      return;
    }
    setOptOutStatus("done");
  }

  async function handleRemindLater(event: React.FormEvent) {
    event.preventDefault();
    setRemindStatus("working");
    setErrorMessage(null);
    const result = await remindLater(token, remindAt);
    if (!result.ok) {
      setRemindStatus("error");
      setErrorMessage(result.error.detail);
      return;
    }
    setRemindStatus("done");
  }

  const consumed = optOutStatus === "done" || remindStatus === "done";

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col gap-6 px-6 py-10">
      <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-center text-xs font-medium text-amber-800">
        Test mode — this uses synthetic data. No real payment will be made.
      </div>

      {!consumed && (
        <>
          <header className="flex flex-col gap-1">
            <h1 className="text-xl font-semibold text-gray-900">{context.fix.headline}</h1>
            <p className="text-sm text-gray-600">{context.fix.explanation}</p>
          </header>

          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <p className="text-xs uppercase tracking-wide text-gray-400">Amount</p>
            <p className="text-2xl font-semibold text-gray-900">₹{context.amount_at_risk}</p>
          </div>

          <button
            type="button"
            onClick={handlePay}
            disabled={payStatus === "working"}
            className="w-full rounded-md bg-indigo-600 px-4 py-3 text-center font-medium text-white transition hover:bg-indigo-700 disabled:opacity-60"
          >
            {payStatus === "working" ? "Preparing payment…" : "Pay now"}
          </button>

          {errorMessage && (payStatus === "error" || optOutStatus === "error" || remindStatus === "error") && (
            <p role="alert" className="text-sm text-red-600">
              {errorMessage}
            </p>
          )}

          <div className="flex flex-col gap-3 border-t border-gray-100 pt-4">
            {!showRemindForm ? (
              <button
                type="button"
                onClick={() => setShowRemindForm(true)}
                className="text-sm font-medium text-gray-600 underline underline-offset-2 hover:text-gray-900"
              >
                Remind me later instead
              </button>
            ) : (
              <form onSubmit={handleRemindLater} className="flex flex-col gap-2">
                <label htmlFor="remind-at" className="text-sm font-medium text-gray-700">
                  Remind me on
                </label>
                <input
                  id="remind-at"
                  type="date"
                  required
                  min={MIN_REMIND_AT}
                  max={MAX_REMIND_AT}
                  value={remindAt}
                  onChange={(event) => setRemindAt(event.target.value)}
                  className="rounded-md border border-gray-300 px-3 py-2 text-sm"
                />
                <button
                  type="submit"
                  disabled={remindStatus === "working"}
                  className="rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-60"
                >
                  {remindStatus === "working" ? "Saving…" : "Confirm reminder"}
                </button>
              </form>
            )}

            <button
              type="button"
              onClick={handleOptOut}
              disabled={optOutStatus === "working"}
              className="text-sm text-gray-400 underline underline-offset-2 hover:text-gray-600 disabled:opacity-60"
            >
              {optOutStatus === "working" ? "Opting out…" : "Stop contacting me about this"}
            </button>
          </div>
        </>
      )}

      {optOutStatus === "done" && (
        <p className="text-center text-sm text-gray-600" role="status">
          Understood — you won&apos;t be contacted about this again.
        </p>
      )}
      {remindStatus === "done" && (
        <p className="text-center text-sm text-gray-600" role="status">
          Got it — we&apos;ll remind you on {remindAt}.
        </p>
      )}
    </main>
  );
}
