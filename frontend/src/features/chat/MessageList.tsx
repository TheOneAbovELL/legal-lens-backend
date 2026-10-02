import { useEffect, useLayoutEffect, useRef } from "react";
import { AssistantMessage } from "./AssistantMessage";
import { StatusRow } from "./StatusRow";
import { UserMessage } from "./UserMessage";
import type { ChatState } from "./chatReducer";

interface Props {
  state: ChatState;
  onRetry: (assistantId: string) => void;
  onStop: () => void;
}

/** Renders the conversation; keeps the view pinned to the bottom only while the user is already there. */
export function MessageList({ state, onRetry, onStop }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  };
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (el && pinned.current) el.scrollTop = el.scrollHeight;
  }, [state.messages]);
  useEffect(() => {
    pinned.current = true;
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [state.conversationId]);

  return (
    <div ref={scrollRef} className="chat__scroll" onScroll={onScroll} data-testid="message-list">
      <div className="chat__column">
        {state.messages.map((m, i) =>
          m.role === "user" ? (
            <UserMessage key={m.id} message={m} />
          ) : (
            <AssistantMessage key={m.id} message={m} question={m.query ?? state.messages[i - 1]?.content ?? null}
              streaming={state.streamingId === m.id}
              onRetry={state.streamingId ? undefined : () => onRetry(m.id)}
              onStop={state.streamingId === m.id ? onStop : undefined} />
          ),
        )}
        {state.streamingId && state.phase !== "streaming" ? <StatusRow phase={state.phase} stage={state.stage} /> : null}
      </div>
    </div>
  );
}
