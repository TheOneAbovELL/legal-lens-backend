import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Highlighted, sourceHref } from "@/features/citations/SourceCard";
import { MappingBadge } from "@/components/ui/Badge";
import { highlightTerms } from "@/lib/utils/citations";
import { provisionLabel } from "@/lib/utils/format";
import type { SearchResult } from "@/types/api";

interface Props {
  result: SearchResult;
  query: string;
  selected: boolean;
  onSelect: () => void;
  onUseInChat: () => void;
}

export function SearchResultCard({ result, query, selected, onSelect, onUseInChat }: Props) {
  const c = result.citation;
  const terms = highlightTerms(query);
  const docType = typeof result.metadata.document_type === "string" ? result.metadata.document_type : null;
  return (
    <article className={`source${selected ? " source--selected" : ""}`} data-testid="search-result" onClick={onSelect}>
      <div className="source__head">
        <h3 className="source__title">{provisionLabel(c)}</h3>
        {result.retrieval_sources.includes("metadata") ? <Badge tone="success" title="Exact provision match">exact</Badge> : null}
      </div>
      <div className="source__meta">
        <Badge>{c.title}</Badge>
        {docType ? <Badge>{docType.replace("_", " ")}</Badge> : null}
        {c.section_heading ? <Badge>{c.section_heading}</Badge> : null}
        {c.page ? <Badge>p. {c.page}</Badge> : null}
        <span className="result__score" title="Final ranking score">{result.relevance_score.toFixed(3)}</span>
      </div>
      <p className="source__excerpt"><Highlighted text={result.snippet} terms={terms} /></p>
      {result.bns_alert ? (
        <div className="row" style={{ fontSize: 13 }}>
          <MappingBadge type={result.bns_alert.mapping_type} />
          <span>{result.bns_alert.old} → {result.bns_alert.new ?? "no equivalent"}</span>
        </div>
      ) : null}
      <div className="source__actions" onClick={(e) => e.stopPropagation()}>
        <Link className="btn btn--sm btn--ghost" to={sourceHref(c)}
          state={{ citation: { ...c, excerpt: result.content }, question: query, from: window.location.pathname + window.location.search }}>Open source</Link>
        <Button size="sm" variant="ghost" onClick={onUseInChat}>Use in chat</Button>
      </div>
    </article>
  );
}
