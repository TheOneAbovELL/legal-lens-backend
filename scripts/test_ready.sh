#!/usr/bin/env bash
# Readiness (HTTP 200 ready / 503 not ready) + component diagnostics. Usage: ./scripts/test_ready.sh
set -uo pipefail
source "$(dirname "$0")/_common.sh"
echo "GET $BASE_URL/ready"
curl -sS -w "\nHTTP %{http_code}\n" "$BASE_URL/ready"
echo; echo "GET $BASE_URL/api/v1/diagnostics/qdrant"
curl -sS "${AUTH_HEADER[@]}" "$BASE_URL/api/v1/diagnostics/qdrant" | pretty
