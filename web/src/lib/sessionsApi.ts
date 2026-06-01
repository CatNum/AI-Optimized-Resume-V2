export type SessionRow = {
  session_id: string;
  title: string;
  title_source?: "fallback" | "auto" | "user";
  preview?: string;
  created_at?: string;
  last_activity_at?: string;
  message_count?: number;
  list_type?: string | null;
  archived?: boolean;
  expired?: boolean;
  activity_headline?: string | null;
};

export type ChatMessage = { role: "user" | "assistant"; content: string };

export type ListSessionsOpts = {
  q?: string;
  archived?: "false" | "true" | "all";
};

async function parseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new SessionApiError(response.status, body?.detail ?? `HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function listSessions(
  opts?: ListSessionsOpts,
): Promise<{ sessions: SessionRow[] }> {
  const params = new URLSearchParams();
  if (opts?.q) params.set("q", opts.q);
  if (opts?.archived) params.set("archived", opts.archived);
  const qs = params.toString();
  const response = await fetch(`/v1/sessions${qs ? `?${qs}` : ""}`);
  return parseJson(response);
}

export async function getSession(sessionId: string): Promise<SessionRow> {
  const response = await fetch(`/v1/sessions/${sessionId}`);
  return parseJson(response);
}

export class SessionApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function getMessages(
  sessionId: string,
): Promise<{ messages: ChatMessage[]; expired?: boolean }> {
  const response = await fetch(`/v1/sessions/${sessionId}/messages`);
  if (response.status === 404) {
    throw new SessionApiError(404, "session_not_found");
  }
  return parseJson(response);
}

export async function patchSession(
  sessionId: string,
  patch: { title?: string; archived?: boolean },
): Promise<SessionRow> {
  const response = await fetch(`/v1/sessions/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  return parseJson(response);
}

export async function deleteSession(sessionId: string): Promise<void> {
  const response = await fetch(`/v1/sessions/${sessionId}`, { method: "DELETE" });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new SessionApiError(response.status, body?.detail ?? `HTTP ${response.status}`);
  }
}

export async function createSession(): Promise<{ session_id: string }> {
  const response = await fetch("/v1/sessions/new", { method: "POST" });
  return parseJson(response);
}

export type TaskRow = {
  id: string;
  title: string;
  status: string;
  kind?: string;
};

export type TaskListRow = {
  list_id: string;
  list_type?: string | null;
  status: string;
  tasks: TaskRow[];
};

export type SessionTasksResponse = {
  session_id: string;
  active_list_id: string | null;
  lists: TaskListRow[];
  all_tasks_completed: boolean;
};

export async function getTasks(sessionId: string): Promise<SessionTasksResponse> {
  const params = new URLSearchParams({ session_id: sessionId });
  const response = await fetch(`/v1/tasks?${params}`);
  return parseJson(response);
}
