import { useCallback, useEffect } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Alert, Skeleton } from "@/components/ui/Card";
import { EXAMPLE_QUESTIONS } from "@/app/config";
import { useEvidence } from "@/features/citations/EvidenceContext";
import { useConversation } from "@/features/conversations/useConversations";
import { describeError } from "@/lib/utils/errors";
import { ChatComposer } from "./ChatComposer";
import { MessageList } from "./MessageList";
import { useChat } from "./useChat";

export function ChatView() {
  const { conversationId = null } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const prefill = (location.state as { prefill?: string } | null)?.prefill ?? "";
  const detail = useConversation(conversationId);
  const evidence = useEvidence();

  const onCreated = useCallback((id: string) => navigate(`/app/chat/${id}`, { replace: true }), [navigate]);
  const chat = useChat(conversationId, detail.data, onCreated);

  // The evidence panel follows the latest completed assistant message.
  useEffect(() => {
    const last = [...chat.state.messages].reverse().find((m) => m.role === "assistant" && m.status === "complete");
    if (last) {
      const idx = chat.state.messages.findIndex((m) => m.id === last.id);
      evidence.show(last.id, last.citations, last.query ?? chat.state.messages[idx - 1]?.content ?? null);
    } else {
      evidence.clear();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chat.state.messages, chat.state.conversationId]);

  // History skeleton only when nothing is known locally (a stream in progress must never be replaced).
  if (conversationId && detail.isPending && chat.state.messages.length === 0) {
    return (
      <div className="chat"><div className="chat__scroll"><div className="chat__column"><Skeleton lines={3} /><Skeleton lines={5} /></div></div></div>
    );
  }
  if (conversationId && detail.isError) {
    const err = describeError(detail.error);
    return (
      <div className="chat">
        <div className="chat__scroll"><div className="chat__column">
          <Alert tone={err.code === "not_found" ? "warning" : "danger"} title={err.code === "not_found" ? "Conversation not found" : err.title}
            action={err.retryable ? <Button size="sm" onClick={() => detail.refetch()}>Retry</Button> : <Button size="sm" onClick={() => navigate("/app")}>New chat</Button>}>
            {err.code === "not_found" ? "This conversation does not exist or belongs to another account." : err.message}
          </Alert>
        </div></div>
      </div>
    );
  }

  const empty = chat.state.messages.length === 0;
  return (
    <div className="chat">
      {empty ? (
        <div className="chat__scroll">
          <div className="empty">
            <h1>Ask Legal Lens a question about Indian law.</h1>
            <p>Answers are grounded in the connected legal corpus and every claim is cited so you can inspect the source.</p>
            <div className="empty__examples">
              {EXAMPLE_QUESTIONS.map((q) => (
                <Button key={q} size="sm" onClick={() => chat.send(q)}>{q}</Button>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <MessageList state={chat.state} onRetry={(id) => void chat.retry(id)} onStop={chat.stop} />
      )}
      <ChatComposer busy={chat.busy} onSend={(text, o) => void chat.send(text, o)} onStop={chat.stop} initialText={prefill} autoFocus />
    </div>
  );
}
