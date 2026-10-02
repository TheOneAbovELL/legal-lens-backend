# RAG pipeline

## Retrieval

`HybridRetriever` (`app/rag/retrieval/hybrid.py`) runs the profile's sources concurrently for every
sub-query:

| Source | Implementation | Notes |
|---|---|---|
| dense | BGE-M3 query embedding → Qdrant `dense` vector | normalized, query-cache (LRU) |
| sparse | BM25-style TF weights, IDF applied by Qdrant (`Modifier.IDF`) | legal abbreviation normalization (`sec.`→`section`) |
| metadata | exact `act` + `section` payload filter for provisions named in the query | run once per request |
| graph | Neo4j `Statute` nodes for named provisions | optional, circuit-breaker protected |

Fusion is weighted reciprocal-rank fusion (`k=60`) scaled by sub-query priority; duplicates are
merged by chunk ID and content hash. Each candidate keeps per-source scores/ranks and its **best
rank per sub-query**. A failing optional source is recorded as a warning; if every source fails a
`RetrievalError` is raised. Embedding failures raise `EmbeddingError` — no zero vectors.

## Reranking

`RerankerSet` dispatches to `none`, `lexical` (fused score + query-term coverage + exact-provision
bonus) or `cross_encoder` (`RERANKER_MODEL`, sigmoid-normalized). **All profiles currently use
`lexical`**: on the labelled set it beat the ms-marco cross-encoder on every metric (recall@5 1.000 vs
0.982, nDCG@5 0.946 vs 0.912) at ~1/4 of the latency (`scripts/evaluate_rag.py --reranker ...`). Each candidate is scored against
the sub-query it ranked best for, so decomposition coverage is not destroyed by scoring everything
against the long original question. If the cross-encoder fails, lexical reranking is used and a
warning is returned.

Known limitation: the default cross-encoder (`ms-marco-MiniLM-L-6-v2`) is trained on English web QA
and over-scores short header-like sub-queries on legal text. A legal or multilingual reranker
(e.g. `BAAI/bge-reranker-v2-m3`) is a drop-in change via `RERANKER_MODEL`, but should be evaluated first.

## Context fusion

`ContextBuilder` (`app/rag/fusion.py`):

0. **pinning** — exact matches on provisions the user named (metadata/graph retrievers) enter first
   and bypass the relevance floor; no reranker score can drop them;
1. relevance floor **per sub-query** (`MIN_RELATIVE_RELEVANCE` × best score of that sub-query);
2. coverage phase — round-robin over sub-queries by priority (up to `max_evidence_per_subquery`);
3. global fill by score;
4. dedup — containment, near-duplicate Jaccard ≥ 0.85, child-of-selected-parent;
   parent expansion replaces selected children by their parent when it fits;
5. budgets — `max_context_tokens`, `max_chunks`, `max_chunks_per_document`; items that do not fit
   are **skipped whole, never truncated**;
6. grouping by document unit (e.g. one section), document order inside groups, citation IDs `C1..Cn`.

Profile budgets are capped by the global `MAX_CONTEXT_TOKENS` / `MAX_CHUNKS` ceilings.

## Evidence gate

Before any LLM call, `validate_evidence` requires either an exact provision hit (metadata/graph),
evidence covering ≥ `EVIDENCE_MIN_TERM_COVERAGE` of the query's content terms, or a dense cosine
≥ `EVIDENCE_MIN_DENSE_SCORE`. Otherwise the pipeline answers "cannot find sufficient support"
without calling the LLM. Mappings only count as evidence for provisions the user named. The dense
threshold is model-specific and must be calibrated on labelled data.

## Generation and verification

`app/services/generation.py` builds a system prompt that requires bracketed citation IDs, forbids
provisions/cases absent from the evidence, forbids describing one provision using another's text,
and forbids prediction/advice/strategy. Role-aware tone: citizen / advocate / researcher.

`validate_output` (after normalizing `【C1】`/`[ C1 ]` to `[C1]`) rejects: unknown citation IDs,
section/article numbers absent from evidence/mappings/question, case names absent from evidence, and
uncited answers when evidence exists. Non-streaming requests get **one** corrective regeneration
(`OUTPUT_VALIDATION_MAX_REGENERATIONS`); invalid IDs are then stripped and warnings returned.
Streaming cannot retract tokens, so the `validation` event reports the result instead.
Only actually-cited evidence is returned as `citations`.

## LLM providers

`LLMProvider` interface → `GroqProvider` (real streaming; reasoning models get
`include_reasoning=false` + `reasoning_effort`, otherwise hidden reasoning can consume the whole
budget). `LLMRouter` applies retry (exponential backoff + full jitter) only to retryable errors
(timeouts, 408/409/425/429/5xx) and falls back through `LLM_PROVIDER_ORDER`; 4xx such as 401/404 move
to the next provider immediately. Streams only retry/fallback before the first token.

## IPC ↔ BNS mapping

`LegalProvisionMapper` reads `data/mappings/ipc_bns.json` (47 curated entries: IPC→BNS, CrPC→BNSS,
IEA→BSA) and distinguishes `exact`, `approximate`, `no_mapping` (e.g. IPC 377, 497), `ambiguous`
(dataset and graph disagree) and `unknown`. Reverse lookups report consolidations (BNS 318 ←
IPC 415/417/420) as exact many-to-one. Every result carries provenance, verification status and the
2024-07-01 effective date; Neo4j `REPLACED_BY` edges cross-check entries when available.
