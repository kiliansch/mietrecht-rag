// Thin fetch wrappers over the FastAPI backend. Base path '/api' (Vite proxies it).
// Identity is carried by the Authorization header — no user_name params anywhere.

import type {
  AppConfig,
  AuthUser,
  CaseDetail,
  CaseDocument,
  CaseSummary,
  ChatHistoryMessage,
  ChatSummary,
  Deadline,
  DeadlineStatus,
  DocumentKind,
  EvalScores,
  EvalStatus,
  LoginResponse,
  Profile,
  Role,
  SourceDetail,
  UserAccount,
} from "./types";

// --- Auth token plumbing -------------------------------------------------------------

let token: string | null = localStorage.getItem("token");
let onUnauthorized: (() => void) | null = null;

export function setToken(t: string | null) {
  token = t;
  if (t) localStorage.setItem("token", t);
  else localStorage.removeItem("token");
}

/** Registered by the session provider: called on any 401 to force a logout. */
export function setOnUnauthorized(cb: (() => void) | null) {
  onUnauthorized = cb;
}

export const authHeaders = (): Record<string, string> =>
  token ? { Authorization: `Bearer ${token}` } : {};

const jsonHeaders = (): Record<string, string> => ({
  "Content-Type": "application/json",
  ...authHeaders(),
});

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    if (res.status === 401 && onUnauthorized) onUnauthorized();
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

// --- Auth ------------------------------------------------------------------------------

export const postLogin = (username: string, password: string) =>
  fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  }).then(json<LoginResponse>);

export const getMe = () => fetch("/api/auth/me", { headers: authHeaders() }).then(json<AuthUser>);

export const patchPersona = (persona: Role) =>
  fetch("/api/auth/me", {
    method: "PATCH",
    headers: jsonHeaders(),
    body: JSON.stringify({ persona }),
  }).then(json<AuthUser>);

// --- App -------------------------------------------------------------------------------

export const getConfig = () => fetch("/api/config").then(json<AppConfig>);

export const validateInput = (text: string) =>
  fetch("/api/chat/validate", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ text }),
  }).then(json<{ error: string | null }>);

export interface ChatBody {
  thread_id?: string; // free chat
  case_id?: string; // case chat: the server uses the case's own thread
  role: string;
  model: string;
  message: string;
  language?: string; // answer language ("de" | "en")
}

// Returns the raw streaming Response; the caller consumes it with parseSSE.
// An optional AbortSignal lets the caller cancel the stream (e.g. on thread switch).
export const postChat = (body: ChatBody, signal?: AbortSignal) =>
  fetch("/api/chat", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(body),
    signal,
  });

// Continue a thread parked on a tool-approval interrupt (SSE, same protocol as chat).
export const postResume = (
  body: {
    case_id?: string;
    thread_id?: string;
    interrupt_id: string;
    decision: "approve" | "reject";
    // Set when the paused turn was a document analysis: the continuation's final
    // answer is persisted as that document's analysis summary.
    document_id?: string;
    language?: string;
  },
  signal?: AbortSignal,
) =>
  fetch("/api/chat/resume", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(body),
    signal,
  });

export const getProfile = () =>
  fetch("/api/profile", { headers: authHeaders() }).then(json<Profile>);

// --- Saved chat history ("Verlauf") ----------------------------------------------------

export const getChats = () =>
  fetch("/api/chats", { headers: authHeaders() }).then(json<ChatSummary[]>);

export const getChatMessages = (threadId: string) =>
  fetch(`/api/chats/${threadId}/messages`, { headers: authHeaders() }).then(
    json<ChatHistoryMessage[]>,
  );

export const renameChat = (threadId: string, title: string) =>
  fetch(`/api/chats/${threadId}`, {
    method: "PATCH",
    headers: jsonHeaders(),
    body: JSON.stringify({ title }),
  }).then(json<{ thread_id: string; title: string }>);

export const deleteChat = (threadId: string) =>
  fetch(`/api/chats/${threadId}`, { method: "DELETE", headers: authHeaders() });

// Full statute-§ / decision text behind a citation, for the in-app source viewer.
export const getSource = (collection: string, url: string) =>
  fetch(
    `/api/sources?collection=${encodeURIComponent(collection)}&url=${encodeURIComponent(url)}`,
    { headers: authHeaders() },
  ).then(json<SourceDetail>);

export const postFeedback = (body: {
  thread_id: string;
  question: string;
  answer: string;
  rating: number;
  comment?: string;
}) =>
  fetch("/api/feedback", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });

// --- Cases ("Mietfall-Akten") ----------------------------------------------------------

export const getCases = () =>
  fetch("/api/cases", { headers: authHeaders() }).then(json<CaseSummary[]>);

export const createCase = (title: string) =>
  fetch("/api/cases", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ title }),
  }).then(json<CaseSummary>);

export const getCase = (caseId: string) =>
  fetch(`/api/cases/${caseId}`, { headers: authHeaders() }).then(json<CaseDetail>);

export const deleteCase = (caseId: string) =>
  fetch(`/api/cases/${caseId}`, { method: "DELETE", headers: authHeaders() });

export const uploadCaseDocument = (caseId: string, file: File, kind: DocumentKind) => {
  const form = new FormData();
  form.append("file", file);
  form.append("kind", kind);
  return fetch(`/api/cases/${caseId}/documents`, {
    method: "POST",
    headers: authHeaders(),
    body: form,
  }).then(json<CaseDocument>);
};

export const getCaseDocument = (caseId: string, docId: string) =>
  fetch(`/api/cases/${caseId}/documents/${docId}`, { headers: authHeaders() }).then(
    json<CaseDocument>,
  );

export const deleteCaseDocument = (caseId: string, docId: string) =>
  fetch(`/api/cases/${caseId}/documents/${docId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });

// SSE streams (raw Response; consumed with parseSSE).
export const analyseCaseDocument = (caseId: string, docId: string, signal?: AbortSignal) =>
  fetch(`/api/cases/${caseId}/documents/${docId}/analyse`, {
    method: "POST",
    headers: authHeaders(),
    signal,
  });

export const reviewCaseContract = (caseId: string, docId: string) =>
  fetch(`/api/cases/${caseId}/documents/${docId}/review`, {
    method: "POST",
    headers: authHeaders(),
  });

export const createDeadline = (
  caseId: string,
  body: { title: string; due_date: string; note?: string },
) =>
  fetch(`/api/cases/${caseId}/deadlines`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  }).then(json<Deadline>);

export const setDeadlineStatus = (caseId: string, deadlineId: string, status: DeadlineStatus) =>
  fetch(`/api/cases/${caseId}/deadlines/${deadlineId}`, {
    method: "PATCH",
    headers: jsonHeaders(),
    body: JSON.stringify({ status }),
  }).then(json<{ id: string; status: DeadlineStatus }>);

export const deleteDeadline = (caseId: string, deadlineId: string) =>
  fetch(`/api/cases/${caseId}/deadlines/${deadlineId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });

// --- Admin (JWT role check server-side) ------------------------------------------------

export const getUsers = () =>
  fetch("/api/admin/users", { headers: authHeaders() }).then(json<UserAccount[]>);

export const createUser = (body: {
  username: string;
  display_name: string;
  password: string;
  role: "user" | "admin";
}) =>
  fetch("/api/admin/users", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  }).then(json<UserAccount>);

export const setUserActive = (username: string, isActive: boolean) =>
  fetch(`/api/admin/users/${encodeURIComponent(username)}`, {
    method: "PATCH",
    headers: jsonHeaders(),
    body: JSON.stringify({ is_active: isActive }),
  }).then(json<{ username: string; is_active: boolean }>);

export const getEvalResults = () =>
  fetch("/api/admin/eval/results", { headers: authHeaders() }).then(json<EvalScores | null>);

export const runEval = () =>
  fetch("/api/admin/eval/run", { method: "POST", headers: authHeaders() }).then(
    json<{ status: string }>,
  );

export const getEvalStatus = () =>
  fetch("/api/admin/eval/status", { headers: authHeaders() }).then(json<EvalStatus>);
