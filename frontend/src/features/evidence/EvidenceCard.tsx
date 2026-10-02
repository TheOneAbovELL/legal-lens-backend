import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Copy, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { citationLabel } from "@/components/ui/Chip";
import { useToast } from "@/components/ui/Toast";
import { highlightTerms } from "@/lib/utils/citations";
import type { Citation } from "@/types/api";

/** Highlight question terms inside a passage without injecting HTML. */
export function Highlighted({ text, terms }: { text: string; terms: string[] }) {
  const parts = useMemo(() => {
    if (!terms.length || !text) return [{ text, hit: false }];
    const pattern = new RegExp(`(${terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi");
    const lower = new Set(terms.map((t) => t.toLowerCase()));
    return text.split(pattern).filter((p) => p !== "").map((p) => ({ text: p, hit: lower.has(p.toLowerCase()) }));
  }, [text, terms]);
  return <>{parts.map((p, i) => (p.hit ? <mark key={i}>{p.text}</mark> : <span key={i}>{p.text}</span>))}</>;
}

export function sourceHref(c: Citation): string {
  const params = new URLSearchParams();
  if (c.chunk_id) params.set("chunk", c.chunk_id);
  return `/app/sources/${encodeURIComponent(c.document_id)}?${params.toString()}`;
}

interface Props {
  citation: Citation;
  selected?: boolean;
  question?: string | null;
  onSelect?: () => void;
  /** Hide actions (preview inside search). */
  compact?: boolean;
}

/** A cited passage rendered like a document extract, with the "why" line and the question terms marked. */
export function EvidenceCard({ citation, selected, question, onSelect, compact }: Props) {
  const [open, setOpen] = useState(false);
  const { notify } = useToast();
  const terms = useMemo(() => highlightTerms(question ?? ""), [question]);
  const label = citationLabel(citation);
  const why = citation.retrieval_sources.includes("metadata")
    ? "Exact match for a provision named in the question"
    : citation.retrieval_sources.includes("graph")
      ? "Linked provision from the knowledge graph"
      : terms.length ? "Passage ranked relevant to the question" : null;
  const copy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(`${citation.citation_id} ${label} — ${citation.title} (${citation.source})\n${citation.excerpt}`);
      notify({ tone: "success", title: "Citation copied" });
    } catch {
      notify({ tone: "danger", title: "Copy failed", message: "Clipboard access was denied." });
    }
  };
  return (
    <article className={`evc${selected ? " evc--selected" : ""}`} id={`source-${citation.citation_id}`} aria-current={selected ? "true" : undefined}
      onClick={onSelect} data-testid="source-card" tabIndex={onSelect ? 0 : undefined}
      onKeyDown={(e) => { if (onSelect && (e.key === "Enter" || e.key === " ") && e.target === e.currentTarget) { e.preventDefault(); onSelect(); } }}>
      <div className="evc__head">
        <span className="cite cite--static" aria-hidden="true"><span className="cite__id">{citation.citation_id}</span></span>
        <h3 className="evc__title">{label}</h3>
      </div>
      <p className="evc__doc">
        {citation.title}
        {citation.section_heading ? ` · ${citation.section_heading}` : ""}
        {citation.subsection ? ` · sub-provision ${citation.subsection}` : ""}
        {citation.page ? ` · p. ${citation.page}` : ""}
        {citation.court ? ` · ${citation.court}` : ""}
      </p>
      {why ? <p className="evc__why">{why}</p> : null}
      {citation.excerpt ? (
        <p className={`evc__text${open ? " evc__text--open" : ""}`}><Highlighted text={citation.excerpt} terms={terms} /></p>
      ) : (
        <p className="evc__text" style={{ color: "var(--ink-3)" }}>No excerpt stored for this source.</p>
      )}
      <div className="evc__foot">
        <span>{citation.source}{citation.document_version ? ` · version ${citation.document_version.replace(/^v-?/, "")}` : ""}</span>
        {!compact ? (
          <span className="row" style={{ marginLeft: "auto", gap: 2 }} onClick={(e) => e.stopPropagation()}>
            {citation.excerpt && citation.excerpt.length > 420 ? (
              <Button size="sm" onClick={() => setOpen((o) => !o)} aria-expanded={open}>{open ? "Less" : "More"}</Button>
            ) : null}
            <Button size="sm" icon={<Copy />} onClick={copy}>Copy</Button>
            <Link className="btn btn--sm btn--ghost" to={sourceHref(citation)}
              state={{ citation, question, from: window.location.pathname + window.location.search }}>
              <ExternalLink />Open source
            </Link>
          </span>
        ) : null}
      </div>
    </article>
  );
}
