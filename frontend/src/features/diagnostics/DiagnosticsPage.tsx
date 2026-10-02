import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate } from "react-router-dom";
import { appConfig } from "@/app/config";
import { Badge, ComplexityBadge, type BadgeTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Alert, Card, Skeleton } from "@/components/ui/Card";
import { Input } from "@/components/ui/Field";
import { diagnosticsApi, systemApi } from "@/lib/api";
import { describeError } from "@/lib/utils/errors";
import { formatMs } from "@/lib/utils/format";

function tone(status: string): BadgeTone {
  if (status === "ok" || status === "configured") return "success";
  if (status === "disabled" || status === "loading") return "neutral";
  return "danger";
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <Card><h2 style={{ fontSize: 15, margin: "0 0 10px" }}>{title}</h2>{children}</Card>;
}

/** Development-only. Shows backend dependency state; never shows keys, secrets or prompts. */
export function DiagnosticsPage() {
  const ready = useQuery({ queryKey: ["ready"], queryFn: ({ signal }) => systemApi.ready(signal), retry: false });
  const config = useQuery({ queryKey: ["diag", "config"], queryFn: ({ signal }) => diagnosticsApi.config(signal), retry: false });
  const qdrant = useQuery({ queryKey: ["diag", "qdrant"], queryFn: ({ signal }) => diagnosticsApi.qdrant(signal), retry: false });
  const embedding = useQuery({ queryKey: ["diag", "embedding"], queryFn: ({ signal }) => diagnosticsApi.embedding(signal), retry: false });
  const llm = useMutation({ mutationFn: () => diagnosticsApi.llm() });
  const [routeQuery, setRouteQuery] = useState("Compare IPC 420 and BNS 318.");
  const route = useMutation({ mutationFn: (q: string) => diagnosticsApi.route(q) });

  if (!appConfig.diagnosticsEnabled) return <Navigate to="/app" replace />;

  return (
    <div className="page">
      <div className="page__inner">
        <h1>Diagnostics</h1>
        <p className="page__lead">Development view of backend dependencies. Disabled in production builds and when the backend runs with diagnostics off.</p>

        <Section title="Readiness">
          {ready.isPending ? <Skeleton lines={3} /> : ready.isError ? (
            <Alert tone="danger" action={<Button size="sm" onClick={() => ready.refetch()}>Retry</Button>}>{describeError(ready.error).message}</Alert>
          ) : (
            <div className="stack">
              <div className="row">
                <Badge tone={ready.data.status === "ready" ? "success" : "danger"}>{ready.data.status}</Badge>
                {ready.data.components.map((c) => (
                  <Badge key={c.name} tone={tone(c.status)} title={c.error ?? JSON.stringify(c.detail)}>{c.name}: {c.status}</Badge>
                ))}
              </div>
              <dl className="kv">
                {ready.data.components.flatMap((c) => Object.entries(c.detail).map(([k, v]) => (
                  <div key={`${c.name}.${k}`} style={{ display: "contents" }}><dt>{c.name}.{k}</dt><dd>{String(v)}</dd></div>
                )))}
              </dl>
            </div>
          )}
        </Section>

        <div className="grid-2">
          <Section title="Configuration (no secrets)">
            {config.isPending ? <Skeleton lines={4} /> : config.isError ? (
              <Alert tone="warning">{describeError(config.error).message}</Alert>
            ) : (
              <dl className="kv">
                {Object.entries(config.data).map(([k, v]) => (
                  <div key={k} style={{ display: "contents" }}><dt>{k}</dt><dd>{Array.isArray(v) ? v.join(", ") : String(v)}</dd></div>
                ))}
              </dl>
            )}
          </Section>
          <Section title="Qdrant">
            {qdrant.isPending ? <Skeleton lines={4} /> : qdrant.isError ? (
              <Alert tone="warning">{describeError(qdrant.error).message}</Alert>
            ) : (
              <dl className="kv">
                <dt>reachable</dt><dd>{String(qdrant.data.reachable)}</dd>
                <dt>mode / target</dt><dd>{qdrant.data.mode} · {qdrant.data.target}</dd>
                <dt>collection</dt><dd>{qdrant.data.collection} ({qdrant.data.collection_exists ? "exists" : "missing"})</dd>
                <dt>points</dt><dd>{qdrant.data.points ?? "–"}</dd>
                <dt>dimension</dt><dd>{qdrant.data.vector_dimension ?? "–"} / expected {qdrant.data.expected_dimension}</dd>
                <dt>distance</dt><dd>{qdrant.data.distance ?? "–"}</dd>
                <dt>sparse</dt><dd>{String(qdrant.data.sparse_enabled)}</dd>
                <dt>probe query</dt><dd>{qdrant.data.test_query_ok === null || qdrant.data.test_query_ok === undefined ? "–" : qdrant.data.test_query_ok ? "ok" : "failed"}</dd>
                <dt>latency</dt><dd>{formatMs(qdrant.data.latency_ms)}</dd>
                {qdrant.data.error ? <><dt>error</dt><dd>{qdrant.data.error}</dd></> : null}
              </dl>
            )}
          </Section>
          <Section title="Embedding model">
            {embedding.isPending ? <Skeleton lines={4} /> : embedding.isError ? (
              <Alert tone="warning">{describeError(embedding.error).message}</Alert>
            ) : (
              <dl className="kv">
                <dt>ok</dt><dd>{String(embedding.data.ok)}</dd>
                <dt>model</dt><dd>{embedding.data.model}</dd>
                <dt>loaded</dt><dd>{String(embedding.data.loaded)}</dd>
                <dt>dimension</dt><dd>{embedding.data.dimension ?? "–"} / expected {embedding.data.expected_dimension}</dd>
                <dt>normalized</dt><dd>{String(embedding.data.normalized ?? "–")}</dd>
                <dt>latency</dt><dd>{formatMs(embedding.data.latency_ms)}</dd>
                {embedding.data.error ? <><dt>error</dt><dd>{embedding.data.error}</dd></> : null}
              </dl>
            )}
          </Section>
          <Section title="LLM provider (one small real call)">
            <div className="stack">
              <div><Button size="sm" onClick={() => llm.mutate()} loading={llm.isPending}>Run check</Button></div>
              {llm.isError ? <Alert tone="warning">{describeError(llm.error).message}</Alert> : null}
              {llm.data ? (
                <dl className="kv">
                  <dt>ok</dt><dd>{String(llm.data.ok)}</dd>
                  <dt>providers</dt><dd>{llm.data.configured_providers.join(", ") || "none"}</dd>
                  <dt>provider / model</dt><dd>{llm.data.provider ?? "–"} · {llm.data.model ?? "–"}</dd>
                  <dt>reply</dt><dd>{llm.data.response_preview ?? "–"}</dd>
                  <dt>latency</dt><dd>{formatMs(llm.data.latency_ms)}</dd>
                  {llm.data.error ? <><dt>error</dt><dd>{llm.data.error}</dd></> : null}
                </dl>
              ) : null}
            </div>
          </Section>
        </div>

        <Section title="Routing (no retrieval, no LLM)">
          <form className="stack" onSubmit={(e) => { e.preventDefault(); route.mutate(routeQuery); }}>
            <Input label="Query" value={routeQuery} onChange={(e) => setRouteQuery(e.target.value)} />
            <div><Button size="sm" type="submit" loading={route.isPending} disabled={!routeQuery.trim()}>Inspect route</Button></div>
          </form>
          {route.isError ? <Alert tone="warning">{describeError(route.error).message}</Alert> : null}
          {route.data ? (
            <div className="stack" style={{ marginTop: 12 }}>
              <div className="row">
                <Badge>intent: {route.data.intent.intent}</Badge>
                <Badge tone={route.data.would_refuse ? "danger" : "success"}>safety: {route.data.safety.decision}</Badge>
                <ComplexityBadge complexity={route.data.complexity?.complexity} />
                {route.data.retrieval_profile ? <Badge>{route.data.retrieval_profile}</Badge> : null}
                {route.data.route ? <Badge>route: {route.data.route}</Badge> : null}
              </div>
              {route.data.entities.length ? <div style={{ fontSize: 13 }}>Entities: {route.data.entities.join(", ")}</div> : null}
              {route.data.complexity?.reasons.length ? <div style={{ fontSize: 13 }}>Reasons: {route.data.complexity.reasons.join("; ")}</div> : null}
              {route.data.subqueries.length ? (
                <ol style={{ margin: 0, paddingLeft: 20, fontSize: 14 }}>
                  {route.data.subqueries.map((s) => <li key={s.subquery_id}>{s.query} <span style={{ color: "var(--text-faint)" }}>({s.purpose})</span></li>)}
                </ol>
              ) : null}
            </div>
          ) : null}
        </Section>
      </div>
    </div>
  );
}
