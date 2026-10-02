# Query understanding and routing

All deterministic steps below run in well under a millisecond and never call an LLM.

1. **Normalization** (`app/rag/query/normalizer.py`) — NFKC, `u/s`→`under Section`, `r/w`→`read with`,
   `sec.`→`Section`.
2. **Entities** (`entities.py`) — sections with acts in any common form (`Section 420 IPC`,
   `s. 304A of the Indian Penal Code`, `IPC 302`, `420 IPC`, `Sections 299 and 300 … IPC`),
   articles, acts and case citations (`X v. Y`, `AIR 1978 SC 597`, `(2017) 10 SCC 1`).
3. **MEM-0 follow-ups** (`app/services/session_memory.py`) — with a `session_id`, a follow-up with no
   provision of its own ("what is its punishment?") inherits the previous turn's provisions.
   Bounded (turns, sessions, TTL), per-process, namespaced per user; never persisted.
4. **Intent** (`intent.py`) — statute lookup, provision mapping, case law, procedural, document
   analysis, general legal, small talk.
5. **Safety** (`app/services/safety.py`) — see below; a refusal ends the graph.
6. **Complexity** (`complexity.py`) — weighted features, not a keyword switch: extra provisions,
   multiple acts, case citations, number of questions, comparison, reasoning (why/how/analyse),
   temporal/version cues, cross-references (`read with`), conflicting authority, evidence demands,
   multi-part markers, log-scaled length and intent. Score ≥ 1.0 → MODERATE, ≥ 2.6 → COMPLEX.
   The result includes confidence, ranked reasons, features, entities, and decomposition /
   reranking / multi-hop / evidence-level flags. Weights and thresholds load from
   `COMPLEXITY_CONFIG_PATH` (JSON). Measured accuracy on the 18 labelled fixture queries: **66.7%**
   (weights intentionally not tuned on such a small set).
7. **Profile selection** (`app/rag/profiles.py`, `config/retrieval_profiles.json`) —
   SIMPLE→FAST, MODERATE→BALANCED, COMPLEX→DEEP, with intent minimums (mapping/case law →
   BALANCED, document analysis → DEEP), unavailable sources removed, chunk profiles from rules or
   (with `ADAPTIVE_SELECTION_MODE=data_driven`) from `evaluation/results/latest.json`, and a fallback
   to all indexed representations when the chosen one is not indexed. Requests may force a profile.

| Profile | top_k | sources | reranker | expansion | decomposition |
|---|---|---|---|---|---|
| FAST | 6 | dense, sparse, metadata | lexical | – | – |
| BALANCED | 10 | + graph | lexical (measured; see RAG.md) | ✓ | – |
| DEEP | 16 | + graph | lexical (measured; see RAG.md) | ✓ | ✓ |

## Paths

* **SIMPLE** — the (follow-up-resolved) query is the only sub-query.
* **MODERATE** — `QueryExpander`: original + one look-up per named provision when several are compared
  (otherwise a statute-name-expanded variant) + mapped counterpart provisions (e.g. IPC 420 →
  `Bharatiya Nyaya Sanhita, 2023 Section 318(4) …`), max 4.
* **COMPLEX** — `QueryDecomposer`: LLM plan (JSON, timeout, token budget, schema validation,
  authoritative act glossary in the prompt) merged with entity-grounded rule look-ups. Grounded
  look-ups outrank LLM proposals under the cap (`DECOMPOSITION_MAX_SUBQUERIES`), near-duplicates
  (Jaccard ≥ 0.8) and fragments < 3 tokens are dropped, the original query is always kept, and it is
  single-level (no recursion). Any LLM failure → rule-based plan (`rule_fallback`). In search mode the
  LLM is not used.

## Safety guard

Redirects (no retrieval, no LLM): outcome prediction, personal legal advice, litigation strategy,
guilt determination (system design guardrails), facilitation of offences (forging documents,
fabricating/tampering with evidence, threatening witnesses…), and prompt-injection attempts.
Informational questions on the same topics are allowed. Personal situations and non-Indian
jurisdictions are allowed with caution notes. `evaluation/safety_questions.json` (12 negative +
8 normal questions) passes 20/20 (`python scripts/evaluate_safety.py`).
