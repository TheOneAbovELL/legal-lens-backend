"""Create the payload indexes the backend's filters need on an externally managed Qdrant
collection (e.g. the data-layer ``judgment_chunks`` cluster).

Qdrant Cloud rejects filters on keys that have no payload index. Index creation is additive and
touches no data, so it is safe to run on a shared collection; run it once per collection.

    python scripts/prepare_external_collection.py           # uses QDRANT_* from .env
    python scripts/prepare_external_collection.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qdrant_client import AsyncQdrantClient, models  # noqa: E402

from app.core.config import get_settings  # noqa: E402

# Keys build_filter() can reference, across both payload schemas (ours and the data layer's).
KEYWORD_KEYS = (
    "document_id", "document_type", "act", "section", "court", "jurisdiction", "chunk_profile",
    "case_id", "doc_type", "statutes", "statutes_current", "chunk_id",
)
BOOL_KEYS = ("is_latest", "substantive")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="list missing indexes without creating them")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.qdrant_url:
        print("QDRANT_URL is not set; this script targets a remote collection only.")
        return 2
    client = AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None,
        timeout=30,
    )
    try:
        collection = settings.qdrant_collection
        info = await client.get_collection(collection)
        existing = set(info.payload_schema or {})
        print(f"collection {collection!r}: {info.points_count} points, indexed keys: {sorted(existing) or '(none)'}")
        wanted = [(k, models.PayloadSchemaType.KEYWORD) for k in KEYWORD_KEYS]
        wanted += [(k, models.PayloadSchemaType.BOOL) for k in BOOL_KEYS]
        missing = [(k, t) for k, t in wanted if k not in existing]
        if not missing:
            print("nothing to do; all filterable keys are indexed.")
            return 0
        for key, schema in missing:
            if args.dry_run:
                print(f"would create {schema.value:8} index on {key!r}")
                continue
            await client.create_payload_index(collection, key, schema, wait=True)
            print(f"created {schema.value:8} index on {key!r}")
        return 0
    finally:
        await client.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
