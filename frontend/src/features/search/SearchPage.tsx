import { useEffect, useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ChevronDown, Search } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Field";
import { Notice, Skeleton } from "@/components/ui/Feedback";
import { EvidenceCard } from "@/features/evidence/EvidenceCard";
import { searchApi } from "@/lib/api";
import { describeError } from "@/lib/utils/errors";
import type { SearchFilters, SearchResponse } from "@/types/api";
import { SearchResult } from "./SearchResult";

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
    onSuccess: () => setSelected(0),
  });
  // A shared link (/app/search?q=…) runs its query on arrival.
  const initial = params.get("q");
  useEffect(() => {
    if (initial?.trim()) search.mutate({ query: initial.trim(), filters: null });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
      <div className="page__col">
        <div className="page__head">
          <h1 className="t-title">Search legal sources</h1>
          <p className="page__lead">Explore the connected corpus directly. The same retrieval that grounds answers, without generation.</p>
        </div>
        <form onSubmit={submit} aria-label="Search">
          <div className="searchbar">
            <label htmlFor="search-input" className="sr-only">Search query</label>
            <input id="search-input" className="input" value={query} onChange={(e) => setQuery(e.target.value)}
              placeholder="Section 420 IPC · punishment for theft · Article 21" data-testid="search-input" autoFocus />
            <Button type="submit" variant="primary" size="lg" icon={<Search />} loading={search.isPending} disabled={!query.trim()} data-testid="search-button">Search</Button>
          </div>
          <details>
            <summary className="filters__toggle"><ChevronDown />Filters</summary>
            <div className="filters">
              <Select id="filter-act" label="Act" value={act} onChange={(e) => setAct(e.target.value)}>
                {ACTS.map((a) => <option key={a} value={a}>{a || "Any act"}</option>)}
              </Select>
              <Input id="filter-section" label="Section / Article" value={section} onChange={(e) => setSection(e.target.value)} placeholder="e.g. 420" />
              <Select id="filter-type" label="Document type" value={docType} onChange={(e) => setDocType(e.target.value)}>
                {TYPES.map((t) => <option key={t} value={t}>{t ? t.replace("_", " ") : "Any type"}</option>)}
              </Select>
            </div>
          </details>
        </form>

        {search.isPending ? <div className="stack"><Skeleton lines={3} /><Skeleton lines={3} /></div> : null}
        {error ? (
          <Notice tone="danger" title={error.title} action={error.retryable ? <Button variant="secondary" size="sm" onClick={() => submit()}>Retry</Button> : undefined}>{error.message}</Notice>
        ) : null}
        {data ? (
          <>
            <div className="results-meta" data-testid="search-meta">
              <span>{data.total} result{data.total === 1 ? "" : "s"} for “{data.query}”</span>
              {data.retrieval_metadata.complexity ? <span>· {data.retrieval_metadata.complexity.toLowerCase()} query</span> : null}
              {data.retrieval_metadata.subqueries > 1 ? <span>· {data.retrieval_metadata.subqueries} sub-queries</span> : null}
              <span>· {Object.keys(data.retrieval_metadata.sources).filter((k) => (data.retrieval_metadata.sources[k] ?? 0) > 0).length > 1 ? "hybrid retrieval" : "retrieval"}</span>
            </div>
            {data.warnings.map((w) => <Notice key={w} tone="warn">{w}</Notice>)}
            {data.results.length === 0 ? (
              <Notice>No matching legal evidence was found in the connected corpus. Try naming the Act and section, or remove a filter.</Notice>
            ) : (
              <div className="results-grid">
                <div className="results" data-testid="search-results">
                  {data.results.map((r, i) => (
                    <SearchResult key={r.chunk_id} result={r} query={data.query} selected={selected === i} onSelect={() => setSelected(i)}
                      onUseInResearch={() => navigate("/app", { state: { prefill: `${data.query} (see ${r.citation.act ?? ""} ${r.citation.section ?? r.citation.title})`.trim() } })} />
                  ))}
                </div>
                <div className="results-aside">
                  {current ? (
                    <EvidenceCard citation={{ ...current.citation, excerpt: current.content }} question={data.query} selected />
                  ) : (
                    <div className="ev__empty"><strong>No passage selected</strong>Select a result to read the full passage.</div>
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
