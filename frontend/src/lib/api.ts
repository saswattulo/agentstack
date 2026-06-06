// Thin typed client for the AgentStack API. Week 4 expands this with the chat
// streaming hook, eval dashboard queries, and a real auth provider.

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const FALLBACK_KEY = process.env.NEXT_PUBLIC_API_KEY ?? "";

let accessToken: string | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
  if (typeof window !== "undefined") {
    if (token) localStorage.setItem("agentstack.token", token);
    else localStorage.removeItem("agentstack.token");
  }
}

export function getAccessToken(): string | null {
  if (accessToken) return accessToken;
  if (typeof window !== "undefined") {
    accessToken = localStorage.getItem("agentstack.token");
  }
  return accessToken;
}

function authHeaders(): Record<string, string> {
  const token = getAccessToken();
  if (token) return { Authorization: `Bearer ${token}` };
  if (FALLBACK_KEY) return { "X-API-Key": FALLBACK_KEY };
  return {};
}

export const API_BASE = BASE;

export function bearerHeaders(): Record<string, string> {
  return authHeaders();
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  // 204 No Content
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export interface User {
  id: string;
  email: string;
  name: string | null;
  is_active: boolean;
  is_admin: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface Collection {
  id: string;
  owner_id: string;
  name: string;
  description: string | null;
  embedding_model: string;
  embedding_dim: number;
  chunking_strategy: string;
  chunk_size: number;
  chunk_overlap: number;
  created_at: string;
  updated_at: string;
}

export interface Conversation {
  id: string;
  user_id: string;
  collection_id: string | null;
  title: string;
  summary: string | null;
  created_at: string;
  updated_at: string;
}

export async function register(email: string, password: string, name?: string) {
  const res = await request<TokenResponse>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password, name }),
  });
  setAccessToken(res.access_token);
  return res;
}

export async function login(email: string, password: string) {
  const res = await request<TokenResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  setAccessToken(res.access_token);
  return res;
}

export async function me() {
  return request<User>("/api/v1/auth/me");
}

export async function listCollections() {
  return request<{ items: Collection[]; total: number }>("/api/v1/collections");
}

export async function createCollection(name: string, description?: string) {
  return request<Collection>("/api/v1/collections", {
    method: "POST",
    body: JSON.stringify({ name, description }),
  });
}

export async function deleteCollection(id: string) {
  return request<void>(`/api/v1/collections/${id}`, { method: "DELETE" });
}

export async function listConversations() {
  return request<{ items: Conversation[]; total: number }>("/api/v1/conversations");
}

export async function createConversation(title: string, collection_id?: string) {
  return request<Conversation>("/api/v1/conversations", {
    method: "POST",
    body: JSON.stringify({ title, collection_id }),
  });
}

// ---- conversations detail / mutate ----

export interface Citation {
  index: number;
  chunk_id: string;
  document_id: string | null;
  score: number;
  preview: string;
}

export interface ConversationMessage {
  query_id: string;
  question: string;
  answer: string | null;
  citations: Citation[];
  created_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: ConversationMessage[];
}

export async function getConversation(id: string) {
  return request<ConversationDetail>(`/api/v1/conversations/${id}`);
}

export async function updateConversation(id: string, title: string) {
  return request<Conversation>(`/api/v1/conversations/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
}

export async function deleteConversation(id: string) {
  return request<void>(`/api/v1/conversations/${id}`, { method: "DELETE" });
}

// ---- documents ----

export type DocumentStatus =
  | "pending"
  | "parsing"
  | "chunking"
  | "embedding"
  | "indexing"
  | "completed"
  | "failed";

export interface DocumentRead {
  id: string;
  collection_id: string;
  source_type: string;
  source_uri: string;
  filename: string | null;
  mime_type: string | null;
  size_bytes: number | null;
  status: DocumentStatus;
  progress: number;
  error_message: string | null;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export async function listDocuments(collectionId: string) {
  return request<{ items: DocumentRead[]; total: number }>(
    `/api/v1/collections/${collectionId}/documents`,
  );
}

export async function getDocument(id: string) {
  return request<DocumentRead>(`/api/v1/documents/${id}`);
}

export async function deleteDocument(id: string) {
  return request<void>(`/api/v1/documents/${id}`, { method: "DELETE" });
}

export async function ingestFile(collectionId: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/api/v1/collections/${collectionId}/ingest`, {
    method: "POST",
    headers: { ...authHeaders() }, // no JSON content-type; browser sets multipart boundary
    body: form,
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return (await res.json()) as DocumentRead;
}

// ---- eval ----

export interface EvalResult {
  query_id: string;
  status: "pending" | "ready";
  faithfulness?: number | null;
  answer_relevancy?: number | null;
  context_precision?: number | null;
  context_recall?: number | null;
  citation_accuracy?: number | null;
  extra?: Record<string, unknown>;
}

// Returns {status: "pending"} while the async eval is still running (200, not
// 404 — so the browser console stays clean during polling).
export async function getEvalResult(queryId: string): Promise<EvalResult> {
  return request<EvalResult>(`/api/v1/eval/results/${queryId}`);
}

// ---- api keys ----

export interface ApiKey {
  id: string;
  name: string;
  key_prefix: string;
  is_active: boolean;
  rate_limit_per_minute: number;
  rate_limit_per_day: number;
  last_used_at: string | null;
  created_at: string;
}

export interface ApiKeyCreated extends ApiKey {
  raw_key: string;
}

export async function listApiKeys() {
  return request<ApiKey[]>("/api/v1/auth/api-keys");
}

export async function createApiKey(name: string) {
  return request<ApiKeyCreated>("/api/v1/auth/api-keys", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function revokeApiKey(id: string) {
  return request<void>(`/api/v1/auth/api-keys/${id}`, { method: "DELETE" });
}

export async function health() {
  return request<{ status: string; version: string }>("/health");
}
