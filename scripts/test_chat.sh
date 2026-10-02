#!/usr/bin/env bash
# Chat (JSON). Usage: ./scripts/test_chat.sh ["question"]
set -euo pipefail
source "$(dirname "$0")/_common.sh"
QUERY=${1:-What is the punishment for cheating under Section 420 IPC?}
echo "POST /api/v1/chat  \"$QUERY\""
curl -sS -X POST "$BASE_URL/api/v1/chat" "${AUTH_HEADER[@]}" -H "Content-Type: application/json" \
  -d "{\"query\":\"$QUERY\"}" | python -c "
import sys, json
d = json.load(sys.stdin)
if 'error' in d: print(d); sys.exit(1)
m = d['metadata']
print('route:', m['route'], '| complexity:', (m['complexity'] or {}).get('complexity'), '| profile:', m['retrieval_profile'], '| model:', m['model'])
print('answer:', d['answer'])
for c in d['citations']: print('  ', c['citation_id'], c['title'], c.get('section'))
for a in d['bns_alerts']: print('  alert:', a['old'], '->', a['new'])
print('warnings:', d['warnings'])"
