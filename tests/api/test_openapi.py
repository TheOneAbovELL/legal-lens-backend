"""OpenAPI quality: every endpoint documented, typed schemas, bearer security, docs pages served."""

from __future__ import annotations

import httpx

EXPECTED = {
    ("get", "/"), ("get", "/health"), ("get", "/ready"),
    ("post", "/api/v1/auth/signup"), ("post", "/api/v1/auth/login"), ("get", "/api/v1/auth/me"),
    ("post", "/api/v1/chat"), ("post", "/api/v1/chat/stream"), ("post", "/api/v1/query/stream"),
    ("post", "/api/v1/search"), ("get", "/api/v1/search"), ("get", "/api/v1/statute/map"),
    ("get", "/api/v1/diagnostics/config"), ("get", "/api/v1/diagnostics/qdrant"),
    ("get", "/api/v1/diagnostics/embedding"), ("post", "/api/v1/diagnostics/llm"), ("post", "/api/v1/diagnostics/route"),
}


async def test_openapi_lists_every_endpoint_with_docs(client: httpx.AsyncClient) -> None:
    spec = (await client.get("/openapi.json")).json()
    assert spec["openapi"].startswith("3.")
    found = {(method, path) for path, ops in spec["paths"].items() for method in ops}
    assert EXPECTED <= found
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            assert op.get("summary"), f"{method} {path} has no summary"
            assert op.get("tags"), f"{method} {path} has no tag"
    assert {t["name"] for t in spec["tags"]} >= {"Health", "Authentication", "Chat", "Search", "Statutes", "Diagnostics"}


async def test_bearer_security_scheme_for_swagger_authorize(client: httpx.AsyncClient) -> None:
    spec = (await client.get("/openapi.json")).json()
    schemes = spec["components"]["securitySchemes"]
    assert any(s["type"] == "http" and s["scheme"] == "bearer" for s in schemes.values())
    assert spec["paths"]["/api/v1/auth/me"]["get"].get("security")
    assert spec["paths"]["/api/v1/chat"]["post"].get("security")


async def test_schemas_are_typed_not_free_form(client: httpx.AsyncClient) -> None:
    spec = (await client.get("/openapi.json")).json()
    schemas = spec["components"]["schemas"]
    for name in ("ChatRequest", "ChatResponse", "SearchRequest", "SearchResponse", "SearchResult", "Citation",
                 "ChunkMetadata", "ReadinessResponse", "RetrievalDiagnostics", "TokenResponse", "ErrorResponse"):
        assert name in schemas, name
    assert schemas["SearchResult"]["properties"]["metadata"]["$ref"].endswith("/ChunkMetadata")
    chat_ok = spec["paths"]["/api/v1/chat"]["post"]["responses"]
    assert chat_ok["422"]["content"]["application/json"]["schema"]["$ref"].endswith("/ErrorResponse")
    examples = spec["paths"]["/api/v1/chat"]["post"]["requestBody"]["content"]["application/json"]["examples"]
    assert {"simple", "moderate", "complex", "refusal"} <= set(examples)


async def test_docs_and_redoc_pages(client: httpx.AsyncClient) -> None:
    docs = await client.get("/docs")
    assert docs.status_code == 200 and "swagger-ui" in docs.text
    redoc = await client.get("/redoc")
    assert redoc.status_code == 200 and "redoc" in redoc.text.lower()
