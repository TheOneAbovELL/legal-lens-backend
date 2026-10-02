import { memo } from "react";
import { BookOpenText, Copy, RotateCcw, ShieldCheck, Square } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { CitationChip } from "@/components/ui/Chip";
import { Notice } from "@/components/ui/Feedback";
import { useToast } from "@/components/ui/Toast";
import { AnswerMarkdown } from "@/features/evidence/AnswerMarkdown";
import { useEvidence } from "@/features/evidence/EvidenceContext";
import { MappingComparison } from "@/features/mapping/MappingComparison";
import { BREAKPOINTS, useMediaQuery } from "@/hooks/useMediaQuery";
import { formatTime } from "@/lib/utils/format";
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
  const overlayEvidence = useMediaQuery(BREAKPOINTS.noEvidencePane);
  const isActive = evidence.messageId === message.id;
  const activeId = isActive && evidence.selected ? evidence.selected.citation.citation_id : null;

  const openCitation = (id: string) => {
    const citation = message.citations.find((c) => c.citation_id === id);
    if (!citation) return;
    evidence.show(message.id, message.citations, question);
    evidence.select(message.id, citation, overlayEvidence);
  };
  const showSources = () => {
    evidence.show(message.id, message.citations, question);
    if (overlayEvidence) evidence.setDrawerOpen(true);
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
        <Notice tone="danger" title={message.error.title}
          action={onRetry && message.error.retryable ? <Button variant="secondary" size="sm" icon={<RotateCcw />} onClick={onRetry}>Try again</Button> : undefined}>
          {message.error.message}
        </Notice>
      );
    }
    if (message.status === "incomplete") {
      return (
        <>
          {message.content ? <AnswerMarkdown text={message.content} citations={message.citations} /> : null}
          <Notice tone="warn" title="Response stopped before it finished"
            action={onRetry ? <Button variant="secondary" size="sm" icon={<RotateCcw />} onClick={onRetry}>Try again</Button> : undefined}>
            The stream ended early. You can ask again to get a complete answer.
          </Notice>
        </>
      );
    }
    if (message.status === "insufficient_evidence") {
      return (
        <Notice tone="warn" title="Not enough evidence in the connected sources">
          {message.content || "Legal Lens could not find sufficient supporting legal sources to answer this reliably."}
          <div style={{ marginTop: 6, color: "var(--ink-3)" }}>Name the Act and section, rephrase, or explore the corpus with Search.</div>
        </Notice>
      );
    }
    if (message.status === "refused") {
      return <Notice tone="info" title="Outside what Legal Lens can help with">{message.content}</Notice>;
    }
    if (!message.content && streaming) return null;
    return <AnswerMarkdown text={message.content} citations={message.citations} activeId={activeId} onCite={openCitation} streaming={streaming} />;
  })();

  const complete = !streaming && message.status === "complete";
  return (
    <article className="turn" aria-label="Legal Lens answer" data-testid="assistant-message" data-status={message.status}>
      <div className="turn__label">
        <span>Legal Lens</span>
        <time className="turn__time" dateTime={message.createdAt}>{formatTime(message.createdAt)}</time>
      </div>
      {body}
      {message.bnsAlerts.length > 0 ? <MappingComparison alerts={message.bnsAlerts} /> : null}
      {complete ? (
        message.citations.length > 0 ? (
          <div className="sources" data-testid="sources-row">
            <span className="sources__label">Sources</span>
            {message.citations.map((c) => (
              <CitationChip key={c.citation_id} citation={c} active={activeId === c.citation_id} onClick={() => openCitation(c.citation_id)} />
            ))}
          </div>
        ) : (
          <div className="sources"><span className="t-meta">The answer did not return source evidence.</span></div>
        )
      ) : null}
      {message.warnings.length > 0 && !streaming ? (
        <div className="t-meta" style={{ color: "var(--warn)" }}>{message.warnings.join(" · ")}</div>
      ) : null}
      {complete || message.status === "incomplete" || message.status === "failed" ? (
        <div className="turn__footer">
          {complete ? (
            <span className="trust">
              {message.citations.length > 0 ? (
                <span className="trust__item"><ShieldCheck aria-hidden="true" />Based on {message.citations.length} retrieved legal source{message.citations.length === 1 ? "" : "s"}</span>
              ) : null}
              {message.analysis?.decomposition_needed ? <span className="trust__item">Multi-aspect research</span> : null}
            </span>
          ) : null}
          <span className="turn__spacer" />
          {message.citations.length > 0 && complete ? <Button size="sm" icon={<BookOpenText />} onClick={showSources}><span>View evidence</span></Button> : null}
          {message.content ? <Button size="sm" icon={<Copy />} onClick={copy} aria-label="Copy answer"><span>Copy</span></Button> : null}
          {onRetry && complete ? <Button size="sm" icon={<RotateCcw />} onClick={onRetry} aria-label="Regenerate answer"><span>Regenerate</span></Button> : null}
        </div>
      ) : null}
      {streaming && onStop && message.content ? (
        <div className="turn__footer"><Button size="sm" variant="secondary" icon={<Square />} onClick={onStop}>Stop</Button></div>
      ) : null}
      {complete && message.disclaimer ? <p className="t-meta" style={{ margin: 0 }}>{message.disclaimer}</p> : null}
    </article>
  );
});
