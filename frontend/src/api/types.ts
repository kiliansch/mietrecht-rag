// DTOs mirroring src/api/schemas.py and the SSE event payloads.

export type Role = "mieter" | "vermieter" | "jurist";

export interface AuthUser {
  username: string;
  display_name: string;
  role: "user" | "admin"; // authorisation role (not the legal persona)
  persona: Role;
}

export interface LoginResponse {
  token: string;
  user: AuthUser;
}

export interface UserAccount {
  username: string;
  display_name: string;
  role: "user" | "admin";
  persona: Role;
  is_active: boolean;
  created_at: string;
}

export interface AppConfig {
  roles: { key: string; label: string }[];
  models: { value: string; label: string }[];
  pricing: Record<string, [number, number]>;
  thresholds: Record<string, number>;
  rate_limit: { requests: number; window_secs: number };
  max_upload_bytes: number;
}

export interface Source {
  source: string; // "statutes" | "case_law"
  header: string;
  url: string;
}

export interface SourceDetail {
  collection: string;
  url: string;
  title: string;
  blocks: { heading: string; content: string }[];
}

export interface ChatSummary {
  thread_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

// One reconstructed turn of a saved thread (from the chat-history endpoint).
export interface ChatHistoryMessage {
  role: "user" | "assistant";
  content: string;
  sources: Source[];
}

export interface ToolCall {
  id: string;
  name: string;
  args: Record<string, unknown>;
  result: string | null;
}

// A proposed agent action awaiting the user's confirmation (HITL interrupt).
export interface PendingApproval {
  interrupt_id: string;
  action: string; // "create_deadline" | "save_draft"
  args: Record<string, unknown>;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  toolCalls?: ToolCall[];
  feedback?: 1 | -1 | null;
  pendingApproval?: PendingApproval | null;
}

export interface Profile {
  role: string | null;
  facts: Record<string, string | number | boolean>;
  facts_source: Record<string, string>;
}

// --- Cases ("Mietfall-Akten") ---

export type DocumentKind = "contract" | "letter" | "draft";
export type DeadlineStatus = "open" | "done" | "missed";

export interface CaseSummary {
  id: string;
  title: string;
  status: "open" | "closed";
  thread_id: string;
  created_at: string;
  open_deadlines: number;
  next_due: string | null; // ISO date of the soonest open deadline
  document_count: number;
}

export interface LetterAnalysis {
  summary: string;
}

export interface ContractAnalysis {
  findings: Finding[];
  summary: { wirksam: number; bedenklich: number; unwirksam: number };
  total_clauses: number;
}

export interface CaseDocument {
  id: string;
  case_id: string;
  kind: DocumentKind;
  filename: string | null;
  title: string;
  analysis: LetterAnalysis | ContractAnalysis | null;
  sources: Source[] | null;
  created_at: string;
  content?: string; // only on the single-document endpoint
  extracted_facts?: Record<string, number>; // only on the upload endpoint (contracts)
}

export interface Deadline {
  id: string;
  case_id: string;
  document_id: string | null;
  title: string;
  due_date: string; // ISO date
  note: string;
  status: DeadlineStatus;
  created_by: string;
  created_at: string;
}

export interface CaseDetail extends Omit<CaseSummary, "open_deadlines" | "next_due" | "document_count"> {
  documents: CaseDocument[];
  deadlines: Deadline[];
}

export interface Finding {
  heading: string;
  verdict: "wirksam" | "bedenklich" | "unwirksam";
  reasoning: string;
  sources: Source[];
}

export interface EvalScores {
  agent: Record<string, number>;
  retrieval: Record<string, Record<string, number>>;
}

export interface EvalStatus {
  status: "idle" | "running" | "done" | "error";
  results: EvalScores | null;
  error: string | null;
}
