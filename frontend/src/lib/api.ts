// Fetch helpers for the FastAPI backend. Production is same-origin; local
// demos can set VITE_API_BASE=https://helpdesk.ampixa.com or a k2 URL.

const DEFAULT_API_BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/+$/, "");
const API_BASE_STORAGE_KEY = "speakgov_api_base";

export function getRuntimeApiBase() {
  if (typeof window === "undefined") return DEFAULT_API_BASE;
  return (window.localStorage.getItem(API_BASE_STORAGE_KEY) || DEFAULT_API_BASE).replace(/\/+$/, "");
}

export function setRuntimeApiBase(value: string) {
  const cleaned = value.trim().replace(/\/+$/, "");
  if (typeof window !== "undefined") {
    if (cleaned) window.localStorage.setItem(API_BASE_STORAGE_KEY, cleaned);
    else window.localStorage.removeItem(API_BASE_STORAGE_KEY);
  }
  return cleaned;
}

export function apiPath(path: string) {
  return `${getRuntimeApiBase()}${path}`;
}

export type QuerySource = {
  rank: number;
  source_ref?: string;
  is_tacit: boolean;
  label: string;
  url?: string | null;
  snippet: string;
  confidence?: string | null;
  interviewee_role?: string | null;
};

export type QueryCitation = {
  url: string;
  rank: number;
  snippet: string;
  is_tacit: boolean;
};

export type QueryResponse = {
  answer: string;
  citations: QueryCitation[];
  sources: QuerySource[];
  did_refuse: boolean;
  retrieved_tacit: number;
  retrieved_gov: number;
  latency_ms: { retrieval: number; generation: number; total: number };
  detected_lang: string;
};

export type ChatHistoryTurn = {
  role: "user" | "assistant";
  content: string;
};

export type QueryStreamMeta = {
  sources: QuerySource[];
  retrieved_tacit: number;
  retrieved_gov: number;
  latency_ms: { retrieval: number; generation?: number; total?: number };
  detected_lang: string;
};

export type QueryStreamHandlers = {
  onMeta?: (meta: QueryStreamMeta) => void;
  onToken?: (text: string) => void;
  onFinal?: (response: QueryResponse) => void;
};

const QUERY_BODY_DEFAULTS = {
  top_k_tacit: 3,
  top_k_gov: 3,
  max_new_tokens: 300,
};

export async function postQuery(
  question: string,
  history: ChatHistoryTurn[] = [],
  signal?: AbortSignal,
): Promise<QueryResponse> {
  const r = await fetch(apiPath("/query"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      history,
      ...QUERY_BODY_DEFAULTS,
    }),
    signal,
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(`HTTP ${r.status}: ${t.slice(0, 200)}`);
  }
  return (await r.json()) as QueryResponse;
}

function dispatchSseBlock(
  block: string,
  handlers: QueryStreamHandlers,
  setFinal: (response: QueryResponse) => void,
) {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (!dataLines.length) return;
  const data = JSON.parse(dataLines.join("\n")) as unknown;
  if (event === "meta") handlers.onMeta?.(data as QueryStreamMeta);
  if (event === "token") handlers.onToken?.((data as { text?: string }).text || "");
  if (event === "final") {
    const response = data as QueryResponse;
    setFinal(response);
    handlers.onFinal?.(response);
  }
  if (event === "error") {
    throw new Error((data as { message?: string }).message || "streaming failed");
  }
}

export async function postQueryStream(
  question: string,
  history: ChatHistoryTurn[] = [],
  handlers: QueryStreamHandlers = {},
  signal?: AbortSignal,
): Promise<QueryResponse> {
  const r = await fetch(apiPath("/query/stream"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      history,
      ...QUERY_BODY_DEFAULTS,
    }),
    signal,
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(`HTTP ${r.status}: ${t.slice(0, 200)}`);
  }
  if (!r.body) throw new Error("streaming is not supported by this browser");

  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let final: QueryResponse | null = null;
  const setFinal = (response: QueryResponse) => {
    final = response;
  };

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    let idx = buffer.indexOf("\n\n");
    while (idx >= 0) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      if (block.trim()) dispatchSseBlock(block, handlers, setFinal);
      idx = buffer.indexOf("\n\n");
    }
    if (done) break;
  }
  if (buffer.trim()) dispatchSseBlock(buffer, handlers, setFinal);
  if (!final) throw new Error("stream ended before final answer");
  return final;
}

export type VoiceTranscribeResponse = {
  transcript: string;
  latency_ms: { transcription: number; total: number };
  mime_type: string;
  bytes: number;
  provider: string;
  model_id?: string | null;
};

export type VoiceProvidersResponse = {
  asr_provider: string;
  asr_model_id?: string | null;
  asr_space_url?: string | null;
  tts_provider: string;
  tts_model_repo?: string | null;
  tts_speaker?: string | null;
  tts_space_url?: string | null;
  tts_enabled: boolean;
};

export async function getVoiceProviders(signal?: AbortSignal): Promise<VoiceProvidersResponse> {
  const r = await fetch(apiPath("/voice/providers"), { signal });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(`HTTP ${r.status}: ${t.slice(0, 200)}`);
  }
  return (await r.json()) as VoiceProvidersResponse;
}

export async function transcribeVoice(
  audio: Blob,
  filename = "recording.webm",
  signal?: AbortSignal,
): Promise<VoiceTranscribeResponse> {
  const form = new FormData();
  form.append("audio", audio, filename);
  const r = await fetch(apiPath("/voice/transcribe"), {
    method: "POST",
    body: form,
    signal,
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(`HTTP ${r.status}: ${t.slice(0, 200)}`);
  }
  return (await r.json()) as VoiceTranscribeResponse;
}

export async function synthesizeVoice(
  text: string,
  signal?: AbortSignal,
): Promise<{ audio: Blob; provider: string; model: string; speaker: string; latencyMs: number }> {
  const r = await fetch(apiPath("/voice/synthesize"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
    signal,
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(`HTTP ${r.status}: ${t.slice(0, 200)}`);
  }
  return {
    audio: await r.blob(),
    provider: r.headers.get("X-Voice-Provider") || "",
    model: r.headers.get("X-Voice-Model") || "",
    speaker: r.headers.get("X-Voice-Speaker") || "",
    latencyMs: Number(r.headers.get("X-Voice-Latency-Ms") || 0),
  };
}

export type WhatsAppStatus = {
  status: string;
  connected: boolean;
  connectedJid?: string | null;
  hasQr: boolean;
  qrUpdatedAt?: string | null;
  lastError?: string | null;
  lastDisconnectReason?: number | null;
  autoReply: boolean;
  allowGroups: boolean;
  inboundCount: number;
  outboundCount: number;
  lastInboundAt?: string | null;
  lastOutboundAt?: string | null;
  authDir?: string;
};

export type WhatsAppQr = {
  qr?: string | null;
  qrDataUrl?: string | null;
  updatedAt?: string | null;
  status: string;
  connected: boolean;
};

export async function getWhatsAppStatus(signal?: AbortSignal): Promise<WhatsAppStatus> {
  const r = await fetch(apiPath("/whatsapp/status"), { signal });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(`HTTP ${r.status}: ${t.slice(0, 200)}`);
  }
  return (await r.json()) as WhatsAppStatus;
}

export async function connectWhatsApp(signal?: AbortSignal): Promise<WhatsAppStatus> {
  const r = await fetch(apiPath("/whatsapp/connect"), { method: "POST", signal });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(`HTTP ${r.status}: ${t.slice(0, 200)}`);
  }
  return (await r.json()) as WhatsAppStatus;
}

export async function getWhatsAppQr(signal?: AbortSignal): Promise<WhatsAppQr> {
  const r = await fetch(apiPath("/whatsapp/qr"), { signal });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(`HTTP ${r.status}: ${t.slice(0, 200)}`);
  }
  return (await r.json()) as WhatsAppQr;
}

export async function sendWhatsApp(to: string, text: string, signal?: AbortSignal) {
  const r = await fetch(apiPath("/whatsapp/send"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ to, text }),
    signal,
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(`HTTP ${r.status}: ${t.slice(0, 200)}`);
  }
  return (await r.json()) as { ok: boolean; jid: string; messageId?: string | null };
}

export async function logoutWhatsApp(signal?: AbortSignal): Promise<WhatsAppStatus> {
  const r = await fetch(apiPath("/whatsapp/logout"), { method: "POST", signal });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(`HTTP ${r.status}: ${t.slice(0, 200)}`);
  }
  return (await r.json()) as WhatsAppStatus;
}

export type Questionnaire = {
  title?: string;
  title_ne?: string;
  intro?: string;
  intro_ne?: string;
  questions: Array<{
    id: string;
    question: string;
    question_ne?: string;
  }>;
};

export async function getQuestionnaire(): Promise<Questionnaire> {
  const r = await fetch(apiPath("/interview/questionnaire"));
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return (await r.json()) as Questionnaire;
}

export type SubmissionAudio = {
  question_id: string;
  filename: string;
  bytes?: number;
};

export type SubmissionPhoto = { filename: string; bytes?: number };

export type Submission = {
  id: string;
  name: string;
  office: string;
  submitted_at: string;
  ip?: string;
  user_agent?: string;
  status: "pending" | "approved" | "rejected";
  audio: SubmissionAudio[];
  photos: SubmissionPhoto[];
  approved_at?: string;
  rejected_at?: string;
  transcripts?: Record<string, string>;
};

export async function submitInterview(form: FormData): Promise<{ id: string; status: string; audio_count: number; photo_count: number }> {
  const r = await fetch(apiPath("/interview/submit"), { method: "POST", body: form });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(`HTTP ${r.status}: ${t.slice(0, 300)}`);
  }
  return r.json();
}

// ---- Admin (HTTP Basic Auth) -----------------------------------------------

const ADMIN_CREDS_KEY = "helpdesk.admin.b64";

export function setAdminCreds(user: string, pass: string) {
  localStorage.setItem(ADMIN_CREDS_KEY, btoa(`${user}:${pass}`));
}
export function clearAdminCreds() {
  localStorage.removeItem(ADMIN_CREDS_KEY);
}
export function hasAdminCreds() {
  return !!localStorage.getItem(ADMIN_CREDS_KEY);
}
function adminHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const b64 = localStorage.getItem(ADMIN_CREDS_KEY);
  return b64 ? { ...extra, Authorization: `Basic ${b64}` } : extra;
}

export async function listAdminSubmissions(): Promise<{ submissions: Submission[] }> {
  const r = await fetch(apiPath("/admin/submissions"), { headers: adminHeaders() });
  if (r.status === 401 || r.status === 403) throw new AdminAuthError();
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export async function getAdminSubmission(id: string): Promise<Submission> {
  const r = await fetch(apiPath(`/admin/submission/${encodeURIComponent(id)}`), { headers: adminHeaders() });
  if (r.status === 401 || r.status === 403) throw new AdminAuthError();
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export type ApproveResult = {
  status: "approved";
  transcripts: Record<string, string>;
  claims: number;
  transcribe_errors: Record<string, string>;
};

export async function adminApprove(id: string): Promise<ApproveResult> {
  const r = await fetch(apiPath(`/admin/submission/${encodeURIComponent(id)}/approve`), {
    method: "POST",
    headers: adminHeaders(),
  });
  if (r.status === 401 || r.status === 403) throw new AdminAuthError();
  if (!r.ok) throw new Error(`HTTP ${r.status}: ${(await r.text()).slice(0, 200)}`);
  return r.json();
}

export async function adminReject(id: string): Promise<{ status: "rejected" }> {
  const r = await fetch(apiPath(`/admin/submission/${encodeURIComponent(id)}/reject`), {
    method: "POST",
    headers: adminHeaders(),
  });
  if (r.status === 401 || r.status === 403) throw new AdminAuthError();
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export class AdminAuthError extends Error {
  constructor() {
    super("admin auth required");
    this.name = "AdminAuthError";
  }
}

export function adminAudioUrl(submissionId: string, filename: string): string {
  // Returns the URL with credentials embedded so audio/img tags work without
  // needing CSP-aware fetch wrapping. Falls back to plain URL if no creds.
  return apiPath(`/admin/audio/${encodeURIComponent(submissionId)}/${encodeURIComponent(filename)}`);
}

export function adminPhotoUrl(submissionId: string, filename: string): string {
  return apiPath(`/admin/photo/${encodeURIComponent(submissionId)}/${encodeURIComponent(filename)}`);
}
