import type { ChatMessage, Citation } from "./types";

const TOKEN_KEY = "eaik_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {
      const data = await response.json();
      if (typeof data.detail === "string") message = data.detail;
      else if (Array.isArray(data.detail)) message = data.detail[0]?.msg ?? message;
    } catch {
      /* ignore */
    }
    if (response.status === 401) setToken(null);
    throw new ApiError(response.status, message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  upload: <T>(path: string, file: File, title = "") => {
    const form = new FormData();
    form.append("file", file);
    if (title) form.append("title", title);
    return request<T>(path, { method: "POST", body: form });
  },
};

interface StreamHandlers {
  onMeta?: (meta: { conversation_id: number; provider: string; retrieved: number }) => void;
  onCitations?: (citations: Citation[]) => void;
  onToken?: (text: string) => void;
  onDone?: (info: { message_id: number; latency_ms: number; provider: string }) => void;
}

export async function streamChat(
  payload: { question: string; conversation_id: number | null; kb_ids: number[] },
  handlers: StreamHandlers,
): Promise<number> {
  const token = getToken();
  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok || !response.body) {
    let message = "问答请求失败";
    try {
      const data = await response.json();
      if (typeof data.detail === "string") message = data.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(response.status, message);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let conversationId = payload.conversation_id ?? 0;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      const lines = block.split("\n");
      const eventLine = lines.find((line) => line.startsWith("event:"));
      const dataLine = lines.find((line) => line.startsWith("data:"));
      if (!dataLine) continue;
      const event = eventLine?.slice(6).trim() ?? "message";
      const data = JSON.parse(dataLine.slice(5).trim());
      if (event === "meta") {
        conversationId = data.conversation_id;
        handlers.onMeta?.(data);
      } else if (event === "citations") {
        handlers.onCitations?.(data.citations);
      } else if (event === "token") {
        handlers.onToken?.(data.text);
      } else if (event === "done") {
        handlers.onDone?.(data);
      }
    }
  }
  return conversationId;
}

export function toMessage(raw: Record<string, unknown>): ChatMessage {
  return {
    id: raw.id as number,
    role: raw.role as "user" | "assistant",
    content: (raw.content as string) ?? "",
    citations: (raw.citations as Citation[]) ?? [],
    provider: raw.provider as string,
    latency_ms: raw.latency_ms as number,
    created_at: raw.created_at as string,
  };
}

export function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

export function formatAmount(amount: number | null): string {
  if (amount === null || amount === undefined) return "—";
  return `¥ ${amount.toLocaleString("zh-CN")}`;
}

export const STATUS_LABEL: Record<string, string> = {
  uploaded: "待分析",
  analyzing: "分析中",
  pending_review: "待复核",
  needs_changes: "待修改",
  approved: "已通过",
  rejected: "已拒绝",
};

export const SEVERITY_LABEL: Record<string, string> = {
  high: "高风险",
  medium: "中风险",
  low: "低风险",
};

export const RISK_STATUS_LABEL: Record<string, string> = {
  open: "待处理",
  accepted: "已接受风险",
  ignored: "已忽略",
  fixed: "已整改",
};

export const ROLE_LABEL: Record<string, string> = {
  admin: "系统管理员",
  hr: "人事专员",
  finance: "财务专员",
  legal: "法务专员",
  employee: "普通员工",
};
