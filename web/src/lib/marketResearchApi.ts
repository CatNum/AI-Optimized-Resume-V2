export type ResearchStatus =
  | "queued"
  | "running"
  | "waiting_user"
  | "cancelling"
  | "completed"
  | "partial_completed"
  | "failed"
  | "cancelled";

export type DirectionPlan = {
  direction_name: string;
  direction_key: string;
  boss_keywords: string[];
  trends_keywords: string[];
  cities: string[];
  experience_basis: "total" | "related";
  experience_min: number;
  experience_max: number;
};

export type ResearchPlan = {
  plan_id: string;
  plan_version: number;
  status: "draft" | "confirmed" | "consumed";
  directions: DirectionPlan[];
  filter_policy: {
    employment_type: "full_time";
    allowed_recruiter_activity: string[];
  };
  budget_seconds: number;
  confirmed_at: string | null;
};

export type ResearchSnapshot = {
  research_id: string;
  plan_id: string;
  status: ResearchStatus;
  stage: string;
  direction_name: string | null;
  keyword: string | null;
  city: string | null;
  candidate_count: number;
  valid_job_count: number;
  semantic_analyzed_count: number;
  elapsed_seconds: number;
  available_actions: Array<"continue" | "cancel">;
  error: { error_code: string; user_action: string } | null;
  completion_published_at: string | null;
};

export type MarketResearchStatusResponse = {
  has_active_research: boolean;
  owned: boolean;
  result_confirmed: boolean;
  snapshot?: ResearchSnapshot;
  plan?: ResearchPlan;
  active_summary?: { research_id: string; status: ResearchStatus };
};

async function jsonRequest<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const code = payload?.detail?.code || payload?.detail?.error_code || `HTTP ${response.status}`;
    throw new Error(code);
  }
  return payload as T;
}

export function getMarketResearchStatus(sessionId: string) {
  return jsonRequest<MarketResearchStatusResponse>(
    `/v1/market-research/status?session_id=${encodeURIComponent(sessionId)}`,
  );
}

export function reviseMarketResearchPlan(
  planId: string,
  sessionId: string,
  directions: DirectionPlan[],
) {
  return jsonRequest<ResearchPlan>(`/v1/market-research/plans/${planId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      directions: directions.map(({ direction_key: _directionKey, ...direction }) => direction),
    }),
  });
}

export function confirmMarketResearchPlan(planId: string, sessionId: string) {
  return jsonRequest<ResearchPlan>(`/v1/market-research/plans/${planId}/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
}

export function continueMarketResearch(researchId: string, sessionId: string) {
  return jsonRequest<ResearchSnapshot>(`/v1/market-research/${researchId}/continue`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
}

export function cancelMarketResearch(researchId: string, sessionId: string) {
  return jsonRequest<ResearchSnapshot>(`/v1/market-research/${researchId}/cancel`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
}

export function confirmMarketResearchResult(researchId: string, sessionId: string) {
  return jsonRequest<{ confirmed: true }>(
    `/v1/market-research/${researchId}/confirm-result`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId }),
    },
  );
}
