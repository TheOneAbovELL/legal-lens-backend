import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";
import { highlightTerms } from "@/lib/utils/citations";
import { provisionLabel } from "@/lib/utils/format";
import type { Citation } from "@/types/api";

interface Props {
  citation: Citation;
  selected?: boolean;
  question?: string | null;
  onSelect?: () => void;
  compact?: boolean;
}

/** Highlight question terms inside an excerpt without injecting HTML. */
export function Highlighted({ text, terms }: { text: string; terms: string[] }) {
  const parts = useMemo(() => {
    if (!terms.length || !text) return [{ text, hit: false }];
    const pattern = new RegExp(`(${terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi");
    return text.split(pattern).filter((p) => p !== "").map((p) => ({ text: p, hit: pattern.test(p) && terms.includes(p.toLowerCase()) }));
  }, [text, terms]);
  return <>{parts.map((p, i) => (p.hit ? <mark key={i}>{p.text}</mark> : <span key={i}>{p.text}</span>))}</>;
}

export function sourceHref(c: Citation): string {
  const params = new URLSearchParams();
  if (c.chunk_id) params.set("chunk", c.chunk_id);
  return `/app/sources/${encodeURIComponent(c.document_id)}?${params.toString()}`;
}

export function SourceCard({ citation, selected, question, onSelect, compact }: Props) {
  const [open, setOpen] = useState(false);
  const { notify } = useToast();
  const terms = useMemo(() => highlightTerms(question ?? ""), [question]);
  const copy = async () => {
    const text = `${citation.citation_id} — ${provisionLabel(citation)} (${citation.source})\n${citation.excerpt}`;
    try {
      await navigator.clipboard.writeText(text);
      notify({ tone: "success", title: "Citation copied" });
    } catch {
      notify({ tone: "danger", title: "Copy failed", message: "Clipboard access was denied." });
    }
  };
  return (
    <article className={`source${selected ? " source--selected" : ""}`} id={`source-${citation.citation_id}`}
      aria-current={selected ? "true" : undefined} onClick={onSelect} data-testid="source-card">
      <div className="source__head">
        <span className="cite" aria-hidden="true">{citation.citation_id}</span>
        <h3 className="source__title">{provisionLabel(citation)}</h3>
      </div>
      <div className="source__meta">
        <Badge>{citation.title}</Badge>
        {citation.section_heading ? <Badge>{citation.section_heading}</Badge> : null}
        {citation.page ? <Badge>p. {citation.page}</Badge> : null}
        {citation.court ? <Badge>{citation.court}</Badge> : null}
        {typeof citation.score === "number" ? <Badge title="Retrieval relevance">rel. {citation.score.toFixed(2)}</Badge> : null}
      </div>
      {citation.excerpt ? (
        <p className={`source__excerpt${open ? " source__excerpt--open" : ""}`}>
          <Highlighted text={citation.excerpt} terms={terms} />
        </p>
      ) : (
        <p className="source__excerpt" style={{ color: "var(--text-faint)" }}>No excerpt stored for this source.</p>
      )}
      <div className="source__meta" style={{ fontSize: 12, color: "var(--text-faint)" }}>
        <span>Source: {citation.source}</span>
        {citation.document_version ? <span> · v{citation.document_version}</span> : null}
      </div>
      {!compact ? (
        <div className="source__actions" onClick={(e) => e.stopPropagation()}>
          {citation.excerpt && citation.excerpt.length > 280 ? (
            <Button size="sm" variant="ghost" onClick={() => setOpen((o) => !o)} aria-expanded={open}>{open ? "Show less" : "Show more"}</Button>
          ) : null}
          <Button size="sm" variant="ghost" onClick={copy}>Copy</Button>
          <Link className="btn btn--sm btn--ghost" to={sourceHref(citation)}
            state={{ citation, question, from: window.location.pathname + window.location.search }}>Open source</Link>
        </div>
      ) : null}
    </article>
  );
}
