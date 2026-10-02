# Adaptive RAG: what is measured, what is policy

"Adaptive" in Legal Lens means two *measured* decisions, both encoded as inspectable data rather
than runtime magic:

1. **Retrieval profile per query** — `config/retrieval_profiles.json` + the complexity router.
2. **Chunking profile per corpus** — `config/chunking_profiles.json` + the chunking benchmark.

Neither claims superiority without data; the numbers below come from the fixture corpus and the 18
labelled queries in `evaluation/legal_queries.json`. **The real legal corpus is the authoritative
benchmark once it is ingested** — re-run the scripts and re-decide.

## Policy (version 1)

```
policy_version: 1
rules:
  - complexity == SIMPLE   -> profile FAST     (top_k 6,  dense+sparse+metadata, lexical rerank, no expansion)
  - complexity == MODERATE -> profile BALANCED (top_k 10, +graph, lexical rerank, expansion)
  - complexity == COMPLEX  -> profile DEEP     (top_k 16, +graph, lexical rerank, expansion, decomposition)
  - intent in {provision_mapping, case_law} -> at least BALANCED
  - intent == document_analysis             -> DEEP
  - a request may force a profile (chat/search `profile`)
chunking:
  default: hierarchical-400 (120–512 token MoM window)
  data_driven mode: best profile from evaluation/results/latest.json when ADAPTIVE_SELECTION_MODE=data_driven
```

Complexity is a weighted feature score (`app/rag/query/complexity.py`, thresholds 1.0 / 2.6,
weights in `config/complexity.json` when provided), not a character count and not an LLM call.

## Benchmarks and how to run them

| Question | Command | Output |
|---|---|---|
| Which chunking profile retrieves best? | `python scripts/evaluate_chunking.py --write-latest --min-gain 0.02` | `evaluation/results/chunking_*.json`, `latest.json` |
| Does routing / hybrid / reranking help? | `python scripts/evaluate_rag.py [--reranker lexical\|cross_encoder\|none] [--with-answers]` | `evaluation/results/rag_*.json` |
| Does the guard hold? | `python scripts/evaluate_safety.py` | 20/20 on the questionnaire |

Reports separate **retrieval quality** (Recall@5/10, Precision@5/10, MRR, nDCG, hit rate),
**answer quality** (answer rate, citation validity, evidence coverage — only with `--with-answers`)
and **system performance** (latency, LLM calls, tokens), with per-query rows so failures are not
hidden behind averages.

## Measured so far (fixture corpus, 18 queries)

| Decision | Evidence | Outcome |
|---|---|---|
| Reranker | lexical: recall@5 1.000, nDCG@5 0.946, ~233 ms; ms-marco cross-encoder: 0.982 / 0.912, ~858 ms | all profiles use `lexical`; cross-encoder stays available via `RERANKER_MODEL` |
| Routing accuracy | 12/18 correct complexity labels (66.7 %) | weights untouched; too small a set to tune |
| Cross-code comparison | "Compare IPC 420 and BNS 318." scores 4.5 → COMPLEX (two acts + comparison + mapping intent); "Explain the difference between Article 14 and Article 21." scores 2.5 → MODERATE | kept: a cross-code comparison benefits from one retrieval per provision (decomposition); revisit with the real labelled set |
| Exact provisions | named provisions were dropped by the reranker | pinned in context fusion (phase 0), measured fix |
| Chunking | hierarchical-400 best on recall with the smallest context | default profile |

## What would change the policy

* A real-corpus benchmark showing cross-encoder (or a legal reranker such as `bge-reranker-v2-m3`)
  beating lexical by more than `--min-gain`.
* Judgments entering the corpus: `document_type`-specific chunk profiles (judgment paragraphs vs
  statute sections) selected from ingestion metadata (`chunk_profile` is stored on every chunk).
* Enough labelled queries (hundreds) to tune complexity weights; until then the classifier stays
  deterministic and inspectable (`POST /api/v1/diagnostics/route`).
