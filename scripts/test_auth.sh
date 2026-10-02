#!/usr/bin/env bash
# Signup (throwaway user unless LL_USERNAME/LL_PASSWORD given) -> login -> /me.
# Usage: ./scripts/test_auth.sh        (prints an export line for LEGAL_LENS_TOKEN)
set -euo pipefail
source "$(dirname "$0")/_common.sh"
LL_USERNAME=${LL_USERNAME:-curl_$RANDOM$RANDOM}
LL_PASSWORD=${LL_PASSWORD:-Curl-test-$RANDOM-pass}
echo "POST /api/v1/auth/signup ($LL_USERNAME)"
curl -sS -o /dev/null -w "HTTP %{http_code}\n" -X POST "$BASE_URL/api/v1/auth/signup" \
  -H "Content-Type: application/json" -d "{\"username\":\"$LL_USERNAME\",\"password\":\"$LL_PASSWORD\"}"
echo "POST /api/v1/auth/login"
TOKEN=$(curl -sS -X POST "$BASE_URL/api/v1/auth/login" -H "Content-Type: application/json" \
  -d "{\"username\":\"$LL_USERNAME\",\"password\":\"$LL_PASSWORD\"}" | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "token received (${#TOKEN} chars)"
echo "GET /api/v1/auth/me"; curl -sS -H "Authorization: Bearer $TOKEN" "$BASE_URL/api/v1/auth/me" | pretty
echo "wrong password ->"; curl -sS -o /dev/null -w "HTTP %{http_code}\n" -X POST "$BASE_URL/api/v1/auth/login" \
  -H "Content-Type: application/json" -d "{\"username\":\"$LL_USERNAME\",\"password\":\"wrong-pass-1\"}"
echo; echo "export LEGAL_LENS_TOKEN=$TOKEN"
