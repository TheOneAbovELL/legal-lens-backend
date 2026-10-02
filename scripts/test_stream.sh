#!/usr/bin/env bash
# Raw SSE stream (events print as they arrive). Usage: ./scripts/test_stream.sh ["question"]
# For a formatted view use: python scripts/test_stream.py "question"
set -euo pipefail
source "$(dirname "$0")/_common.sh"
QUERY=${1:-Explain Article 21 of the Constitution}
curl -sS -N -X POST "$BASE_URL/api/v1/chat/stream" "${AUTH_HEADER[@]}" -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" -d "{\"query\":\"$QUERY\"}"
