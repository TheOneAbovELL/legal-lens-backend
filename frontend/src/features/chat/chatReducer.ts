/**
 * Pure chat state machine. Stream events from the backend drive it; the UI only renders the state.
 * No fetch, no DOM — fully unit-testable.
 */
import type { BnsAlert, Citation, EvidenceOut, MessageOut, MessageStatus, PipelineMetadata, QueryAnalysis, RetrievalDiagnostics, StreamEvent } from "@/types/api";

export type Phase = "idle" | "analyzing" | "retrieving" | "reviewing" | "generating" | "streaming";

export interface UiError {
  title: string;
  message: string;
  retryable: boolean;
  code: string;
}

export interface ChatMessage {
  id: string;
  serverId: string | null;
  role: "user" | "assistant";
  content: string;
  status: MessageStatus;
  createdAt: string;
  citations: Citation[];
  bnsAlerts: BnsAlert[];
  analysis: QueryAnalysis | null;
  warnings: string[];
  disclaimer: string | null;
  requestId: string | null;
  error: UiError | null;
  diagnostics: RetrievalDiagnostics | null;
  metadata: PipelineMetadata | null;
  /** The question this assistant message answers (for retry). */
  query: string | null;
}

/** One research aspect (backend sub-query) and whether its retrieval has completed. */
export interface Aspect {
  id: string;
  label: string;
  done: boolean;
}

export interface StageInfo {
  complexity?: string;
  profile?: string;
  route?: string;
  candidates?: number;
  evidence?: number;
  subqueries?: number;
  aspects?: Aspect[];
}

export interface ChatState {
  conversationId: string | null;
  persisted: boolean;
  messages: ChatMessage[];
  phase: Phase;
  streamingId: string | null;
  stage: StageInfo;
}

export type ChatAction =
  | { type: "reset"; conversationId: string | null }
  | { type: "load"; conversationId: string; messages: MessageOut[] }
  | { type: "send"; query: string; userId: string; assistantId: string; now: string }
  | { type: "event"; event: StreamEvent; assistantId: string }
  | { type: "failed"; assistantId: string; error: UiError; partial?: string }
  | { type: "cancelled"; assistantId: string }
  | { type: "remove"; ids: string[] };

export const initialChatState = (conversationId: string | null = null): ChatState => ({
  conversationId,
  persisted: false,
  messages: [],
  phase: "idle",
  streamingId: null,
  stage: {},
});

export function evidenceToCitation(e: EvidenceOut): Citation {
  return {
    citation_id: e.citation_id, document_id: e.document_id, chunk_id: e.chunk_id, source: e.source, title: e.title,
    act: e.act, section: e.section, page: e.page, excerpt: e.excerpt, score: e.score, retrieval_sources: [],
  };
}

export function fromServerMessage(m: MessageOut): ChatMessage {
  return {
    id: m.id, serverId: m.id, role: m.role, content: m.content, status: m.status as MessageStatus, createdAt: m.created_at,
    citations: m.citations.map(evidenceToCitation), bnsAlerts: [], analysis: null, warnings: [], disclaimer: null,
    requestId: m.request_id, error: null, diagnostics: null, metadata: null, query: null,
  };
}

function blank(id: string, role: "user" | "assistant", content: string, now: string, query: string | null): ChatMessage {
  return {
    id, serverId: null, role, content, status: role === "user" ? "complete" : "streaming", createdAt: now,
    citations: [], bnsAlerts: [], analysis: null, warnings: [], disclaimer: null, requestId: null, error: null,
    diagnostics: null, metadata: null, query,
  };
}

function patch(state: ChatState, id: string, update: Partial<ChatMessage>): ChatState {
  return { ...state, messages: state.messages.map((m) => (m.id === id ? { ...m, ...update } : m)) };
}

/** Short, safe label for a sub-query: its purpose when the planner gave one, else the query text. */
function aspectLabel(sq: { query: string; purpose: string }): string {
  const purpose = sq.purpose?.trim();
  if (purpose && purpose.length <= 60 && !/^(lookup|retrieve|search)$/i.test(purpose)) return purpose;
  return sq.query.length > 70 ? `${sq.query.slice(0, 67)}…` : sq.query;
}

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "reset":
      return initialChatState(action.conversationId);
    case "load":
      return { ...initialChatState(action.conversationId), persisted: true, messages: action.messages.map(fromServerMessage) };
    case "send": {
      const user = blank(action.userId, "user", action.query, action.now, null);
      const assistant = blank(action.assistantId, "assistant", "", action.now, action.query);
      return { ...state, messages: [...state.messages, user, assistant], phase: "analyzing", streamingId: action.assistantId, stage: {} };
    }
    case "failed":
      return {
        ...patch(state, action.assistantId, { status: "failed", error: action.error, content: action.partial ?? "" }),
        phase: "idle", streamingId: null,
      };
    case "cancelled": {
      const current = state.messages.find((m) => m.id === action.assistantId);
      return {
        ...patch(state, action.assistantId, { status: "incomplete", content: current?.content ?? "" }),
        phase: "idle", streamingId: null,
      };
    }
    case "remove":
      return { ...state, messages: state.messages.filter((m) => !action.ids.includes(m.id)) };
    case "event":
      return applyEvent(state, action.event, action.assistantId);
    default:
      return state;
  }
}

function applyEvent(state: ChatState, event: StreamEvent, id: string): ChatState {
  switch (event.type) {
    case "start": {
      const next = { ...state, conversationId: event.conversation_id ?? state.conversationId, persisted: event.persisted };
      const userIdx = [...next.messages].reverse().findIndex((m) => m.role === "user");
      if (event.user_message_id && userIdx >= 0) {
        const realIdx = next.messages.length - 1 - userIdx;
        next.messages = next.messages.map((m, i) => (i === realIdx ? { ...m, serverId: event.user_message_id, requestId: event.request_id } : m));
      }
      return patch(next, id, { requestId: event.request_id });
    }
    case "intent":
    case "safety":
      return { ...state, phase: "analyzing" };
    case "complexity":
      return { ...state, stage: { ...state.stage, complexity: event.complexity, profile: event.profile, route: event.route } };
    case "analysis": {
      const { type: _type, ...analysis } = event;
      void _type;
      return patch({ ...state, phase: "retrieving" }, id, { analysis });
    }
    case "plan": {
      const aspects = event.subqueries.length > 1 ? event.subqueries.map((s) => ({ id: s.id, label: aspectLabel(s), done: false })) : undefined;
      return { ...state, phase: "retrieving", stage: { ...state.stage, subqueries: event.subqueries.length, aspects } };
    }
    case "retrieval":
      return {
        ...state, phase: "reviewing",
        stage: { ...state.stage, candidates: event.candidates, aspects: state.stage.aspects?.map((a) => ({ ...a, done: true })) },
      };
    case "reranking":
      return { ...state, phase: "reviewing" };
    case "evidence":
      return { ...state, phase: "generating", stage: { ...state.stage, evidence: event.count } };
    case "bns_alert":
    case "status":
      return state;
    case "token": {
      const current = state.messages.find((m) => m.id === id);
      // A regeneration (new attempt number) restarts the draft instead of appending to the rejected one.
      const attempt = event.attempt ?? 0;
      const lastAttempt = current?.metadata?.llm_attempts ?? 0;
      const content = attempt !== lastAttempt ? event.content : (current?.content ?? "") + event.content;
      return patch({ ...state, phase: "streaming" }, id, {
        content, metadata: { ...(current?.metadata ?? { request_id: current?.requestId ?? "" }), llm_attempts: attempt },
      });
    }
    case "citation": {
      const current = state.messages.find((m) => m.id === id);
      const { type: _type, ...citation } = event;
      void _type;
      const list = current?.citations ?? [];
      if (list.some((c) => c.citation_id === citation.citation_id)) return state;
      return patch(state, id, { citations: [...list, citation] });
    }
    case "validation":
      return event.valid ? state : patch(state, id, { warnings: event.warnings });
    case "complete": {
      // Reconcile: the complete payload is canonical (answer text, citations, ids). Never duplicate.
      // Pipeline warnings are operational detail (planner fallbacks, optional sources); only answer
      // validation warnings (from the `validation` event) are user-facing and are kept.
      const { type: _type, ...result } = event;
      void _type;
      const current = state.messages.find((m) => m.id === id);
      return {
        ...patch(state, id, {
          serverId: result.message_id ?? null,
          content: result.answer ?? "",
          status: result.status,
          citations: result.citations ?? [],
          bnsAlerts: result.bns_alerts ?? [],
          analysis: result.analysis ?? null,
          warnings: current?.warnings ?? [],
          disclaimer: result.disclaimer ?? null,
          requestId: result.request_id,
          diagnostics: result.diagnostics ?? null,
          metadata: result.metadata ?? null,
          error: null,
        }),
        conversationId: result.conversation_id ?? state.conversationId,
        persisted: result.persisted,
        phase: "idle",
        streamingId: null,
      };
    }
    case "error": {
      const current = state.messages.find((m) => m.id === id);
      return {
        ...patch(state, id, {
          status: "failed",
          error: { title: "Legal Lens couldn't complete this research request.", message: event.message, retryable: true, code: event.code },
          content: current?.content ?? "",
        }),
        phase: "idle", streamingId: null,
      };
    }
    default:
      return state;
  }
}

export function phaseLabel(phase: Phase, stage: StageInfo): string | null {
  switch (phase) {
    case "analyzing":
      return "Analyzing question";
    case "retrieving":
      return stage.subqueries && stage.subqueries > 1 ? `Researching ${stage.subqueries} legal aspects` : "Searching legal sources";
    case "reviewing":
      return stage.candidates !== undefined ? `Reviewing ${stage.candidates} passages` : "Reviewing evidence";
    case "generating":
      return stage.evidence !== undefined ? `Preparing answer from ${stage.evidence} sources` : "Preparing answer";
    default:
      return null;
  }
}

export const PHASES: { key: Phase; label: string }[] = [
  { key: "analyzing", label: "Analyze" },
  { key: "retrieving", label: "Search" },
  { key: "reviewing", label: "Review" },
  { key: "generating", label: "Answer" },
];
