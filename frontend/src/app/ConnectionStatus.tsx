import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Card";
import { systemApi } from "@/lib/api";

/** Polls /health (liveness) and /ready (dependencies) and renders the degraded banner. */
export function useBackendStatus() {
  const health = useQuery({ queryKey: ["health"], queryFn: ({ signal }) => systemApi.health(signal), retry: 1, retryDelay: 400, refetchInterval: 20_000, refetchOnWindowFocus: true });
  const ready = useQuery({ queryKey: ["ready"], queryFn: ({ signal }) => systemApi.ready(signal), retry: false, refetchInterval: 30_000, enabled: health.isSuccess });
  const offline = health.isError;
  const notReady = ready.isSuccess ? ready.data.status !== "ready" : ready.isError;
  const failed = ready.isSuccess ? ready.data.failed : [];
  const checks = ready.isSuccess ? ready.data.checks : {};
  return { offline, notReady, failed, checks, loading: health.isPending, refetch: () => { void health.refetch(); void ready.refetch(); } };
}

export function ConnectionBadge() {
  const status = useBackendStatus();
  if (status.loading) return <Badge title="Checking backend">…</Badge>;
  if (status.offline) return <Badge tone="danger" title="Backend unreachable">offline</Badge>;
  if (status.notReady) return <Badge tone="warning" title={`Degraded: ${status.failed.join(", ") || "dependencies not ready"}`}>degraded</Badge>;
  return <Badge tone="success" title="Backend ready">online</Badge>;
}

export function ConnectionBanner() {
  const status = useBackendStatus();
  if (status.loading) return null;
  if (status.offline) {
    return (
      <div style={{ padding: "8px 16px" }}>
        <Alert tone="danger" title="Legal Lens backend is currently unavailable." action={<Button size="sm" onClick={status.refetch}>Retry</Button>}>
          Check the server status, then retry.
        </Alert>
      </div>
    );
  }
  if (status.notReady) {
    const parts = status.failed.map((name) => {
      if (name === "qdrant") return "the document index";
      if (name === "embedding") return "the embedding model";
      if (name === "llm") return "answer generation (no LLM credentials)";
      if (name === "database") return "conversation history (database)";
      return name;
    });
    return (
      <div style={{ padding: "8px 16px" }}>
        <Alert tone="warning" title="Running in degraded mode" action={<Button size="sm" onClick={status.refetch}>Re-check</Button>}>
          {parts.length ? `Unavailable: ${parts.join(", ")}.` : "Some dependencies are not ready."}{" "}
          {status.checks.llm && status.checks.llm !== "configured" ? "Search still works; chat answers cannot be generated." : ""}
          {status.checks.qdrant && status.checks.qdrant !== "ok" ? " Search and chat need the index." : ""}
          {status.checks.database && status.checks.database !== "ok" ? " Chat may continue statelessly; history is unavailable." : ""}
        </Alert>
      </div>
    );
  }
  return null;
}
