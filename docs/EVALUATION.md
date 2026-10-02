# Evaluation

## Framework

* Dataset: `evaluation/legal_queries.json` — 18 labelled queries (8 SIMPLE, 6 MODERATE, 4 COMPLEX)
  over `evaluation/corpus/` (paraphrased IPC/BNS/CrPC/Constitution excerpts). Each example has
  `query`, `expected_sections` (`document_id:section`), optional `expected_document_ids` /
  `relevant_chunk_ids`, `query_type`, `complexity`, `evidence_requirements`.
* Runner (`app/rag/evaluation/runner.py`): each chunking profile is indexed into its own in-memory
  Qdrant collection by the **production** ingestion code, then queried by the **production**
  retrievers (dense / sparse / hybrid, optional lexical rerank). Embeddings are cached across
  profiles.
* Relevance is judged by **character-span overlap with the labelled section's location in the
  source**, not by chunk metadata, so structure-unaware chunks are judged fairly.
* Metrics (`metrics.py`): Recall@K (unit coverage), Precision@K, HitRate@K, MRR, nDCG@K, plus mean/p95
  retrieval latency, context tokens in the top results, chunk counts, embedded tokens (indexing
  cost) and indexing time. The complexity classifier's accuracy and confusion matrix are reported.
* Recommendations: best chunk profile per complexity by the primary metric (default nDCG@max K),
  **only** if it beats the default profile by `--min-gain` (default 0.02); otherwise
  `no_clear_winner` and the default is kept. Ties break on smaller context, then indexing cost.
* Output: `evaluation/results/chunking-<timestamp>.json/.csv`; `--write-latest` also writes
  `latest.json`, which `ADAPTIVE_SELECTION_MODE=data_driven` reads. Runs record the dataset
  fingerprint, embedding model and git commit. Large runs require `--yes`.

```bash
python scripts/evaluate_chunking.py --dataset evaluation/legal_queries.json \
    --strategies fixed sentence recursive semantic sliding_window hierarchical \
    --retrieval dense sparse hybrid --top-k 5 10 [--rerank] [--write-latest]
python scripts/evaluate_safety.py
```

## Results on the fixture set (BAAI/bge-m3, 2026-10-02)

17 profiles × 3 retrieval modes (the LLM `ai` profile skipped; `--allow-llm` enables it).

* Structure-aware strategies are **indistinguishable** on this corpus (nDCG@10 0.960–0.971,
  Recall@10 0.97–1.00): sections are short, so most strategies produce the same ~21 chunks.
  Differences of ≤ 0.01 are noise at n = 18.
* The structure-unaware baseline (`fixed-500-100-naive`) reaches the same recall but with
  **~4× the context** (1,490 vs ~370 tokens in the top 5) and lower nDCG@10 (0.908–0.927).
  This supports structure-aware chunking on context cost, not on recall.
* Sentence windows (`sliding-3-2`) gave the highest Precision@5 (0.40–0.41 vs 0.33) at slightly
  lower recall.
* The guard kept `hierarchical-400` for SIMPLE and COMPLEX (`no_clear_winner`). For MODERATE, the
  naive profile cleared the +0.02 margin (+0.03 on 6 queries) — a small-sample result that ignores
  its 4× context cost. Selection mode therefore stays `rules` until a larger, real-corpus set exists.
* Complexity classifier accuracy: 66.7% (12/18). Safety questionnaire: 20/20.

## What is needed for real conclusions

A labelled set (hundreds of queries) over the real corpus — full Acts and Supreme Court judgments,
where sections and judgments are long enough for chunking choices to matter — plus answer-level
grounding evaluation. The framework runs unchanged on such a set.
