import { useEffect } from "react";
import { SourceCard } from "./SourceCard";
import { useEvidence } from "./EvidenceContext";

/** Right-hand evidence list (desktop) or drawer body (mobile). */
export function EvidenceList() {
  const { citations, messageId, question, selected, select } = useEvidence();
  useEffect(() => {
    if (!selected) return;
    document.getElementById(`source-${selected.citation.citation_id}`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selected]);
  if (!messageId) {
    return <div className="evidence__empty">Sources cited in an answer appear here. Click a citation such as [C1] to inspect it.</div>;
  }
  if (citations.length === 0) {
    return <div className="evidence__empty">The answer did not return source evidence.</div>;
  }
  return (
    <div className="evidence__list" data-testid="evidence-list">
      {citations.map((c) => (
        <SourceCard key={c.citation_id} citation={c} question={question}
          selected={selected?.messageId === messageId && selected.citation.citation_id === c.citation_id}
          onSelect={() => select(messageId, c)} />
      ))}
    </div>
  );
}

export function EvidencePanel() {
  const { citations, messageId } = useEvidence();
  return (
    <aside className="evidence" aria-label="Sources and evidence">
      <div className="evidence__head">
        <span>Sources</span>
        {messageId ? <span className="badge">{citations.length}</span> : null}
      </div>
      <EvidenceList />
    </aside>
  );
}
