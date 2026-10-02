/**
 * Frontend ⇄ backend contract: every endpoint the client calls must exist in the exported OpenAPI
 * document (python scripts/export_openapi.py) and every response field the UI reads must be declared.
 */
import { describe, expect, it } from "vitest";
import spec from "../contract/openapi.json";
import { CLIENT_PATHS } from "@/lib/api";

type Schema = { properties?: Record<string, unknown>; required?: string[]; allOf?: Schema[]; $ref?: string };
const schemas = (spec as { components: { schemas: Record<string, Schema> } }).components.schemas;
const paths = (spec as { paths: Record<string, Record<string, unknown>> }).paths;

function props(name: string): string[] {
  const schema = schemas[name];
  if (!schema) throw new Error(`schema ${name} missing from OpenAPI`);
  return Object.keys(schema.properties ?? {});
}

describe("API contract", () => {
  it("exposes every path and method the client calls", () => {
    for (const { method, path } of CLIENT_PATHS) {
      expect(paths[path], `${method.toUpperCase()} ${path} missing`).toBeDefined();
      expect(paths[path]?.[method], `${method.toUpperCase()} ${path} missing`).toBeDefined();
    }
  });

  it("chat response carries the fields the UI reads", () => {
    const fields = props("ChatResponse");
    for (const f of ["answer", "request_id", "conversation_id", "message_id", "persisted", "status", "analysis", "refused",
      "citations", "bns_alerts", "warnings", "disclaimer", "metadata"]) {
      expect(fields, f).toContain(f);
    }
    expect(props("QueryAnalysis")).toEqual(expect.arrayContaining(["intent", "complexity", "retrieval_profile", "decomposition_needed", "provisions"]));
    expect(props("Citation")).toEqual(expect.arrayContaining(["citation_id", "document_id", "chunk_id", "title", "section", "page", "excerpt", "source", "score"]));
    expect(props("BnsAlert")).toEqual(expect.arrayContaining(["old", "new", "effective", "mapping_type", "verification_status", "provenance"]));
  });

  it("conversation and search responses match the UI types", () => {
    expect(props("ConversationDetail")).toEqual(expect.arrayContaining(["id", "title", "updated_at", "messages"]));
    expect(props("MessageOut")).toEqual(expect.arrayContaining(["id", "role", "content", "status", "created_at", "citations"]));
    expect(props("EvidenceOut")).toEqual(expect.arrayContaining(["citation_id", "document_id", "excerpt", "section"]));
    expect(props("SearchResponse")).toEqual(expect.arrayContaining(["results", "total", "processing_time_ms", "retrieval_metadata", "warnings"]));
    expect(props("SearchResult")).toEqual(expect.arrayContaining(["chunk_id", "snippet", "content", "relevance_score", "retrieval_sources", "citation", "metadata"]));
    expect(props("ReadinessResponse")).toEqual(expect.arrayContaining(["status", "checks", "failed", "components"]));
    expect(props("ErrorResponse")).toContain("error");
    expect(props("ErrorDetail")).toEqual(expect.arrayContaining(["code", "message", "request_id"]));
  });

  it("documents bearer auth and the SSE stream", () => {
    const security = (spec as { components: { securitySchemes?: Record<string, { type: string; scheme?: string }> } }).components.securitySchemes ?? {};
    expect(Object.values(security).some((s) => s.type === "http" && s.scheme === "bearer")).toBe(true);
    const stream = paths["/api/v1/chat/stream"]?.post as { responses: Record<string, { content?: Record<string, unknown> }> };
    expect(stream.responses["200"]?.content?.["text/event-stream"]).toBeDefined();
  });
});
