export interface User {
  id: number;
  username: string;
  display_name: string;
  department: string;
  role: "admin" | "hr" | "finance" | "legal" | "employee";
}

export interface KB {
  id: number;
  name: string;
  description: string;
  department: string;
  visibility: "public" | "internal" | "restricted";
  document_count: number;
  chunk_count: number;
  my_permission: "read" | "write";
  updated_at: string;
}

export interface Doc {
  id: number;
  kb_id: number;
  kb_name: string;
  title: string;
  filename: string;
  size: number;
  status: "pending" | "ready" | "failed";
  error: string;
  page_count: number;
  char_count: number;
  chunk_count: number;
  created_at: string;
}

export interface Citation {
  index: number;
  chunk_id: number;
  doc_id: number;
  doc_title: string;
  kb_name: string;
  page: number;
  section: string;
  snippet: string;
  start_char: number;
  end_char: number;
  score: number;
}

export interface ChatMessage {
  id?: number;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  provider?: string;
  latency_ms?: number;
  created_at?: string;
}

export interface Conversation {
  id: number;
  title: string;
  updated_at: string;
  message_count: number;
}

export interface ContractListItem {
  id: number;
  title: string;
  counterparty: string;
  amount: number | null;
  status: string;
  risk_score: number;
  risk_level: string;
  risk_counts: { high: number; medium: number; low: number };
  created_at: string;
}

export interface Clause {
  id: number;
  clause_type: string;
  clause_name: string;
  heading: string;
  content: string;
  confidence: number;
  extractor: string;
}

export interface Risk {
  id: number;
  rule_code: string;
  name: string;
  severity: "high" | "medium" | "low";
  message: string;
  evidence: string;
  clause_type: string;
  status: "open" | "accepted" | "ignored" | "fixed";
  note: string;
  handled_at: string | null;
}

export interface ReviewTask {
  id: number;
  status: string;
  decision: string;
  comment: string;
  reviewer_id: number | null;
  created_at: string;
  completed_at: string | null;
}

export interface ContractDetail {
  id: number;
  title: string;
  filename: string;
  contract_no: string;
  counterparty: string;
  amount: number | null;
  status: string;
  risk_score: number;
  risk_level: string;
  summary: string;
  uploaded_by: string;
  created_at: string;
  updated_at: string;
  can_review: boolean;
  clauses: Clause[];
  risks: Risk[];
  tasks: ReviewTask[];
}

export interface Rule {
  id: number;
  code: string;
  name: string;
  category: string;
  severity: string;
  kind: string;
  params: Record<string, unknown>;
  message: string;
  legal_basis: string;
  enabled: boolean;
}

export interface AdminUser extends User {
  is_active: boolean;
  created_at: string;
}

export interface AuditItem {
  id: number;
  actor: string;
  action: string;
  target_type: string;
  target_id: string;
  detail: string;
  created_at: string;
}

export interface SystemStatus {
  llm: string;
  llm_enabled: boolean;
  embedding: string;
  stats: {
    users: number;
    knowledge_bases: number;
    documents: number;
    chunks: number;
    contracts: number;
    contracts_pending: number;
  };
}
