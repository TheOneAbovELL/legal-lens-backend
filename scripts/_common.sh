# Shared settings for the curl test scripts. Override: BASE_URL=http://host:port ./scripts/test_x.sh
BASE_URL=${BASE_URL:-http://127.0.0.1:8000}
# Optional bearer token (e.g. from test_auth.sh) when AUTH_REQUIRED=true.
AUTH_HEADER=()
if [ -n "${LEGAL_LENS_TOKEN:-}" ]; then AUTH_HEADER=(-H "Authorization: Bearer ${LEGAL_LENS_TOKEN}"); fi
# Pretty-print JSON with the project's Python if available.
pretty() { python -m json.tool 2>/dev/null || cat; }
