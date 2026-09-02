import { API_BASE_URL } from "./api";

export type BreakdownRow = {
  dimension: string;
  key: string;
  lift_pp: number;
  p_value: number;
  significant: boolean;
  n_treated: number;
  n_control: number;
};

export type BatchReport = {
  batch_id: string;
  seed: number;
  n_cases_total: number;
  at_risk_inr: string;
  raw_recovered_inr: string;
  incremental_inr: string;
  ci_low_inr: string;
  ci_high_inr: string;
  lift_pp: number;
  z: number;
  p_value: number;
  significant: boolean;
  n_treated: number;
  n_control: number;
  mde_pp: number;
  cuped_adjusted_inr: string;
  cuped_theta: number;
  spend_on_contact_inr: string;
  cost_per_inr_recovered: string | null;
  saved_by_not_contacting_inr: string;
  actions_blocked_by_policy: Record<string, number>;
  contacts_per_recovered_case_median: number | null;
  max_touches_respected_rate: number;
  cases_in_exception_queue: number;
  exception_queue_all_triaged: boolean;
  audit_chain_verified: boolean;
  replay_equality_passed: boolean;
  exclusions: Record<string, number>;
  breakdowns: BreakdownRow[];
};

export type BatchSummary = {
  batch_report: BatchReport | null;
  cases_by_state: Record<string, number>;
  audit_chain_verified: boolean;
  replay_equality_passed: boolean;
};

export type WorkQueueItem = {
  case_id: string;
  root_cause: string | null;
  amount_at_risk: string;
  uplift: number;
  uplift_segment: string | null;
  expected_value_inr: string | null;
  reason: string;
  updated_at: string;
};

export type ExceptionQueueItem = {
  case_id: string;
  root_cause: string | null;
  amount_at_risk: string;
  reason: string;
  occurred_at: string;
};

export type ComplianceView = {
  blocked_by_category: Record<string, number>;
  total_blocked: number;
};

export type CaseEventRow = {
  event_id: string;
  seq: number;
  occurred_at: string;
  event_type: string;
  actor: { kind: string; identifier: string };
  payload: Record<string, unknown>;
  policy_version: string | null;
  model_versions: Record<string, string> | null;
};

export type CaseTimeline = {
  case: {
    case_id: string;
    merchant_id: string;
    source_type: string;
    amount_at_risk: string;
    resolution_state: string;
    cohort: string | null;
    root_cause: string | null;
    created_at: string;
    updated_at: string;
  };
  events: CaseEventRow[];
};

export type ModelInfo = {
  metrics: Record<string, unknown> | null;
  known_failure_modes: string[];
  available: boolean;
};

export type ModelTransparency = {
  models: Record<string, ModelInfo>;
};

export type QAResponse = {
  answer: string;
  citations: string[];
  refused: boolean;
  refusal_reason: string | null;
  degraded_mode: boolean;
  prompt_version: string;
  prompt_hash: string;
};

export type WhatIfProjection = {
  cases_considered: number;
  baseline_would_contact: number;
  projected_would_contact: number;
  newly_contactable: number;
  newly_uneconomic: number;
  newly_requires_approval: number;
  no_longer_requires_approval: number;
  newly_over_contact_cap: number;
  is_projection: true;
};

export type ChaosOutcome = { label: string; passed: boolean; detail: string };
export type ChaosResult = {
  scenario: string;
  case_id: string;
  passed: boolean;
  narrative: string[];
  outcomes: ChaosOutcome[];
};

export type Approval = {
  approval_id: string;
  case_id: string;
  root_cause: string | null;
  action_type: string;
  channel: string | null;
  uplift: number;
  expected_value_inr: string;
  estimated_cost_inr: string;
  rule_id: string;
  reason: string;
  requested_at: string;
};

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`${path} -> HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    throw new Error(`${path} -> HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const fetchBatchSummary = () => getJson<BatchSummary>("/dashboard/summary");
export const fetchWorkQueue = (limit = 50) =>
  getJson<WorkQueueItem[]>(`/dashboard/queue?limit=${limit}`);
export const fetchExceptionQueue = () =>
  getJson<ExceptionQueueItem[]>("/dashboard/exceptions");
export const fetchComplianceView = () => getJson<ComplianceView>("/dashboard/compliance");
export const fetchCaseTimeline = (caseId: string) =>
  getJson<CaseTimeline>(`/dashboard/cases/${caseId}/timeline`);
export const fetchModelTransparency = () =>
  getJson<ModelTransparency>("/dashboard/models");
export const fetchChaosScenarios = () => getJson<Record<string, string>>("/dashboard/chaos/scenarios");
export const fetchApprovals = () => getJson<Approval[]>("/approvals");
export const fetchKillswitchStatus = () => getJson<{ engaged: boolean }>("/killswitch");

export const askGroundedQuestion = (caseId: string, question: string) =>
  postJson<QAResponse>("/dashboard/qa", { case_id: caseId, question });

export const runWhatIf = (params: {
  ev_floor_inr?: string;
  channel_cost_inr?: string;
  approval_threshold_inr?: string;
  max_contacts?: number;
}) => postJson<WhatIfProjection>("/dashboard/what-if", params);

export const runChaosScenario = (scenario: string) =>
  postJson<ChaosResult>(`/dashboard/chaos/${scenario}`);

export const grantApproval = (approvalId: string) =>
  postJson<{ approval_id: string; status: string; staged_action_id: string }>(
    `/approvals/${approvalId}/grant`,
  );
export const rejectApproval = (approvalId: string) =>
  postJson<{ approval_id: string; status: string }>(`/approvals/${approvalId}/reject`);
export const cancelStagedAction = (stagedActionId: string) =>
  postJson<{ staged_action_id: string; status: string }>(`/staged/${stagedActionId}/cancel`);
export const engageKillswitch = () =>
  postJson<{ engaged: boolean; cancelled_staged_actions: number }>("/killswitch/engage");
export const disengageKillswitch = () =>
  postJson<{ engaged: boolean }>("/killswitch/disengage");

export function exportUrl(format: "json" | "markdown"): string {
  return `${API_BASE_URL}/dashboard/export?format=${format}`;
}

export function streamUrl(): string {
  return `${API_BASE_URL}/dashboard/stream`;
}
