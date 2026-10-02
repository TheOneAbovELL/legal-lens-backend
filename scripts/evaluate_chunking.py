"""Evaluate chunking strategies / retrieval modes against a labelled query set.

Examples:
    python scripts/evaluate_chunking.py --dataset evaluation/legal_queries.json \
        --strategies fixed sentence recursive semantic hierarchical --top-k 5 10
    python scripts/evaluate_chunking.py --profiles hierarchical-400 recursive-500-50 --retrieval dense hybrid
    python scripts/evaluate_chunking.py --embedding-model sentence-transformers/all-MiniLM-L6-v2 --embedding-dimension 384

Writes evaluation/results/<timestamp>.json (+ .csv) and, with --write-latest, latest.json, which
ADAPTIVE_SELECTION_MODE=data_driven uses to pick chunk profiles per query complexity.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import PROJECT_ROOT, get_settings  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.providers.embeddings.sentence_transformer import SentenceTransformerEmbedder  # noqa: E402
from app.rag.chunking.registry import ChunkingProfileRegistry  # noqa: E402
from app.rag.evaluation.dataset import EvalDataset  # noqa: E402
from app.rag.evaluation.runner import RETRIEVAL_MODES, EvaluationReport, EvaluationRunner  # noqa: E402

SAFE_EMBED_TOKENS = 2_000_000  # ask for --yes above this estimated embedding volume


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dataset", type=Path, default=PROJECT_ROOT / "evaluation" / "legal_queries.json")
    p.add_argument("--corpus", type=Path, help="defaults to the dataset's 'corpus' field")
    p.add_argument("--strategies", nargs="*", help="evaluate every configured profile of these strategies")
    p.add_argument("--profiles", nargs="*", help="explicit profile names")
    p.add_argument("--top-k", nargs="+", type=int, default=[5, 10])
    p.add_argument("--retrieval", nargs="+", choices=sorted(RETRIEVAL_MODES), default=["hybrid"])
    p.add_argument("--rerank", action="store_true", help="apply lexical reranking after retrieval")
    p.add_argument("--embedding-model", help="override EMBEDDING_MODEL")
    p.add_argument("--embedding-dimension", type=int, help="override EMBEDDING_DIMENSION")
    p.add_argument("--metric", default=None, help="primary metric for recommendations (default ndcg@<max k>)")
    p.add_argument("--min-gain", type=float, default=0.02,
                   help="minimum metric gain over the default profile required to recommend another profile")
    p.add_argument("--allow-llm", action="store_true", help="include 'ai' (LLM) chunking profiles")
    p.add_argument("--output", type=Path, default=PROJECT_ROOT / "evaluation" / "results")
    p.add_argument("--write-latest", action="store_true", help="also write results/latest.json for data-driven selection")
    p.add_argument("--yes", action="store_true", help="skip the cost confirmation for large runs")
    return p.parse_args()


def git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5,
                              cwd=PROJECT_ROOT).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


async def main() -> int:
    args = parse_args()
    settings = get_settings()
    configure_logging("WARNING", json_logs=False)
    dataset = EvalDataset.load(args.dataset)
    corpus = args.corpus or (PROJECT_ROOT / dataset.corpus)
    registry = ChunkingProfileRegistry.from_file(settings.chunking_profiles_path, settings.chunking_default_profile)

    names = list(args.profiles or [])
    for strategy in args.strategies or []:
        names.extend(n for n in registry.names(strategy) if n not in names)
    if not names:
        names = [registry.default]
    profiles = [registry.get(n) for n in names]
    skipped = [p.name for p in profiles if p.strategy == "ai" and not args.allow_llm]
    profiles = [p for p in profiles if p.name not in skipped]
    if skipped:
        print(f"skipping LLM chunking profiles (use --allow-llm): {', '.join(skipped)}")

    corpus_chars = sum(p.stat().st_size for p in corpus.rglob("*.txt"))
    estimate = corpus_chars // 4 * len(profiles)
    print(f"plan: {len(profiles)} profiles x {len(args.retrieval)} retrieval modes over {len(dataset.examples)} queries; "
          f"~{estimate:,} tokens to embed (before cross-profile caching)")
    if estimate > SAFE_EMBED_TOKENS and not args.yes:
        print("estimated embedding volume is large; re-run with --yes to proceed")
        return 2

    embedder = SentenceTransformerEmbedder(
        args.embedding_model or settings.embedding_model,
        dimension=args.embedding_dimension or settings.embedding_dimension,
        device=settings.embedding_device,
        model_version=settings.embedding_version,
        batch_size=settings.embedding_batch_size,
    )
    await embedder.warmup()
    runner = EvaluationRunner(embedder, corpus, dataset, args.top_k)
    metric = args.metric or f"ndcg@{max(args.top_k)}"

    results = []
    for profile in profiles:
        started = time.perf_counter()
        results.extend(await runner.evaluate_profile(profile, args.retrieval, args.rerank))
        print(f"  evaluated {profile.name} in {time.perf_counter() - started:.1f}s")

    report = EvaluationReport(
        dataset=dataset.name, dataset_fingerprint=dataset.fingerprint, embedding_model=embedder.model_name,
        ks=sorted(set(args.top_k)), results=results, classifier=runner.classifier_report(),
        recommendations=EvaluationRunner.recommend(results, metric, baseline=registry.default, min_gain=args.min_gain), primary_metric=metric,
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        notes=[f"git commit: {git_commit()}", f"corpus: {corpus}",
               "Metrics are only as representative as the labelled dataset and corpus."],
    )
    args.output.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_json = args.output / f"chunking-{stamp}.json"
    out_json.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    if args.write_latest:
        (args.output / "latest.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")

    ks = report.ks
    columns = ["profile", "strategy", "chunk_size", "overlap", "retrieval", "reranker", "chunks", "mean_chunk_tokens"]
    metric_cols = [f"{m}@{k}" for k in ks for m in ("recall", "precision", "hit", "ndcg")] + ["mrr"]
    tail = ["mean_latency_ms", "mean_context_tokens", "embedded_tokens", "index_seconds"]
    with (args.output / f"chunking-{stamp}.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(columns + metric_cols + tail)
        for r in results:
            row = r.model_dump()
            writer.writerow([row[c] for c in columns] + [r.metrics.get(m, "") for m in metric_cols] + [row[c] for c in tail])

    header = f"{'profile':<22}{'retr':<8}" + "".join(f"{m:>13}" for m in metric_cols) + f"{'lat_ms':>9}{'ctx_tok':>9}{'chunks':>8}"
    print("\n" + header)
    for r in sorted(results, key=lambda r: -r.metrics.get(metric, 0)):
        print(f"{r.profile:<22}{r.retrieval:<8}" + "".join(f"{r.metrics.get(m, 0):>13.3f}" for m in metric_cols)
              + f"{r.mean_latency_ms:>9.1f}{r.mean_context_tokens:>9.0f}{r.chunks:>8}")
    print(f"\ncomplexity classifier accuracy: {report.classifier.accuracy:.2%} on {report.classifier.examples} labelled queries")
    print(f"recommendations ({metric}): {json.dumps(report.recommendations)}")
    print(f"written: {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
