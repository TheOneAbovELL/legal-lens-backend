import { useMutation } from "@tanstack/react-query";
import { useEffect } from "react";
import { Link, useLocation, useParams, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Alert, Skeleton } from "@/components/ui/Card";
import { searchApi } from "@/lib/api";
import { describeError } from "@/lib/utils/errors";
import type { Citation } from "@/types/api";
import { SourceCard } from "./SourceCard";

/**
 * Full-page source viewer. The citation passed through router state renders immediately; the full
 * passage is then fetched through the search engine (filtered to the document) so the page also
 * works after a refresh.
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

  return (
    <div className="page">
      <div className="page__inner" style={{ maxWidth: 820 }}>
        <div className="row">
          <Link to={backTo} className="btn btn--sm btn--ghost">← Back</Link>
          <Link to="/app/search" className="btn btn--sm btn--ghost">Search</Link>
        </div>
        <h1>Source</h1>
        <p className="page__lead">Document <code>{documentId}</code>{chunkId ? <> · passage <code>{chunkId}</code></> : null}</p>
        {citation ? <SourceCard citation={citation} question={state?.question ?? null} selected compact /> : null}
        {lookup.isPending && !citation ? <Skeleton lines={6} /> : null}
        {error ? (
          <Alert tone="danger" title={error.title} action={error.retryable ? <Button size="sm" onClick={() => lookup.mutate()}>Retry</Button> : undefined}>
            {error.message}
          </Alert>
        ) : null}
        {lookup.data && lookup.data.results.length > 1 ? (
          <>
            <h2 style={{ fontSize: 16, margin: "8px 0 0" }}>Other passages from this document</h2>
            <div className="results">
              {lookup.data.results.filter((r) => r.chunk_id !== (hit?.chunk_id ?? chunkId)).slice(0, 8).map((r) => (
                <SourceCard key={r.chunk_id} citation={{ ...r.citation, excerpt: r.content }} question={state?.question ?? null} compact />
              ))}
            </div>
          </>
        ) : null}
        {lookup.data && lookup.data.results.length === 0 && !citation ? (
          <Alert tone="warning">This document is not present in the connected corpus.</Alert>
        ) : null}
      </div>
    </div>
  );
}
