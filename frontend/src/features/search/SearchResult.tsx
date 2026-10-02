import { Link } from "react-router-dom";
import { ExternalLink, MessageSquarePlus } from "lucide-react";
import { Badge, MappingBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { citationLabel } from "@/components/ui/Chip";
import { Highlighted, sourceHref } from "@/features/evidence/EvidenceCard";
import { highlightTerms } from "@/lib/utils/citations";
import type { SearchResult as SearchResultT } from "@/types/api";

interface Props {
  result: SearchResultT;
  query: string;
  selected: boolean;
  onSelect: () => void;
  onUseInResearch: () => void;
}

/** Compact, information-rich result: provision, document, passage, mapping. No raw scores. */
export function SearchResult({ result, query, selected, onSelect, onUseInResearch }: Props) {
  const c = result.citation;
  const terms = highlightTerms(query);
  const exact = result.retrieval_sources.includes("metadata");
  return (
    <article className={`result${selected ? " result--selected" : ""}`} data-testid="search-result" onClick={onSelect} tabIndex={0}
      aria-current={selected ? "true" : undefined}
      onKeyDown={(e) => { if ((e.key === "Enter" || e.key === " ") && e.target === e.currentTarget) { e.preventDefault(); onSelect(); } }}>
      <div className="result__head">
        <h3 className="result__title">{citationLabel(c)}</h3>
        {exact ? <Badge tone="ok" title="Matches a provision named in the query">exact</Badge> : null}
      </div>
      <p className="result__doc">{c.title}{c.section_heading ? ` · ${c.section_heading}` : ""}{c.page ? ` · p. ${c.page}` : ""}</p>
      <p className="result__snippet"><Highlighted text={result.snippet} terms={terms} /></p>
      <div className="result__foot" onClick={(e) => e.stopPropagation()}>
        {result.bns_alert ? <><MappingBadge type={result.bns_alert.mapping_type} /><span>{result.bns_alert.old} → {result.bns_alert.new ?? "no equivalent"}</span></> : null}
        <span style={{ marginLeft: "auto", display: "inline-flex", gap: 2 }}>
          <Button size="sm" icon={<MessageSquarePlus />} onClick={onUseInResearch}>Use in research</Button>
          <Link className="btn btn--sm btn--ghost" to={sourceHref(c)}
            state={{ citation: { ...c, excerpt: result.content }, question: query, from: window.location.pathname + window.location.search }}>
            <ExternalLink />Open source
          </Link>
        </span>
      </div>
    </article>
  );
}
