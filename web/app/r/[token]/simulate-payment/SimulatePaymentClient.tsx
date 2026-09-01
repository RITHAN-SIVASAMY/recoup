"use client";

import { useState } from "react";
import { simulatePayment } from "@/lib/api";

type Status = "idle" | "working" | "done" | "error";

export function SimulatePaymentClient({ token }: { token: string }) {
  const [status, setStatus] = useState<Status>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function handleConfirm() {
    setStatus("working");
    const result = await simulatePayment(token);
    if (!result.ok) {
      setStatus("error");
      setErrorMessage(result.error.detail);
      return;
    }
    setStatus("done");
  }

  if (status === "done") {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-3 px-6 text-center">
        <div className="text-4xl">✅</div>
        <h1 className="text-xl font-semibold">Payment recovered</h1>
        <p className="max-w-sm text-sm text-gray-500">
          This was a simulated test-mode payment. The case has been marked recovered.
        </p>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 px-6 text-center">
      <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-800">
        Test mode — no real Razorpay checkout is configured. This confirms a synthetic payment.
      </div>
      <h1 className="text-xl font-semibold">Simulate a successful payment?</h1>
      <p className="max-w-sm text-sm text-gray-500">
        In production this step is Razorpay&apos;s real hosted checkout. Confirming here marks
        this case recovered exactly as a real payment success webhook would.
      </p>
      <button
        type="button"
        onClick={handleConfirm}
        disabled={status === "working"}
        className="rounded-md bg-indigo-600 px-4 py-3 font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
      >
        {status === "working" ? "Confirming…" : "Simulate payment"}
      </button>
      {status === "error" && (
        <p role="alert" className="text-sm text-red-600">
          {errorMessage}
        </p>
      )}
    </main>
  );
}
