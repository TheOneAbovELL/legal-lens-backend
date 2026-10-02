#!/usr/bin/env bash
# Liveness + root. Usage: ./scripts/test_health.sh
set -euo pipefail
source "$(dirname "$0")/_common.sh"
echo "GET $BASE_URL/";        curl -sS "$BASE_URL/" | pretty
echo "GET $BASE_URL/health";  curl -sS -w "\nHTTP %{http_code}\n" "$BASE_URL/health"
