import { redirect } from "next/navigation";

import { getSessionToken } from "./session";

const API_BASE_URL = process.env.API_BASE_URL;

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

/** Call the API with the session's token attached. Server-side only: the
 *  token must never reach the browser. */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (!API_BASE_URL) throw new Error("API_BASE_URL is not set");

  const token = await getSessionToken();
  if (!token) redirect("/login");

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      ...init.headers,
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    // The queue changes while it is being worked, so never serve a cached
    // page of it.
    cache: "no-store",
  });

  if (response.status === 401) redirect("/login");

  if (!response.ok) {
    const detail = await response.text();
    let message = detail;
    try {
      message = JSON.parse(detail).detail ?? detail;
    } catch {
      /* not JSON; use the raw body */
    }
    throw new ApiError(response.status, message);
  }

  return response.json() as Promise<T>;
}

export type QueueItem = {
  id: string;
  message: string;
  intent: string | null;
  confidence: number | null;
  escalate: boolean;
  escalation_reason: string | null;
  status: string;
  channel: string;
  created_at: string;
};

export type Citation = {
  source_id: string;
  title: string;
  updated_at: string;
  excerpt: string;
};

export type AuditEntry = {
  action: string;
  actor_email: string | null;
  from_status: string | null;
  to_status: string | null;
  detail: Record<string, unknown>;
  created_at: string;
};

export type EventDetail = QueueItem & {
  customer_email: string | null;
  draft_reply: string | null;
  final_reply: string | null;
  citations: Citation[];
  model: string | null;
  latency_ms: number | null;
  audit: AuditEntry[];
};

export type QueuePage = { items: QueueItem[]; next_cursor: string | null };
