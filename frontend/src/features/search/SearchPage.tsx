import { useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Badge, ComplexityBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Alert, Skeleton } from "@/components/ui/Card";
import { Input } from "@/components/ui/Field";
import { SourceCard } from "@/features/citations/SourceCard";
import { searchApi } from "@/lib/api";
import { describeError } from "@/lib/utils/errors";
import { formatMs } from "@/lib/utils/format";
import type { SearchFilters, SearchResponse } from "@/types/api";
import { SearchResultCard } from "./SearchResultCard";

const ACTS = ["", "IPC", "BNS", "CRPC", "BNSS", "IEA", "BSA", "CONSTITUTION"];
const TYPES = ["", "statute", "constitution", "case_law", "regulation", "commentary", "other"];

export function SearchPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [query, setQuery] = useState(params.get("q") ?? "");
  const [act, setAct] = useState("");
  const [section, setSection] = useState("");
  const [docType, setDocType] = useState("");
  const [selected, setSelected] = useState<number | null>(null);

  const search = useMutation({
    mutationFn: (body: { query: string; filters: SearchFilters | null }) => searchApi.search({ query: body.query, top_k: 10, filters: body.filters }),
    onSuccess: () => setSelected(null),
  });

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    const text = query.trim();
    if (!text) return;
    const filters: SearchFilters = {};
    if (act) filters.acts = [act];
    if (section.trim()) filters.sections = [section.trim()];
    if (docType) filters.document_types = [docType];
    setParams({ q: text });
    search.mutate({ query: text, filters: Object.keys(filters).length ? filters : null });
  };

  const data: SearchResponse | undefined = search.data;
  const current = selected !== null && data ? data.results[selected] : undefined;
  const error = search.error ? describeError(search.error) : null;

  return (
    <div className="page">
      <div className="page__inner">
        <h1>Search legal evidence</h1>
        <p className="page__lead">Retrieval only — the same hybrid engine that grounds chat answers, without generation.</p>
        <form onSubmit={submit} className="stack" aria-label="Search">
          <div className="searchbar">
            <label htmlFor="search-input" className="visually-hidden">Search query</label>
            <input id="search-input" className="input" value={query} onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. Section 420 IPC, punishment for theft, Article 21" data-testid="search-input" />
            <Button type="submit" variant="primary" loading={search.isPending} disabled={!query.trim()} data-testid="search-button">Search</Button>
          </div>
          <details>
            <summary style={{ cursor: "pointer", color: "var(--text-muted)", fontSize: 14 }}>Filters</summary>
            <div className="filters" style={{ marginTop: 12 }}>
              <div className="field">
                <label className="field__label" htmlFor="filter-act">Act</label>
                <select id="filter-act" className="input" value={act} onChange={(e) => setAct(e.target.value)}>
                  {ACTS.map((a) => <option key={a} value={a}>{a || "Any act"}</option>)}
                </select>
              </div>
              <Input id="filter-section" label="Section / Article" value={section} onChange={(e) => setSection(e.target.value)} placeholder="e.g. 420" />
              <div className="field">
                <label className="field__label" htmlFor="filter-type">Document type</label>
                <select id="filter-type" className="input" value={docType} onChange={(e) => setDocType(e.target.value)}>
                  {TYPES.map((t) => <option key={t} value={t}>{t ? t.replace("_", " ") : "Any type"}</option>)}
                </select>
              </div>
            </div>
          </details>
        </form>

        {search.isPending ? <div className="stack"><Skeleton lines={3} /><Skeleton lines={3} /></div> : null}
        {error ? (
          <Alert tone="danger" title={error.title} action={error.retryable ? <Button size="sm" onClick={() => submit()}>Retry</Button> : undefined}>{error.message}</Alert>
        ) : null}
        {data ? (
          <>
            <div className="row" style={{ fontSize: 13, color: "var(--text-muted)" }} data-testid="search-meta">
              <span>{data.total} result{data.total === 1 ? "" : "s"}</span>
              <span>· {formatMs(data.processing_time_ms)}</span>
              <ComplexityBadge complexity={data.retrieval_metadata.complexity} />
              {data.retrieval_metadata.strategy ? <Badge>{data.retrieval_metadata.strategy}</Badge> : null}
              {Object.entries(data.retrieval_metadata.sources).map(([name, hits]) => (
                <Badge key={name} title={`${hits} hits from ${name} retrieval`}>{name}: {hits}</Badge>
              ))}
              {data.retrieval_metadata.reranker ? <Badge title="Reranker">rerank: {data.retrieval_metadata.reranker}</Badge> : null}
            </div>
            {data.warnings.map((w) => <Alert key={w} tone="warning">{w}</Alert>)}
            {data.results.length === 0 ? (
              <Alert tone="info">No matching legal evidence was found in the connected corpus.</Alert>
            ) : (
              <div className="grid-2">
                <div className="results" data-testid="search-results">
                  {data.results.map((r, i) => (
                    <SearchResultCard key={r.chunk_id} result={r} query={data.query} selected={selected === i}
                      onSelect={() => setSelected(i)}
                      onUseInChat={() => navigate("/app", { state: { prefill: `${data.query} (see ${r.citation.act ?? ""} ${r.citation.section ?? r.citation.title})`.trim() } })} />
                  ))}
                </div>
                <div>
                  {current ? (
                    <SourceCard citation={{ ...current.citation, excerpt: current.content }} question={data.query} selected />
                  ) : (
                    <div className="evidence__empty">Select a result to inspect the full passage.</div>
                  )}
                </div>
              </div>
            )}
          </>
        ) : null}
      </div>
    </div>
  );
}
