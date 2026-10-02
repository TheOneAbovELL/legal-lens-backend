import { useEffect } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { IconButton } from "@/components/ui/Button";
import { truncate } from "@/lib/utils/format";
import { EvidenceCard } from "./EvidenceCard";
import { useEvidence } from "./EvidenceContext";

/** Previous / next citation controls, shared by the desktop pane and the mobile sheet. */
export function EvidenceTools() {
  const { citations, selected, step } = useEvidence();
  if (citations.length < 2) return null;
  const idx = selected ? citations.findIndex((c) => c.citation_id === selected.citation.citation_id) : -1;
  return (
    <div className="ev__nav" aria-label="Citation navigation">
      <IconButton label="Previous citation" size="sm" onClick={() => step(-1)}><ChevronLeft /></IconButton>
      <span aria-live="polite">{idx >= 0 ? `${idx + 1} / ${citations.length}` : `${citations.length}`}</span>
      <IconButton label="Next citation" size="sm" onClick={() => step(1)}><ChevronRight /></IconButton>
    </div>
  );
}

export function EvidenceList() {
  const { citations, messageId, question, selected, select } = useEvidence();
  useEffect(() => {
    if (!selected) return;
    document.getElementById(`source-${selected.citation.citation_id}`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selected]);
  if (!messageId) {
    return (
      <div className="ev__empty">
        <strong>No evidence selected</strong>
        Sources cited in an answer appear here. Select a citation such as <span className="cite cite--static"><span className="cite__id">C1</span></span> to inspect the passage behind it.
      </div>
    );
  }
  if (citations.length === 0) {
    return <div className="ev__empty"><strong>No sources for this answer</strong>The answer did not return source evidence.</div>;
  }
  return (
    <>
      {question ? <div className="ev__question">Cited for: <b>{truncate(question, 140)}</b></div> : null}
      <div data-testid="evidence-list">
        {citations.map((c) => (
          <EvidenceCard key={c.citation_id} citation={c} question={question}
            selected={selected?.messageId === messageId && selected.citation.citation_id === c.citation_id}
            onSelect={() => select(messageId, c)} />
        ))}
      </div>
    </>
  );
}

/** Desktop right-hand pane. */
export function EvidencePane() {
  const { citations, messageId } = useEvidence();
  return (
    <aside className="evidence-pane" aria-label="Sources and evidence">
      <div className="ev__head">
        <span className="ev__title">Evidence {messageId ? <span className="ev__count">· {citations.length} source{citations.length === 1 ? "" : "s"}</span> : null}</span>
        <EvidenceTools />
      </div>
      <div className="ev__body"><EvidenceList /></div>
    </aside>
  );
}
