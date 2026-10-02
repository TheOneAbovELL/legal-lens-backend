#!/usr/bin/env bash
# Hybrid search with stage diagnostics (no LLM). Usage: ./scripts/test_search.sh ["query"] [top_k]
set -euo pipefail
source "$(dirname "$0")/_common.sh"
QUERY=${1:-Section 302 IPC}; TOP_K=${2:-5}
echo "POST /api/v1/search  query=\"$QUERY\" top_k=$TOP_K"
curl -sS -X POST "$BASE_URL/api/v1/search" "${AUTH_HEADER[@]}" -H "Content-Type: application/json" \
  -d "{\"query\":\"$QUERY\",\"top_k\":$TOP_K}" | python -c "
import sys, json
d = json.load(sys.stdin)
if 'error' in d: print(d); sys.exit(1)
g = d['diagnostics'] or {}
print('profile:', d['retrieval_metadata']['strategy'], '| complexity:', d['retrieval_metadata']['complexity'], '| mode:', g.get('retrieval_mode'))
for name, s in (g.get('sources') or {}).items(): print(f'  {name:<9} executed={s[\"executed\"]} hits={s[\"hits\"]}')
print('  fusion', g.get('fusion', {}).get('count'), '| reranking', g.get('reranking', {}).get('method'), g.get('reranking', {}).get('count'))
for r in d['results']: print(f'  {r[\"relevance_score\"]:.3f} {r[\"metadata\"][\"act\"]} {r[\"metadata\"][\"section\"]} {r[\"retrieval_sources\"]} {r[\"snippet\"][:70]}')
print('latency ms:', d['processing_time_ms'])"
