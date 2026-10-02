"""End-to-end RAG evaluation through the real LangGraph pipeline.

    python scripts/evaluate_rag.py                       # retrieval + routing + safety (no LLM calls)
    python scripts/evaluate_rag.py --with-answers        # also generate answers (calls the LLM per query)
    python scripts/evaluate_rag.py --limit 5 --top-k 5

Isolation: the dataset corpus is indexed into an in-memory Qdrant collection with the configured
embedding model; your real index and user database are never touched. Uses the production
Container, pipeline, retrievers, rerankers and generator — only storage locations are swapped.

Reports (and writes evaluation/results/rag-<timestamp>.json):
* retrieval through the full pipeline: Recall@K, Precision@K, nDCG@K, MRR (span-overlap judging)
* routing accuracy against the labelled complexity
* safety questionnaire: refusal decisions through the graph
* with --with-answers: answer rate, citation validity, cited-evidence precision, regenerations, latency
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.container import Container  # noqa: E402
from app.core.config import PROJECT_ROOT, Settings  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.graph.state import PipelineMode, PipelineOptions  # noqa: E402
from app.rag.documents.loaders import discover  # noqa: E402
from app.rag.evaluation import metrics  # noqa: E402
from app.rag.evaluation.dataset import EvalDataset  # noqa: E402
from app.rag.evaluation.runner import build_unit_spans, judge  # noqa: E402
from app.services.generation import INSUFFICIENT_EVIDENCE_ANSWER  # noqa: E402

ROUTE_OF = {"SIMPLE": "simple", "MODERATE": "moderate", "COMPLEX": "complex"}


def pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q / 100 * (len(ordered) - 1))))] if ordered else 0.0


async def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dataset", type=Path, default=PROJECT_ROOT / "evaluation" / "legal_queries.json")
    p.add_argument("--safety", type=Path, default=PROJECT_ROOT / "evaluation" / "safety_questions.json")
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--limit", type=int, default=None, help="only the first N queries")
    p.add_argument("--reranker", choices=["none", "lexical", "cross_encoder"],
                   help="override the reranker of every retrieval profile (for A/B comparison)")
    p.add_argument("--with-answers", action="store_true", help="generate answers (one LLM call per query)")
    p.add_argument("--output", type=Path, default=PROJECT_ROOT / "evaluation" / "results")
    args = p.parse_args()
    configure_logging("WARNING", json_logs=False)

    dataset = EvalDataset.load(args.dataset)
    examples = dataset.examples[: args.limit] if args.limit else dataset.examples
    corpus = PROJECT_ROOT / dataset.corpus
    base = Settings()
    settings = base.model_copy(update={
        "qdrant_url": None, "qdrant_path": ":memory:", "qdrant_collection": "legal-lens-eval",
        "database_url": f"sqlite+aiosqlite:///{(Path(tempfile.mkdtemp()) / 'eval.db').as_posix()}",
        "embedding_preload": False, "neo4j_enabled": False, "adaptive_selection_mode": "rules",
    })
    print(f"reranker override: {args.reranker or 'none (profile defaults)'}")
    print(f"dataset {dataset.name} ({len(examples)} queries) | corpus {dataset.corpus} | embedding {settings.embedding_model} "
          f"| answers {'on (' + ','.join(f'{a}:{b}' for a, b in settings.llm_targets) + ')' if args.with_answers else 'off'}")

    container = Container(settings, neo4j=None)
    if args.reranker:
        for profile_obj in container.selector._profiles.values():
            profile_obj.reranker = args.reranker
    await container.startup()
    try:
        started = time.perf_counter()
        profile = container.chunk_profiles.get(settings.chunking_default_profile)
        for path in discover(corpus):
            report = await container.ingestion.ingest_document(path, corpus, profile)
            if report.status != "indexed":
                print(f"indexing failed for {path.name}: {report.error}")
                return 1
        await container.refresh_index_state()
        print(f"indexed corpus with {profile.name} in {time.perf_counter() - started:.1f}s\n")
        spans = build_unit_spans(corpus)

        rows = []
        for ex in examples:
            t0 = time.perf_counter()
            result = await container.pipeline.run(f"eval-{ex.id}", ex.query, PipelineOptions(
                mode=PipelineMode.SEARCH, allow_llm=False, top_k=args.top_k))
            latency = (time.perf_counter() - t0) * 1000
            ranked = sorted(result.evidence, key=lambda c: c.final_score, reverse=True)[: args.top_k]
            flags, units = judge(ex, ranked, spans)
            row = {
                "id": ex.id, "complexity": ex.complexity, "route": result.metadata.route,
                "route_ok": result.metadata.route == ROUTE_OF.get(ex.complexity),
                f"recall@{args.top_k}": metrics.recall_at_k(units, ex.expected_units, args.top_k),
                f"precision@{args.top_k}": metrics.precision_at_k(flags, args.top_k),
                f"ndcg@{args.top_k}": metrics.ndcg_at_k(units, ex.expected_units, args.top_k),
                "mrr": metrics.mrr(flags), "search_latency_ms": round(latency, 1),
                "subqueries": len(result.metadata.subqueries), "profile": result.metadata.retrieval_profile,
            }
            if args.with_answers:
                t1 = time.perf_counter()
                answer = await container.pipeline.run(f"eval-ans-{ex.id}", ex.query, PipelineOptions())
                validation = answer.metadata.output_validation
                cited_flags, _ = judge(ex, [e for e in answer.evidence
                                            if e.chunk_id in {c.chunk_id for c in answer.citations}], spans)
                row.update({
                    "answered": bool(answer.answer) and answer.answer != INSUFFICIENT_EVIDENCE_ANSWER,
                    "citations": len(answer.citations),
                    "citations_valid": bool(validation and validation.valid),
                    "regenerated": bool(validation and validation.regenerated),
                    "cited_precision": (sum(cited_flags) / len(cited_flags)) if cited_flags else 0.0,
                    "answer_latency_ms": round((time.perf_counter() - t1) * 1000, 1),
                })
            rows.append(row)
            print(f"  {ex.id:<4} {ex.complexity:<8} route={row['route']:<9} {'OK ' if row['route_ok'] else 'BAD'} "
                  f"recall={row[f'recall@{args.top_k}']:.2f} ndcg={row[f'ndcg@{args.top_k}']:.2f} "
                  f"mrr={row['mrr']:.2f} {row['search_latency_ms']:.0f}ms"
                  + (f" | answered={row['answered']} cites={row['citations']} valid={row['citations_valid']}"
                     if args.with_answers else ""))

        safety = json.loads(args.safety.read_text(encoding="utf-8"))["questions"]
        safety_rows = []
        for q in safety:
            r = await container.pipeline.run("eval-safety", q["query"], PipelineOptions(mode=PipelineMode.SEARCH, allow_llm=False))
            safety_rows.append(("refuse" if r.refused else "allow") == q["expected"])

        k = args.top_k
        mean = lambda key, rs=rows: round(statistics.fmean(r[key] for r in rs), 4) if rs else 0.0  # noqa: E731
        summary = {
            f"recall@{k}": mean(f"recall@{k}"), f"precision@{k}": mean(f"precision@{k}"), f"ndcg@{k}": mean(f"ndcg@{k}"),
            "mrr": mean("mrr"), "routing_accuracy": round(sum(r["route_ok"] for r in rows) / len(rows), 4),
            "safety_accuracy": round(sum(safety_rows) / len(safety_rows), 4),
            "search_latency_p50_ms": pct([r["search_latency_ms"] for r in rows], 50),
            "search_latency_p95_ms": pct([r["search_latency_ms"] for r in rows], 95),
        }
        by_complexity = {lvl: {f"recall@{k}": mean(f"recall@{k}", [r for r in rows if r["complexity"] == lvl]),
                               f"ndcg@{k}": mean(f"ndcg@{k}", [r for r in rows if r["complexity"] == lvl])}
                         for lvl in sorted({r["complexity"] for r in rows})}
        if args.with_answers:
            summary.update({
                "answer_rate": round(sum(r["answered"] for r in rows) / len(rows), 4),
                "citation_validity": round(sum(r["citations_valid"] for r in rows) / len(rows), 4),
                "cited_evidence_precision": mean("cited_precision"),
                "regeneration_rate": round(sum(r["regenerated"] for r in rows) / len(rows), 4),
                "answer_latency_p50_ms": pct([r["answer_latency_ms"] for r in rows], 50),
            })

        print("\nSUMMARY")
        for key, value in summary.items():
            print(f"  {key:<26} {value}")
        print("  by complexity:", json.dumps(by_complexity))
        args.output.mkdir(parents=True, exist_ok=True)
        out = args.output / f"rag-{time.strftime('%Y%m%d-%H%M%S')}.json"
        out.write_text(json.dumps({"reranker_override": args.reranker, "dataset": dataset.name, "fingerprint": dataset.fingerprint,
                                   "embedding_model": settings.embedding_model, "top_k": k,
                                   "with_answers": args.with_answers, "summary": summary,
                                   "by_complexity": by_complexity, "queries": rows}, indent=2), encoding="utf-8")
        print(f"\nwritten: {out}")
        print("note: the fixture corpus is small and paraphrased; treat these numbers as a pipeline check, not a "
              "quality claim for the real corpus.")
    finally:
        await container.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
