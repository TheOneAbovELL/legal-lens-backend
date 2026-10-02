/** Typed API modules. Components never call fetch directly; they use these (via hooks). */
import { API_PREFIX, request } from "./client";
import type {
  ChatRequest,
  ChatResponse,
  ConfigSummary,
  ConversationDetail,
  ConversationList,
  ConversationOut,
  EmbeddingDiagnostics,
  HealthResponse,
  LLMDiagnostics,
  LoginRequest,
  MessageOut,
  QdrantDiagnostics,
  ReadinessResponse,
  RootResponse,
  RouteDiagnostics,
  SearchRequest,
  SearchResponse,
  SignupRequest,
  TokenResponse,
  UserOut,
  BnsAlert,
} from "@/types/api";

export const systemApi = {
  root: () => request<RootResponse>("/"),
  health: (signal?: AbortSignal) => request<HealthResponse>("/health", { signal, timeoutMs: 5000 }),
  ready: (signal?: AbortSignal) => request<ReadinessResponse>("/ready", { signal, timeoutMs: 8000 }),
};

export const authApi = {
  signup: (body: SignupRequest) => request<TokenResponse>(`${API_PREFIX}/auth/signup`, { body, anonymous: true }),
  login: (body: LoginRequest) => request<TokenResponse>(`${API_PREFIX}/auth/login`, { body, anonymous: true }),
  me: (signal?: AbortSignal) => request<UserOut>(`${API_PREFIX}/auth/me`, { signal }),
};

export const chatApi = {
  ask: (body: ChatRequest, signal?: AbortSignal) =>
    request<ChatResponse>(`${API_PREFIX}/chat`, { body: { ...body, stream: false }, signal, timeoutMs: 120_000 }),
  streamPath: `${API_PREFIX}/chat/stream`,
};

export const searchApi = {
  search: (body: SearchRequest, signal?: AbortSignal) =>
    request<SearchResponse>(`${API_PREFIX}/search`, { body, signal, timeoutMs: 60_000 }),
};

export const conversationApi = {
  list: (signal?: AbortSignal) => request<ConversationList>(`${API_PREFIX}/conversations`, { signal }),
  create: (title?: string | null) => request<ConversationOut>(`${API_PREFIX}/conversations`, { body: { title: title ?? null } }),
  get: (id: string, signal?: AbortSignal) =>
    request<ConversationDetail>(`${API_PREFIX}/conversations/${encodeURIComponent(id)}`, { signal }),
  messages: (id: string, signal?: AbortSignal) =>
    request<MessageOut[]>(`${API_PREFIX}/conversations/${encodeURIComponent(id)}/messages`, { signal }),
  rename: (id: string, title: string) =>
    request<ConversationOut>(`${API_PREFIX}/conversations/${encodeURIComponent(id)}`, { method: "PATCH", body: { title } }),
  remove: (id: string) => request<void>(`${API_PREFIX}/conversations/${encodeURIComponent(id)}`, { method: "DELETE" }),
};

export const legalApi = {
  map: (code: string, section: string, signal?: AbortSignal) =>
    request<BnsAlert>(`${API_PREFIX}/statute/map?code=${encodeURIComponent(code)}&section=${encodeURIComponent(section)}`, { signal }),
};

export const diagnosticsApi = {
  config: (signal?: AbortSignal) => request<ConfigSummary>(`${API_PREFIX}/diagnostics/config`, { signal }),
  qdrant: (signal?: AbortSignal) => request<QdrantDiagnostics>(`${API_PREFIX}/diagnostics/qdrant`, { signal }),
  embedding: (signal?: AbortSignal) => request<EmbeddingDiagnostics>(`${API_PREFIX}/diagnostics/embedding`, { signal }),
  llm: (signal?: AbortSignal) =>
    request<LLMDiagnostics>(`${API_PREFIX}/diagnostics/llm`, { body: { prompt: "Respond with OK.", max_tokens: 16 }, signal, timeoutMs: 60_000 }),
  route: (query: string, signal?: AbortSignal) =>
    request<RouteDiagnostics>(`${API_PREFIX}/diagnostics/route`, { body: { query, use_llm_decomposition: false }, signal }),
};

/** Every path the client can call, for the contract check against OpenAPI. */
export const CLIENT_PATHS: { method: string; path: string }[] = [
  { method: "get", path: "/" },
  { method: "get", path: "/health" },
  { method: "get", path: "/ready" },
  { method: "post", path: `${API_PREFIX}/auth/signup` },
  { method: "post", path: `${API_PREFIX}/auth/login` },
  { method: "get", path: `${API_PREFIX}/auth/me` },
  { method: "post", path: `${API_PREFIX}/chat` },
  { method: "post", path: `${API_PREFIX}/chat/stream` },
  { method: "post", path: `${API_PREFIX}/search` },
  { method: "get", path: `${API_PREFIX}/conversations` },
  { method: "post", path: `${API_PREFIX}/conversations` },
  { method: "get", path: `${API_PREFIX}/conversations/{conversation_id}` },
  { method: "get", path: `${API_PREFIX}/conversations/{conversation_id}/messages` },
  { method: "patch", path: `${API_PREFIX}/conversations/{conversation_id}` },
  { method: "delete", path: `${API_PREFIX}/conversations/{conversation_id}` },
  { method: "get", path: `${API_PREFIX}/statute/map` },
  { method: "get", path: `${API_PREFIX}/diagnostics/config` },
  { method: "get", path: `${API_PREFIX}/diagnostics/qdrant` },
  { method: "get", path: `${API_PREFIX}/diagnostics/embedding` },
  { method: "post", path: `${API_PREFIX}/diagnostics/llm` },
  { method: "post", path: `${API_PREFIX}/diagnostics/route` },
];
