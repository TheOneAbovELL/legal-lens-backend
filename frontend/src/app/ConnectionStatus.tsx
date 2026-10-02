import { useQuery } from "@tanstack/react-query";
import { RefreshCw, WifiOff } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { systemApi } from "@/lib/api";

/** Polls /health (liveness) and /ready (dependencies). */
export function useBackendStatus() {
  const health = useQuery({ queryKey: ["health"], queryFn: ({ signal }) => systemApi.health(signal), retry: 1, retryDelay: 400, refetchInterval: 20_000, refetchOnWindowFocus: true });
  const ready = useQuery({ queryKey: ["ready"], queryFn: ({ signal }) => systemApi.ready(signal), retry: false, refetchInterval: 30_000, enabled: health.isSuccess });
  const offline = health.isError;
  const notReady = ready.isSuccess ? ready.data.status !== "ready" : ready.isError;
  const failed = ready.isSuccess ? ready.data.failed : [];
  const checks = ready.isSuccess ? ready.data.checks : {};
  return { offline, notReady, failed, checks, loading: health.isPending, refetch: () => { void health.refetch(); void ready.refetch(); } };
}

const NAMES: Record<string, string> = {
  qdrant: "document index", embedding: "embedding model", llm: "answer generation", database: "conversation history",
};

/** One quiet line under the top bar; disappears by itself once the backend is healthy again. */
export function ConnectionLine() {
  const status = useBackendStatus();
  if (status.loading) return null;
  if (status.offline) {
    return (
      <div className="netline netline--danger" role="status">
        <WifiOff size={13} aria-hidden="true" />
        <span>Connection interrupted — reconnecting…</span>
        <Button variant="ghost" size="sm" icon={<RefreshCw />} onClick={status.refetch}>Retry now</Button>
      </div>
    );
  }
  if (status.notReady) {
    const parts = status.failed.map((n) => NAMES[n] ?? n);
    const llmDown = status.checks.llm && status.checks.llm !== "configured";
    return (
      <div className="netline" role="status">
        <span>
          {parts.length ? `Limited mode: ${parts.join(", ")} unavailable.` : "Limited mode: some services are starting."}
          {llmDown ? " Search works; answers cannot be generated." : ""}
        </span>
        <Button variant="ghost" size="sm" icon={<RefreshCw />} onClick={status.refetch}>Re-check</Button>
      </div>
    );
  }
  return null;
}
