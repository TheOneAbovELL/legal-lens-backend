import { useMutation } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";
import { Link, useLocation, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, Search } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { citationLabel } from "@/components/ui/Chip";
import { Notice, Skeleton } from "@/components/ui/Feedback";
import { searchApi } from "@/lib/api";
import { highlightTerms } from "@/lib/utils/citations";
import { describeError } from "@/lib/utils/errors";
import type { Citation } from "@/types/api";
import { Highlighted } from "./EvidenceCard";

/**
 * Document reader. The citation passed through router state renders immediately; the full passage
 * and sibling passages are then fetched through the search engine (filtered to the document) so the
 * page also works after a refresh.
 */
export function SourcePage() {
  const { documentId = "" } = useParams();
  const [params] = useSearchParams();
  const chunkId = params.get("chunk");
  const state = useLocation().state as { citation?: Citation; question?: string | null; from?: string } | null;
  const seed = state?.citation ?? null;
  const backTo = state?.from && state.from.startsWith("/app") ? state.from : "/app";

  const lookup = useMutation({
    mutationFn: () => searchApi.search({ query: seed ? `${seed.act ?? ""} ${seed.section ?? seed.title}`.trim() : documentId, top_k: 20, filters: { document_ids: [documentId] } }),
  });
  useEffect(() => {
    lookup.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documentId, chunkId]);

  const hit = lookup.data?.results.find((r) => r.chunk_id === chunkId) ?? lookup.data?.results[0];
  const citation: Citation | null = hit ? { ...hit.citation, excerpt: hit.content } : seed;
  const error = lookup.error ? describeError(lookup.error) : null;
  const terms = useMemo(() => highlightTerms(state?.question ?? ""), [state?.question]);
  const others = (lookup.data?.results ?? []).filter((r) => r.chunk_id !== (hit?.chunk_id ?? chunkId)).slice(0, 8);

  return (
    <div className="page">
      <article className="doc">
        <div className="doc__bar">
          <Link to={backTo} className="btn btn--ghost btn--sm"><ArrowLeft />Back</Link>
          <Link to="/app/search" className="btn btn--ghost btn--sm"><Search />Search</Link>
        </div>
        {citation ? (
          <>
            <p className="doc__kicker">{citation.act ? `${citation.act}` : "Source document"}{citation.section ? ` · Section ${citation.section}` : ""}</p>
            <h1 className="doc__title">{citation.section_heading ?? citationLabel(citation)}</h1>
            <div className="doc__meta">
              <span><b>Document</b> {citation.title}</span>
              {citation.subsection ? <span><b>Sub-provision</b> {citation.subsection}</span> : null}
              {citation.page ? <span><b>Page</b> {citation.page}</span> : null}
              {citation.court ? <span><b>Court</b> {citation.court}</span> : null}
              {citation.cite_as ? <span><b>Cite as</b> {citation.cite_as}</span> : null}
              {citation.opinion_type ? (
                <span><b>Opinion</b> {citation.opinion_type}{citation.opinion_author ? ` · ${citation.opinion_author}` : ""}</span>
              ) : null}
              <span><b>Source</b> {citation.source}{citation.document_version ? ` · version ${citation.document_version.replace(/^v-?/, "")}` : ""}</span>
            </div>
            <div className="doc__text" data-testid="source-text">
              <Highlighted text={citation.excerpt || "No text stored for this passage."} terms={terms} />
            </div>
          </>
        ) : lookup.isPending ? (
          <Skeleton lines={8} />
        ) : null}
        {error ? (
          <div style={{ marginTop: 24 }}>
            <Notice tone="danger" title={error.title} action={error.retryable ? <Button variant="secondary" size="sm" onClick={() => lookup.mutate()}>Retry</Button> : undefined}>
              {error.message}
            </Notice>
          </div>
        ) : null}
        {lookup.data && lookup.data.results.length === 0 && !citation ? (
          <Notice tone="warn">This document is not present in the connected corpus.</Notice>
        ) : null}
        {others.length > 0 ? (
          <section className="doc__section" aria-label="Other passages from this document">
            <h2>Other passages from this document</h2>
            {others.map((r) => (
              <div key={r.chunk_id} className="doc__passage">
                <h3>{citationLabel(r.citation)}{r.citation.section_heading ? ` — ${r.citation.section_heading}` : ""}</h3>
                <p>{r.content}</p>
                <Link className="btn btn--ghost btn--sm" style={{ marginTop: 6 }} to={`/app/sources/${encodeURIComponent(documentId)}?chunk=${encodeURIComponent(r.chunk_id)}`}
                  state={{ citation: { ...r.citation, excerpt: r.content }, question: state?.question ?? null, from: backTo }}>
                  Read passage
                </Link>
              </div>
            ))}
          </section>
        ) : null}
      </article>
    </div>
  );
}
