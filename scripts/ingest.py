"""Ingest legal documents into the vector index.

Examples:
    python scripts/ingest.py --source data/legal_docs
    python scripts/ingest.py --source data/legal_docs --profile semantic-p90-400
    python scripts/ingest.py --source data/legal_docs --strategy recursive --chunk-size 400 --overlap 50
    python scripts/ingest.py --source data/legal_docs --all-profiles --dry-run
    python scripts/ingest.py --source data/legal_docs --validate
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.container import build_embedder, build_store  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.exceptions import VectorStoreError  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.providers.llm.factory import build_llm_router  # noqa: E402
from app.rag.chunking.base import ChunkingProfile  # noqa: E402
from app.rag.chunking.registry import STRATEGIES, ChunkingProfileRegistry  # noqa: E402
from app.rag.documents.loaders import discover  # noqa: E402
from app.rag.ingestion import IngestionService  # noqa: E402
from app.rag.sparse import SparseEncoder  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", type=Path, required=True, help="file or directory of .txt/.md/.pdf/.docx documents")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--profile", help="named chunking profile from config/chunking_profiles.json")
    group.add_argument("--strategy", choices=STRATEGIES, help="ad-hoc profile: strategy (+ --chunk-size/--overlap)")
    group.add_argument("--all-profiles", action="store_true", help="index every configured profile (adaptive experiments)")
    p.add_argument("--chunk-size", type=int, default=400, help="approximate tokens (ad-hoc profile)")
    p.add_argument("--overlap", type=int, default=40, help="approximate tokens (ad-hoc profile)")
    p.add_argument("--dry-run", action="store_true", help="parse and chunk only; no embedding or writes")
    p.add_argument("--validate", action="store_true", help="compare sources with the index; no writes")
    p.add_argument("--force", action="store_true", help="re-embed even if this version is already indexed")
    p.add_argument("--json", action="store_true", help="print the report as JSON")
    return p.parse_args()


def select_profiles(args: argparse.Namespace, registry: ChunkingProfileRegistry) -> list[ChunkingProfile]:
    if args.all_profiles:
        return [registry.get(name) for name in registry.names()]
    if args.strategy:
        return [registry.adhoc(args.strategy, args.chunk_size, args.overlap)]
    return [registry.get(args.profile or registry.default)]


async def main() -> int:
    args = parse_args()
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=False)
    registry = ChunkingProfileRegistry.from_file(settings.chunking_profiles_path, settings.chunking_default_profile)
    profiles = select_profiles(args, registry)
    files = discover(args.source)
    root = args.source if args.source.is_dir() else args.source.parent
    if not files:
        print(f"no supported documents under {args.source}")
        return 1

    store = build_store(settings)
    embedder = build_embedder(settings)
    llm = build_llm_router(settings) if any(p.strategy == "ai" for p in profiles) else None
    service = IngestionService(
        embedder=embedder, store=store, sparse=SparseEncoder(), llm=llm,
        embed_batch_size=settings.embedding_batch_size * 4, upsert_batch_size=settings.qdrant_upsert_batch_size,
    )
    reports = []
    print(f"vector store: {store.describe()}")
    if store.mode == "remote" and not store.dense_name and not args.dry_run:
        # An empty dense vector name means an externally managed collection (the data-layer
        # cluster). This backend reads it; it must never write someone else's collection.
        print("\nERROR: refusing to ingest into the externally managed collection "
              f"{store.collection!r} (QDRANT_DENSE_VECTOR_NAME is empty).\n"
              "Point QDRANT_COLLECTION at a collection this backend owns, or use the local index\n"
              "by clearing QDRANT_URL for this shell.")
        return 2
    try:
        needs_index = not args.dry_run
        if needs_index:
            try:
                await store.ensure_collection(settings.embedding_dimension)
            except VectorStoreError as exc:
                print(f"\nERROR: cannot use {store.describe()}:\n  {exc}")
                if store.mode == "remote":
                    print("QDRANT_URL is set (environment variables override .env). To use the local embedded index,\n"
                          "clear it for this shell:   Remove-Item Env:QDRANT_URL, Env:QDRANT_API_KEY -ErrorAction SilentlyContinue\n"
                          "or check that the Qdrant server/cluster is running and reachable.")
                return 2
        for profile in profiles:
            for path in files:
                if args.validate:
                    reports.append(await service.validate_document(path, root, profile))
                else:
                    reports.append(await service.ingest_document(path, root, profile, dry_run=args.dry_run, force=args.force))
    finally:
        await store.close()
        if llm is not None:
            await llm.aclose()

    if args.json:
        print(json.dumps([r.model_dump() for r in reports], indent=2))
    else:
        for r in reports:
            stats = f"{r.stats.chunks} chunks, {r.stats.min_tokens}-{r.stats.max_tokens} tok (mean {r.stats.mean_tokens})" if r.stats else ""
            print(f"[{r.status:>17}] {r.profile:<22} {r.document_id:<28} {r.version:<16} units={r.units:<4} {stats} {r.error or ''}")
    return 1 if any(r.status == "failed" for r in reports) else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
