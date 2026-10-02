import { useCallback, useEffect } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { ArrowRight, BookOpenText, FileSearch, MessageSquareText } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Notice, Skeleton } from "@/components/ui/Feedback";
import { useEvidence } from "@/features/evidence/EvidenceContext";
import { useConversation } from "@/features/conversations/useConversations";
import { describeError } from "@/lib/utils/errors";
import { ChatComposer } from "./ChatComposer";
import { MessageList } from "./MessageList";
import { useChat } from "./useChat";

/** Suggested research prompts: each one is a real question the connected pipeline handles. */
const PROMPTS: { text: string; tag: string }[] = [
  { text: "What is Article 21 of the Constitution of India?", tag: "provision" },
  { text: "What is the punishment for cheating under Section 420 IPC?", tag: "provision" },
  { text: "Explain the difference between Article 14 and Article 21.", tag: "comparison" },
  { text: "Compare IPC 420 with BNS 318, explain the elements, identify the changes, and cite the relevant statutory evidence.", tag: "multi-aspect" },
];

function Intro({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="thread">
      <section className="intro" aria-labelledby="intro-title">
        <div className="intro__head">
          <span className="intro__kicker">Legal Lens</span>
          <h1 id="intro-title" className="intro__title">Research law with evidence, context, and citations.</h1>
          <p className="intro__lead">Ask a question about Indian law. Legal Lens retrieves the relevant provisions, answers from them, and shows you every source it relied on.</p>
          <div className="intro__steps" aria-label="How it works">
            <span className="intro__step"><MessageSquareText />Ask</span>
            <span className="intro__step"><FileSearch />Retrieve</span>
            <span className="intro__step"><BookOpenText />Verify</span>
          </div>
        </div>
        <div className="prompts">
          <span className="t-section prompts__label">Suggested research</span>
          {PROMPTS.map((p) => (
            <button key={p.text} type="button" className="prompt" onClick={() => onPick(p.text)}>
              <ArrowRight aria-hidden="true" />
              <span>{p.text}</span>
              <span className="prompt__tag">{p.tag}</span>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}

export function ChatView() {
  const { conversationId = null } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const prefill = (location.state as { prefill?: string } | null)?.prefill ?? "";
  const detail = useConversation(conversationId);
  const evidence = useEvidence();

  const onCreated = useCallback((id: string) => navigate(`/app/chat/${id}`, { replace: true }), [navigate]);
  const chat = useChat(conversationId, detail.data, onCreated);

  // The evidence panel follows the latest completed answer.
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

  if (conversationId && detail.isPending && chat.state.messages.length === 0) {
    return (
      <div className="thread"><div className="thread__col"><Skeleton lines={2} width="55%" /><Skeleton lines={6} /></div></div>
    );
  }
  if (conversationId && detail.isError && chat.state.messages.length === 0) {
    const err = describeError(detail.error);
    const missing = err.code === "not_found";
    return (
      <div className="thread"><div className="thread__col">
        <Notice tone={missing ? "warn" : "danger"} title={missing ? "Conversation not found" : err.title}
          action={missing ? <Button variant="secondary" size="sm" onClick={() => navigate("/app")}>New research</Button>
            : err.retryable ? <Button variant="secondary" size="sm" onClick={() => detail.refetch()}>Retry</Button> : undefined}>
          {missing ? "This conversation does not exist or belongs to another account." : err.message}
        </Notice>
      </div></div>
    );
  }

  const empty = chat.state.messages.length === 0;
  return (
    <>
      {empty ? <Intro onPick={(text) => void chat.send(text)} /> : <MessageList state={chat.state} onRetry={(id) => void chat.retry(id)} onStop={chat.stop} />}
      <ChatComposer busy={chat.busy} onSend={(text, o) => void chat.send(text, o)} onStop={chat.stop} initialText={prefill} autoFocus
        placeholder={empty ? "Ask a legal question…" : "Ask a follow-up…"} />
    </>
  );
}
