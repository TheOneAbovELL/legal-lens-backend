import { memo } from "react";
import { Badge, ComplexityBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Card";
import { useToast } from "@/components/ui/Toast";
import { AnswerMarkdown } from "@/features/citations/AnswerMarkdown";
import { useEvidence } from "@/features/citations/EvidenceContext";
import { LegalMappingCard } from "@/features/legal/LegalMappingCard";
import { formatTime, provisionLabel } from "@/lib/utils/format";
import type { ChatMessage } from "./chatReducer";

interface Props {
  message: ChatMessage;
  question: string | null;
  streaming: boolean;
  onRetry?: () => void;
  onStop?: () => void;
}

export const AssistantMessage = memo(function AssistantMessage({ message, question, streaming, onRetry, onStop }: Props) {
  const evidence = useEvidence();
  const { notify } = useToast();
  const isActive = evidence.messageId === message.id;
  const activeId = isActive && evidence.selected ? evidence.selected.citation.citation_id : null;

  const openCitation = (id: string) => {
    const citation = message.citations.find((c) => c.citation_id === id);
    if (!citation) return;
    evidence.show(message.id, message.citations, question);
    evidence.select(message.id, citation, window.matchMedia("(max-width: 1100px)").matches);
  };
  const showSources = () => {
    evidence.show(message.id, message.citations, question);
    if (window.matchMedia("(max-width: 1100px)").matches) evidence.setDrawerOpen(true);
  };
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      notify({ tone: "success", title: "Answer copied" });
    } catch {
      notify({ tone: "danger", title: "Copy failed", message: "Clipboard access was denied." });
    }
  };

  const body = (() => {
    if (message.status === "failed" && message.error) {
      return (
        <Alert tone="danger" title={message.error.title} action={onRetry && message.error.retryable ? <Button size="sm" onClick={onRetry}>Retry</Button> : undefined}>
          {message.error.message}
        </Alert>
      );
    }
    if (message.status === "incomplete") {
      return (
        <>
          {message.content ? <AnswerMarkdown text={message.content} citations={message.citations} /> : null}
          <Alert tone="warning" title="Response incomplete" action={onRetry ? <Button size="sm" onClick={onRetry}>Retry</Button> : undefined}>
            The stream was stopped before the answer finished.
          </Alert>
        </>
      );
    }
    if (message.status === "insufficient_evidence") {
      return (
        <Alert tone="warning" title="Insufficient evidence">
          {message.content || "I could not find sufficient supporting legal sources in the connected corpus to answer this reliably."}
          <div style={{ marginTop: 6, fontSize: 13 }}>Try naming the Act and section, rephrasing, or use Search to explore the corpus.</div>
        </Alert>
      );
    }
    if (message.status === "refused") {
      return <Alert tone="info" title="Outside what Legal Lens can help with">{message.content}</Alert>;
    }
    if (!message.content && streaming) {
      return null;
    }
    return <AnswerMarkdown text={message.content} citations={message.citations} activeId={activeId} onCite={openCitation} streaming={streaming} />;
  })();

  return (
    <article className="msg" aria-label="Legal Lens answer" data-testid="assistant-message" data-status={message.status}>
      {body}
      {message.bnsAlerts.length > 0 ? (
        <div className="stack" style={{ gap: 8 }}>
          {message.bnsAlerts.map((a) => <LegalMappingCard key={`${a.old}-${a.new ?? ""}`} alert={a} />)}
        </div>
      ) : null}
      {!streaming && message.status === "complete" ? (
        message.citations.length > 0 ? (
          <div className="answer__sources">
            <strong>Sources:</strong>
            {message.citations.map((c) => (
              <button key={c.citation_id} type="button" className={`cite${activeId === c.citation_id ? " cite--active" : ""}`}
                onClick={() => openCitation(c.citation_id)} title={`${provisionLabel(c)} — ${c.source}`}>
                {c.citation_id} {provisionLabel(c)}
              </button>
            ))}
            <Button size="sm" variant="ghost" onClick={showSources}>View all</Button>
          </div>
        ) : (
          <div className="answer__sources">The answer did not return source evidence.</div>
        )
      ) : null}
      {message.warnings.length > 0 && !streaming ? (
        <div className="row" style={{ fontSize: 12, color: "var(--warning)" }}>
          {message.warnings.map((w) => <span key={w}>⚠ {w}</span>)}
        </div>
      ) : null}
      <div className="msg__meta">
        <time dateTime={message.createdAt}>{formatTime(message.createdAt)}</time>
        {message.analysis ? <ComplexityBadge complexity={message.analysis.complexity} /> : null}
        {message.analysis?.retrieval_profile ? <Badge title="Retrieval profile">{message.analysis.retrieval_profile}</Badge> : null}
        {message.analysis?.decomposition_needed ? <Badge title="The question was split into sub-queries">decomposed</Badge> : null}
        <span className="msg__actions">
          {streaming && onStop ? <Button size="sm" variant="ghost" onClick={onStop}>Stop</Button> : null}
          {!streaming && message.content ? <Button size="sm" variant="ghost" onClick={copy} aria-label="Copy answer">Copy</Button> : null}
          {!streaming && onRetry && message.status !== "failed" && message.status !== "incomplete" ? <Button size="sm" variant="ghost" onClick={onRetry} aria-label="Ask again">Retry</Button> : null}
        </span>
      </div>
      {message.disclaimer && !streaming && message.status === "complete" ? (
        <p style={{ margin: 0, fontSize: 12, color: "var(--text-faint)" }}>{message.disclaimer}</p>
      ) : null}
    </article>
  );
});
