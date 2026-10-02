import { useMutation, useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { Wrench } from "lucide-react";
import { appConfig } from "@/app/config";
import { StatusText, type Health } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Field";
import { Skeleton } from "@/components/ui/Feedback";
import { diagnosticsApi, systemApi } from "@/lib/api";
import { describeError } from "@/lib/utils/errors";
import { formatMs } from "@/lib/utils/format";

function componentHealth(status: string): Health {
  if (status === "ok" || status === "configured") return "healthy";
  if (status === "disabled" || status === "loading" || status === "not_configured") return "degraded";
  return "unavailable";
}

function Block({ title, health, children, raw }: { title: string; health: Health; children: ReactNode; raw?: unknown }) {
  return (
    <section className="diag__block" aria-label={title}>
      <div className="diag__head"><span>{title}</span><StatusText health={health} /></div>
      <div className="diag__body">
        {children}
        {raw !== undefined ? <details><summary>raw</summary><pre>{JSON.stringify(raw, null, 2)}</pre></details> : null}
      </div>
    </section>
  );
}

/** Developer surface: deliberately monospace, plain status words, raw payloads behind "raw". Never shows secrets. */
export function DiagnosticsPage() {
  const ready = useQuery({ queryKey: ["ready"], queryFn: ({ signal }) => systemApi.ready(signal), retry: false });
  const config = useQuery({ queryKey: ["diag", "config"], queryFn: ({ signal }) => diagnosticsApi.config(signal), retry: false });
  const qdrant = useQuery({ queryKey: ["diag", "qdrant"], queryFn: ({ signal }) => diagnosticsApi.qdrant(signal), retry: false });
  const embedding = useQuery({ queryKey: ["diag", "embedding"], queryFn: ({ signal }) => diagnosticsApi.embedding(signal), retry: false });
  const llm = useMutation({ mutationFn: () => diagnosticsApi.llm() });
  const [routeQuery, setRouteQuery] = useState("Compare IPC 420 and BNS 318.");
  const route = useMutation({ mutationFn: (q: string) => diagnosticsApi.route(q) });

  if (!appConfig.diagnosticsEnabled) return <Navigate to="/app" replace />;

  const overall: Health = ready.isError ? "unavailable" : ready.isPending ? "unknown" : ready.data.status === "ready" ? "healthy" : "degraded";

  return (
    <div className="page diag">
      <div className="page__col">
        <div className="diag__banner"><Wrench size={14} aria-hidden="true" />developer diagnostics · not part of the product · hidden in production builds</div>

        <Block title="backend" health={overall} raw={ready.data}>
          {ready.isPending ? <Skeleton lines={3} /> : ready.isError ? (
            <div className="row">{describeError(ready.error).message} <Button variant="secondary" size="sm" onClick={() => ready.refetch()}>retry</Button></div>
          ) : (
            <dl className="kv">
              {ready.data.components.map((c) => (
                <div key={c.name} style={{ display: "contents" }}>
                  <dt>{c.name}</dt>
                  <dd><StatusText health={componentHealth(c.status)}>{c.status}</StatusText>{c.error ? ` — ${c.error}` : ""}
                    {Object.entries(c.detail).length ? ` · ${Object.entries(c.detail).map(([k, v]) => `${k}=${String(v)}`).join(" ")}` : ""}</dd>
                </div>
              ))}
            </dl>
          )}
        </Block>

        <Block title="configuration (no secrets)" health={config.isError ? "unavailable" : config.isPending ? "unknown" : "healthy"} raw={config.data}>
          {config.isPending ? <Skeleton lines={4} /> : config.isError ? describeError(config.error).message : (
            <dl className="kv">
              {Object.entries(config.data).map(([k, v]) => (
                <div key={k} style={{ display: "contents" }}><dt>{k}</dt><dd>{Array.isArray(v) ? v.join(", ") : String(v)}</dd></div>
              ))}
            </dl>
          )}
        </Block>

        <Block title="qdrant" health={qdrant.isError ? "unavailable" : qdrant.isPending ? "unknown" : qdrant.data.reachable && qdrant.data.collection_exists ? "healthy" : "degraded"} raw={qdrant.data}>
          {qdrant.isPending ? <Skeleton lines={4} /> : qdrant.isError ? describeError(qdrant.error).message : (
            <dl className="kv">
              <dt>mode</dt><dd>{qdrant.data.mode} · {qdrant.data.target}</dd>
              <dt>collection</dt><dd>{qdrant.data.collection} ({qdrant.data.collection_exists ? "exists" : "missing"}) · {qdrant.data.points ?? "–"} points</dd>
              <dt>vectors</dt><dd>{qdrant.data.vector_dimension ?? "–"}d / expected {qdrant.data.expected_dimension} · {qdrant.data.distance ?? "–"} · sparse {String(qdrant.data.sparse_enabled)}</dd>
              <dt>probe</dt><dd>{qdrant.data.test_query_ok == null ? "–" : qdrant.data.test_query_ok ? "ok" : "failed"} · {formatMs(qdrant.data.latency_ms)}</dd>
              {qdrant.data.error ? <><dt>error</dt><dd>{qdrant.data.error}</dd></> : null}
            </dl>
          )}
        </Block>

        <Block title="embeddings" health={embedding.isError ? "unavailable" : embedding.isPending ? "unknown" : embedding.data.ok ? "healthy" : "degraded"} raw={embedding.data}>
          {embedding.isPending ? <Skeleton lines={3} /> : embedding.isError ? describeError(embedding.error).message : (
            <dl className="kv">
              <dt>model</dt><dd>{embedding.data.model} · loaded {String(embedding.data.loaded)}</dd>
              <dt>vector</dt><dd>{embedding.data.dimension ?? "–"}d / expected {embedding.data.expected_dimension} · normalized {String(embedding.data.normalized ?? "–")}</dd>
              <dt>latency</dt><dd>{formatMs(embedding.data.latency_ms)}</dd>
              {embedding.data.error ? <><dt>error</dt><dd>{embedding.data.error}</dd></> : null}
            </dl>
          )}
        </Block>

        <Block title="llm (one real call)" health={llm.isError ? "unavailable" : llm.data ? (llm.data.ok ? "healthy" : "degraded") : "unknown"} raw={llm.data}>
          <div className="stack">
            <div><Button variant="secondary" size="sm" onClick={() => llm.mutate()} loading={llm.isPending}>run check</Button></div>
            {llm.isError ? <span>{describeError(llm.error).message}</span> : null}
            {llm.data ? (
              <dl className="kv">
                <dt>providers</dt><dd>{llm.data.configured_providers.join(", ") || "none"}</dd>
                <dt>used</dt><dd>{llm.data.provider ?? "–"} · {llm.data.model ?? "–"} · {formatMs(llm.data.latency_ms)}</dd>
                <dt>reply</dt><dd>{llm.data.response_preview ?? "–"}</dd>
                {llm.data.error ? <><dt>error</dt><dd>{llm.data.error}</dd></> : null}
              </dl>
            ) : null}
          </div>
        </Block>

        <Block title="routing (no retrieval, no llm)" health={route.isError ? "unavailable" : route.data ? "healthy" : "unknown"} raw={route.data}>
          <form className="stack" onSubmit={(e) => { e.preventDefault(); route.mutate(routeQuery); }}>
            <Input label="query" value={routeQuery} onChange={(e) => setRouteQuery(e.target.value)} />
            <div><Button variant="secondary" size="sm" type="submit" loading={route.isPending} disabled={!routeQuery.trim()}>inspect route</Button></div>
          </form>
          {route.isError ? <span>{describeError(route.error).message}</span> : null}
          {route.data ? (
            <dl className="kv" style={{ marginTop: 10 }}>
              <dt>intent</dt><dd>{route.data.intent.intent}</dd>
              <dt>safety</dt><dd>{route.data.safety.decision}{route.data.would_refuse ? " (refuse)" : ""}</dd>
              <dt>complexity</dt><dd>{route.data.complexity?.complexity ?? "–"} → {route.data.retrieval_profile ?? "–"} / {route.data.route ?? "–"}</dd>
              {route.data.entities.length ? <><dt>entities</dt><dd>{route.data.entities.join(", ")}</dd></> : null}
              {route.data.complexity?.reasons.length ? <><dt>reasons</dt><dd>{route.data.complexity.reasons.join("; ")}</dd></> : null}
              {route.data.subqueries.length ? <><dt>sub-queries</dt><dd>{route.data.subqueries.map((s) => `${s.query} (${s.purpose})`).join(" | ")}</dd></> : null}
            </dl>
          ) : null}
        </Block>
      </div>
    </div>
  );
}
