/**
 * Frontend view of the backend contract (app/schemas/*). Kept in one place and checked against the
 * exported OpenAPI document by `npm run contract` (scripts/check-contract.mjs) so the two cannot drift
 * silently. Only fields the UI reads are typed; unknown extra fields are ignored at runtime.
 */

export type Complexity = "SIMPLE" | "MODERATE" | "COMPLEX";
export type RetrievalProfile = "FAST" | "BALANCED" | "DEEP";
export type UserRole = "citizen" | "advocate" | "researcher";
export type ChatStatus = "complete" | "refused" | "insufficient_evidence" | "small_talk";
export type MessageStatus = ChatStatus | "failed" | "incomplete" | "streaming";

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    request_id?: string | null;
    details?: unknown;
  };
}

// ---- health
export interface RootResponse {
  status: "ok";
  service: string;
  version: string;
  docs?: string | null;
}
export interface HealthResponse {
  status: "healthy";
}
export interface ComponentStatus {
  name: string;
  status: string;
  required: boolean;
  detail: Record<string, string | number | boolean | null>;
  error?: string | null;
}
export interface ReadinessResponse {
  status: "ready" | "not_ready";
  checks: Record<string, string>;
  failed: string[];
  components: ComponentStatus[];
}

// ---- auth
export interface SignupRequest {
  username: string;
  email?: string | null;
  password: string;
  role: UserRole;
}
export interface LoginRequest {
  username: string;
  password: string;
}
export interface TokenResponse {
  message: string;
  user: string;
  role: string;
  access_token: string;
  token_type: string;
  expires_in: number;
}
export interface UserOut {
  id: string;
  username: string;
  email: string | null;
  role: string;
  created_at: string;
}

// ---- shared
export interface Citation {
  citation_id: string;
  document_id: string;
  document_version?: string | null;
  title: string;
  act?: string | null;
  section?: string | null;
  section_heading?: string | null;
  subsection?: string | null;
  paragraph?: number | null;
  page?: number | null;
  case_name?: string | null;
  /** Reporter citation, e.g. "(2019) 3 SCC 39" (judgments). */
  case_citation?: string | null;
  court?: string | null;
  /** majority | concurring | dissenting | ... — a concurrence or dissent is not the holding. */
  opinion_type?: string | null;
  opinion_author?: string | null;
  /** Formal pin citation supplied by the data layer. */
  cite_as?: string | null;
  source: string;
  chunk_id?: string | null;
  retrieval_sources: string[];
  score?: number | null;
  excerpt: string;
}
export interface BnsAlert {
  old: string;
  new: string | null;
  effective: string | null;
  mapping_type: "exact" | "approximate" | "ambiguous" | "no_mapping" | "unknown" | string;
  subject?: string | null;
  notes?: string | null;
  verification_status: string;
  provenance: string;
}
export interface SearchFilters {
  document_ids?: string[];
  document_types?: string[];
  acts?: string[];
  sections?: string[];
  jurisdiction?: string;
  court?: string[];
  date_from?: string;
  date_to?: string;
}

// ---- chat
export interface ChatRequest {
  query: string;
  conversation_id?: string | null;
  user_role?: UserRole | null;
  profile?: RetrievalProfile | null;
  filters?: SearchFilters | null;
  stream?: boolean;
}
export interface QueryAnalysis {
  intent: string | null;
  complexity: Complexity | null;
  confidence: number | null;
  route: string | null;
  retrieval_profile: RetrievalProfile | null;
  safety_decision: string | null;
  jurisdiction: string;
  outside_jurisdiction: boolean;
  decomposition_needed: boolean;
  comparison_required: boolean;
  provisions: string[];
  follow_up: boolean;
}
export interface SubQuery {
  subquery_id: string;
  query: string;
  purpose: string;
}
export interface PipelineMetadata {
  request_id: string;
  route?: string | null;
  retrieval_profile?: string | null;
  subqueries?: SubQuery[];
  retrieval_sources?: Record<string, number>;
  candidates?: number;
  reranker?: string | null;
  evidence_selected?: number;
  context_tokens?: number;
  provider?: string | null;
  model?: string | null;
  llm_attempts?: number | null;
  latency_ms?: number;
  timings_ms?: Record<string, number>;
  errors?: string[];
  follow_up?: boolean;
  output_validation?: { valid: boolean; warnings: string[]; invalid_citation_ids: string[] } | null;
  complexity?: { complexity: Complexity; confidence: number; reasons: string[] } | null;
}
export interface StageDiagnostics {
  executed: boolean;
  count: number;
  latency_ms?: number | null;
  method?: string | null;
}
export interface SourceDiagnostics {
  executed: boolean;
  hits: number;
  latency_ms?: number | null;
  error?: string | null;
}
export interface RetrievalDiagnostics {
  complexity: string | null;
  retrieval_profile: string | null;
  route: string | null;
  retrieval_mode: string;
  subqueries: SubQuery[];
  sources: Record<string, SourceDiagnostics>;
  fusion: StageDiagnostics;
  reranking: StageDiagnostics;
  context: { executed: boolean; selected_chunks: number; groups: number; context_tokens: number };
  provision_mapping: StageDiagnostics;
  generation: StageDiagnostics;
  latency_ms: Record<string, number>;
}
export interface ChatResponse {
  answer: string | null;
  source: string;
  request_id: string;
  conversation_id: string | null;
  message_id: string | null;
  persisted: boolean;
  status: ChatStatus;
  analysis: QueryAnalysis;
  refused: boolean;
  citations: Citation[];
  bns_alerts: BnsAlert[];
  warnings: string[];
  disclaimer: string | null;
  metadata: PipelineMetadata;
  diagnostics?: RetrievalDiagnostics | null;
}

// ---- stream events (one JSON object per `data:` line)
export type StreamEvent =
  | { type: "start"; request_id: string; conversation_id: string | null; persisted: boolean; user_message_id: string | null }
  | { type: "intent"; intent: string | null; confidence: number | null; entities: string[]; follow_up: boolean }
  | { type: "safety"; decision: string; categories: string[] }
  | { type: "complexity"; complexity: Complexity; confidence: number; reasons: string[]; profile: string; route: string }
  | ({ type: "analysis" } & QueryAnalysis)
  | { type: "plan"; method: string | null; subqueries: { id: string; query: string; purpose: string }[] }
  | { type: "retrieval"; candidates: number; sources: Record<string, number> }
  | { type: "reranking"; reranker: string | null; count: number }
  | { type: "evidence"; count: number; context_tokens: number; citations: Citation[] }
  | { type: "bns_alert"; mappings: Record<string, unknown>[] }
  | { type: "status"; message: string }
  | { type: "token"; content: string; attempt?: number }
  | ({ type: "citation" } & Citation)
  | { type: "validation"; valid: boolean; warnings: string[]; invalid_citation_ids: string[] }
  | ({ type: "complete"; message_id: string | null } & ChatResponse)
  | { type: "error"; code: string; message: string; request_id?: string };

// ---- search
export interface SearchRequest {
  query: string;
  top_k?: number;
  filters?: SearchFilters | null;
  profile?: RetrievalProfile | null;
  generate_answer?: boolean;
}
export interface SearchResult {
  document_id: string;
  chunk_id: string;
  title: string;
  case_name?: string | null;
  snippet: string;
  content: string;
  score: number;
  rerank_score?: number | null;
  relevance_score: number;
  retrieval_sources: string[];
  citation: Citation;
  metadata: Record<string, unknown> & { act?: string | null; section?: string | null; document_type?: string; source?: string };
  bns_alert?: BnsAlert | null;
}
export interface RetrievalMetadata {
  strategy: string | null;
  complexity: string | null;
  route: string | null;
  reranker: string | null;
  subqueries: number;
  sources: Record<string, number>;
  candidates: number;
  latency_ms: number;
}
export interface SearchResponse {
  query: string;
  request_id: string;
  results: SearchResult[];
  total: number;
  processing_time_ms: number;
  answer: string | null;
  bns_alerts: BnsAlert[];
  warnings: string[];
  retrieval_metadata: RetrievalMetadata;
  diagnostics?: RetrievalDiagnostics | null;
}

// ---- conversations
export interface EvidenceOut {
  citation_id: string;
  document_id: string;
  chunk_id: string | null;
  source: string;
  title: string;
  act: string | null;
  section: string | null;
  page: number | null;
  excerpt: string;
  score: number | null;
}
export interface MessageOut {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  status: MessageStatus | string;
  request_id: string | null;
  complexity: string | null;
  intent: string | null;
  created_at: string;
  citations: EvidenceOut[];
}
export interface ConversationOut {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
}
export interface ConversationDetail extends ConversationOut {
  messages: MessageOut[];
}
export interface ConversationList {
  conversations: ConversationOut[];
  total: number;
}

// ---- diagnostics (development only)
export interface ConfigSummary {
  environment: string;
  version: string;
  diagnostics_enabled: boolean;
  auth_required: boolean;
  registration_enabled: boolean;
  rate_limit: string;
  vector_store: string;
  [key: string]: string | number | boolean | null | string[] | undefined;
}
export interface QdrantDiagnostics {
  reachable: boolean;
  mode: string;
  target: string;
  collection: string;
  collection_exists: boolean;
  points?: number | null;
  vector_dimension?: number | null;
  expected_dimension: number;
  distance?: string | null;
  sparse_enabled: boolean;
  indexed_chunk_profiles?: string[] | null;
  test_query_ok?: boolean | null;
  latency_ms: number;
  error?: string | null;
}
export interface EmbeddingDiagnostics {
  ok: boolean;
  model: string;
  loaded: boolean;
  expected_dimension: number;
  dimension?: number | null;
  normalized?: boolean | null;
  latency_ms: number;
  error?: string | null;
}
export interface LLMDiagnostics {
  ok: boolean;
  configured_providers: string[];
  provider?: string | null;
  model?: string | null;
  response_preview?: string | null;
  latency_ms: number;
  error?: string | null;
}
export interface RouteDiagnostics {
  query: string;
  normalized_query: string;
  entities: string[];
  intent: { intent: string; confidence: number };
  safety: { decision: string; categories: string[] };
  would_refuse: boolean;
  complexity?: { complexity: Complexity; confidence: number; reasons: string[] } | null;
  retrieval_profile?: string | null;
  route?: string | null;
  subqueries: SubQuery[];
}
