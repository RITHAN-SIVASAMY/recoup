export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type Fix = {
  kind: string;
  headline: string;
  explanation: string;
};

export type RecoveryContext = {
  case_id: string;
  amount_at_risk: string;
  root_cause: string | null;
  fix: Fix;
  test_mode: boolean;
};

export type ApiError = {
  status: number;
  detail: string;
};

export async function fetchRecoveryContext(
  token: string,
): Promise<{ ok: true; data: RecoveryContext } | { ok: false; error: ApiError }> {
  const response = await fetch(`${API_BASE_URL}/api/recovery/${token}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "something went wrong" }));
    return { ok: false, error: { status: response.status, detail: body.detail ?? "unknown error" } };
  }
  return { ok: true, data: await response.json() };
}

async function postJson<T>(
  path: string,
  body?: unknown,
): Promise<{ ok: true; data: T } | { ok: false; error: ApiError }> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    const parsed = await response.json().catch(() => ({ detail: "something went wrong" }));
    return { ok: false, error: { status: response.status, detail: parsed.detail ?? "unknown error" } };
  }
  return { ok: true, data: await response.json() };
}

export function createPayment(token: string) {
  return postJson<{ checkout_url: string; provider_ref: string }>(
    `/api/recovery/${token}/pay`,
  );
}

export function simulatePayment(token: string) {
  return postJson<{ status: string }>(`/api/recovery/${token}/simulate-payment`);
}

export function optOut(token: string) {
  return postJson<{ status: string }>(`/api/recovery/${token}/opt-out`);
}

export function remindLater(token: string, remindAt: string) {
  return postJson<{ status: string; remind_at: string }>(
    `/api/recovery/${token}/remind-later`,
    { remind_at: remindAt },
  );
}

export function switchMethod(token: string, toChannel: string) {
  return postJson<{ status: string }>(`/api/recovery/${token}/method-switch`, {
    to_channel: toChannel,
  });
}
