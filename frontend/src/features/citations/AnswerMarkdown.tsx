import { createContext, memo, useContext, useMemo, type AnchorHTMLAttributes, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { linkCitations } from "@/lib/utils/citations";
import type { Citation } from "@/types/api";

interface Props {
  text: string;
  citations: Citation[];
  activeId?: string | null;
  onCite?: (id: string) => void;
  streaming?: boolean;
}

interface CiteContextValue {
  citations: Citation[];
  activeId: string | null;
  onCite?: (id: string) => void;
}

const CiteContext = createContext<CiteContextValue>({ citations: [], activeId: null });

/** Stable component type (never recreated per render, so chips keep their DOM nodes across updates). */
function MarkdownLink({ href, children, ...rest }: AnchorHTMLAttributes<HTMLAnchorElement> & { children?: ReactNode; node?: unknown }) {
  const { citations, activeId, onCite } = useContext(CiteContext);
  if (href && href.startsWith("#cite-")) {
    const id = href.slice(6);
    const citation = citations.find((c) => c.citation_id === id);
    const label = citation ? `${citation.act ? `${citation.act} ` : ""}${citation.section ? citation.section : citation.title}` : id;
    return (
      <button type="button" className={`cite${activeId === id ? " cite--active" : ""}`}
        title={`Open source ${id}: ${label}`} aria-label={`Citation ${id}: ${label}`} onClick={() => onCite?.(id)}>
        {children}
      </button>
    );
  }
  const { node: _node, ...anchor } = rest;
  void _node;
  return <a href={href} target="_blank" rel="noopener noreferrer" {...anchor}>{children}</a>;
}

const COMPONENTS: Components = { a: MarkdownLink };

/**
 * Markdown renderer for answers. Raw HTML is never rendered (react-markdown escapes it by default),
 * so answer text, citations and excerpts cannot inject markup. `[C1]` becomes a citation chip.
 */
export const AnswerMarkdown = memo(function AnswerMarkdown({ text, citations, activeId = null, onCite, streaming }: Props) {
  const known = useMemo(() => new Set(citations.map((c) => c.citation_id)), [citations]);
  const source = useMemo(() => linkCitations(text, known), [text, known]);
  const ctx = useMemo(() => ({ citations, activeId, onCite }), [citations, activeId, onCite]);
  return (
    <CiteContext.Provider value={ctx}>
      <div className={`answer${streaming ? " answer--streaming" : ""}`}>
        <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml components={COMPONENTS}>
          {source}
        </ReactMarkdown>
      </div>
    </CiteContext.Provider>
  );
});
