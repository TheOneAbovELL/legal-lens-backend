import { useCallback, useEffect, useReducer, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { chatApi } from "@/lib/api";
import { newRequestId } from "@/lib/api/client";
import { streamEvents } from "@/lib/streaming/sse";
import { describeError } from "@/lib/utils/errors";
import type { ConversationDetail, RetrievalProfile } from "@/types/api";
import { conversationKeys } from "@/features/conversations/useConversations";
import { chatReducer, initialChatState, type ChatState } from "./chatReducer";

export interface SendOptions {
  profile?: RetrievalProfile | null;
}

export interface ChatController {
  state: ChatState;
  send: (query: string, options?: SendOptions) => Promise<void>;
  stop: () => void;
  retry: (assistantId: string) => Promise<void>;
  busy: boolean;
}

/**
 * Drives one conversation: optimistic user message, streamed assistant message, reconciliation on
 * `complete`, cancellation, retry. `initial` (server history) resets the state when it changes.
 */
export function useChat(conversationId: string | null, initial: ConversationDetail | null | undefined, onConversationCreated?: (id: string) => void): ChatController {
  const [state, dispatch] = useReducer(chatReducer, conversationId, initialChatState);
  const abortRef = useRef<AbortController | null>(null);
  const queryClient = useQueryClient();
  const loadedFor = useRef<string | null>(null);

  useEffect(() => {
    if (conversationId === null) {
      if (loadedFor.current !== null) {
        loadedFor.current = null;
        dispatch({ type: "reset", conversationId: null });
      }
      return;
    }
    if (initial && initial.id === conversationId && loadedFor.current !== conversationId) {
      loadedFor.current = conversationId;
      dispatch({ type: "load", conversationId, messages: initial.messages });
    }
  }, [conversationId, initial]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const run = useCallback(async (query: string, assistantId: string, options?: SendOptions) => {
    const controller = new AbortController();
    abortRef.current = controller;
    const body = { query, conversation_id: stateRef.current.conversationId, profile: options?.profile ?? null };
    try {
      let createdId: string | null = null;
      for await (const event of streamEvents(chatApi.streamPath, body, { signal: controller.signal })) {
        dispatch({ type: "event", event, assistantId });
        if (event.type === "start" && event.persisted && event.conversation_id && !stateRef.current.conversationId) {
          createdId = event.conversation_id;
        }
        if (event.type === "complete" || event.type === "error") {
          if (event.type === "complete" && event.persisted) {
            void queryClient.invalidateQueries({ queryKey: conversationKeys.all });
          }
        }
      }
      if (createdId) {
        // The local state is already canonical for the conversation this stream created:
        // do not reload it from the server when the route switches to its id.
        loadedFor.current = createdId;
        onConversationCreated?.(createdId);
      }
    } catch (error) {
      if (controller.signal.aborted) {
        dispatch({ type: "cancelled", assistantId });
      } else {
        dispatch({ type: "failed", assistantId, error: describeError(error) });
      }
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
    }
  }, [onConversationCreated, queryClient]);

  // Keep a ref to the latest state for use inside async flows.
  const stateRef = useRef(state);
  stateRef.current = state;

  const send = useCallback(async (query: string, options?: SendOptions) => {
    const text = query.trim();
    if (!text || stateRef.current.streamingId) return;
    const userId = `local-${newRequestId()}`;
    const assistantId = `local-${newRequestId()}`;
    dispatch({ type: "send", query: text, userId, assistantId, now: new Date().toISOString() });
    await run(text, assistantId, options);
  }, [run]);

  const retry = useCallback(async (assistantId: string) => {
    const message = stateRef.current.messages.find((m) => m.id === assistantId);
    if (!message?.query || stateRef.current.streamingId) return;
    // Replace the failed exchange with a fresh one (no duplicate user bubble).
    const idx = stateRef.current.messages.findIndex((m) => m.id === assistantId);
    const previousUser = idx > 0 ? stateRef.current.messages[idx - 1] : undefined;
    dispatch({ type: "remove", ids: [assistantId, ...(previousUser?.role === "user" ? [previousUser.id] : [])] });
    await send(message.query);
  }, [send]);

  useEffect(() => () => abortRef.current?.abort(), []);

  return { state, send, stop, retry, busy: state.streamingId !== null };
}
