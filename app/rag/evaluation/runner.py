"""Chunking / retrieval evaluation runner.

For every chunking profile the corpus is indexed into its own isolated in-memory Qdrant
collection using the production ingestion code, then every labelled query is run through the
production retrievers (dense / sparse / hybrid, optionally lexical reranking). Embeddings are
cached by text across profiles, so overlapping chunks are embedded only once.
"""

from __future__ import annotations

import statistics
import time
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, Field

from app.core.text import count_tokens
from app.domain.query import SubQuery
from app.domain.retrieval import RetrievalFilters, RetrievedChunk
from app.providers.embeddings.base import EmbeddingProvider
from app.providers.vector_store.qdrant_store import QdrantVectorStore
from app.rag.chunking.base import ChunkingProfile
from app.rag.documents.loaders import discover
from app.rag.evaluation import metrics
from app.rag.evaluation.dataset import EvalDataset, EvalExample
from app.rag.ingestion import IngestionService, prepare
from app.rag.query.complexity import QueryComplexityClassifier
from app.rag.query.entities import extract_entities
from app.rag.query.intent import IntentDetector
from app.rag.query.normalizer import normalize_query
from app.rag.reranking import LexicalReranker
from app.rag.retrieval.hybrid import HybridRetriever
from app.rag.retrieval.retrievers import DenseRetriever, MetadataRetriever, SparseRetriever
from app.rag.sparse import SparseEncoder

RETRIEVAL_MODES = {"dense": ["dense"], "sparse": ["sparse"], "hybrid": ["dense", "sparse", "metadata"]}


class CachingEmbedder(EmbeddingProvider):
    """Wraps a real embedder; memoises vectors by text for the duration of an evaluation run."""

    def __init__(self, inner: EmbeddingProvider) -> None:
        self._inner = inner
        self.model_name = inner.model_name
        self.model_version = inner.model_version
        self.dimension = inner.dimension
        self._cache: dict[str, list[float]] = {}
        self.embedded_texts = 0
        self.embedded_tokens = 0

    @property
    def is_ready(self) -> bool:
        return self._inner.is_ready

    async def warmup(self) -> None:
        await self._inner.warmup()

    async def embed_query(self, text: str) -> list[float]:
        key = "q:" + text
        if key not in self._cache:
            self._cache[key] = await self._inner.embed_query(text)
        return self._cache[key]

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        missing = [t for t in dict.fromkeys(texts) if "d:" + t not in self._cache]
        if missing:
            for text, vector in zip(missing, await self._inner.embed_documents(missing), strict=False):
                self._cache["d:" + text] = vector
            self.embedded_texts += len(missing)
            self.embedded_tokens += sum(count_tokens(t) for t in missing)
        return [self._cache["d:" + t] for t in texts]


class MetricSet(BaseModel):
    values: dict[str, float] = Field(default_factory=dict)  # e.g. "recall@5"


class ConfigResult(BaseModel):
    profile: str
    strategy: str
    chunk_size: int
    overlap: int
    retrieval: str
    reranker: str
    chunks: int
    mean_chunk_tokens: float
    index_seconds: float
    embedded_tokens: int
    metrics: dict[str, float]
    by_complexity: dict[str, dict[str, float]]
    mean_latency_ms: float
    p95_latency_ms: float
    mean_context_tokens: float


class ClassifierReport(BaseModel):
    accuracy: float
    confusion: dict[str, dict[str, int]]
    examples: int


class EvaluationReport(BaseModel):
    dataset: str
    dataset_fingerprint: str
    embedding_model: str
    ks: list[int]
    results: list[ConfigResult]
    classifier: ClassifierReport
    recommendations: dict[str, dict[str, str]]
    primary_metric: str
    created_at: str
    notes: list[str] = Field(default_factory=list)


#: document_id -> [(unit label, start, end)] from the structure extractor (ground-truth locations).
UnitSpans = dict[str, list[tuple[str, int, int]]]


def build_unit_spans(corpus_dir: Path) -> UnitSpans:
    spans: UnitSpans = {}
    for path in discover(corpus_dir):
        doc = prepare(path, corpus_dir)
        spans[doc.document.document_id] = [
            (u.number, u.start, u.end) for u in doc.units if u.number and u.end > u.start
        ]
    return spans


def units_of(chunk: RetrievedChunk, spans: UnitSpans, by_document: bool) -> set[str]:
    """Legal units whose text the chunk actually overlaps (independent of chunk metadata)."""
    md = chunk.metadata
    if by_document:
        return {f"{md.document_id}:*"}
    covered = {
        f"{md.document_id}:{label}"
        for label, start, end in spans.get(md.document_id, [])
        if md.char_start < end and md.char_end > start
    }
    if not covered and md.section:  # externally indexed chunks without offsets
        covered.add(f"{md.document_id}:{md.section}")
    return covered


def judge(example: EvalExample, chunks: list[RetrievedChunk], spans: UnitSpans) -> tuple[list[bool], list[set[str]]]:
    by_document = not example.expected_sections
    expected = example.expected_units
    units = [units_of(c, spans, by_document) for c in chunks]
    flags = [bool(u & expected) or c.chunk_id in example.relevant_chunk_ids for u, c in zip(units, chunks, strict=False)]
    return flags, units


def _percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    idx = min(len(ordered) - 1, int(round(pct / 100 * (len(ordered) - 1))))
    return ordered[idx]


class EvaluationRunner:
    def __init__(self, embedder: EmbeddingProvider, corpus_dir: Path, dataset: EvalDataset, ks: list[int]) -> None:
        self._embedder = CachingEmbedder(embedder)
        self._corpus = corpus_dir
        self._dataset = dataset
        self._ks = sorted(set(ks))
        self._sparse = SparseEncoder()
        self._spans = build_unit_spans(corpus_dir)

    def classifier_report(self) -> ClassifierReport:
        classifier, detector = QueryComplexityClassifier(), IntentDetector()
        labels = ["SIMPLE", "MODERATE", "COMPLEX"]
        confusion = {a: {p: 0 for p in labels} for a in labels}
        correct = 0
        for ex in self._dataset.examples:
            q = normalize_query(ex.query)
            entities = extract_entities(q)
            predicted = classifier.classify(q, entities, detector.detect(q, entities)).complexity.value
            confusion.setdefault(ex.complexity, {p: 0 for p in labels})[predicted] += 1
            correct += predicted == ex.complexity
        n = len(self._dataset.examples)
        return ClassifierReport(accuracy=round(correct / n, 4) if n else 0.0, confusion=confusion, examples=n)

    async def _index(self, profile: ChunkingProfile) -> tuple[QdrantVectorStore, int, float, float, int]:
        store = QdrantVectorStore(collection=f"eval-{profile.name}", path=":memory:")
        await store.ensure_collection(self._embedder.dimension)
        service = IngestionService(embedder=self._embedder, store=store, sparse=self._sparse)
        before = self._embedder.embedded_tokens
        start = time.perf_counter()
        token_counts: list[int] = []
        for path in discover(self._corpus):
            report = await service.ingest_document(path, self._corpus, profile)
            if report.status == "failed":
                raise RuntimeError(f"indexing {path.name} with {profile.name} failed: {report.error}")
            if report.stats:
                token_counts.extend([int(report.stats.mean_tokens)] * report.stats.chunks)
        elapsed = time.perf_counter() - start
        mean_tokens = statistics.fmean(token_counts) if token_counts else 0.0
        return store, len(token_counts), mean_tokens, elapsed, self._embedder.embedded_tokens - before

    async def evaluate_profile(
        self, profile: ChunkingProfile, retrieval_modes: list[str], rerank: bool
    ) -> list[ConfigResult]:
        store, n_chunks, mean_tokens, index_s, embedded = await self._index(profile)
        max_k = max(self._ks)
        results: list[ConfigResult] = []
        try:
            for mode in retrieval_modes:
                retriever = HybridRetriever([
                    DenseRetriever(self._embedder, store), SparseRetriever(self._sparse, store), MetadataRetriever(store),
                ])
                reranker = LexicalReranker() if rerank else None
                per_example: list[dict[str, float]] = []
                latencies: list[float] = []
                context_tokens: list[float] = []
                for ex in self._dataset.examples:
                    q = normalize_query(ex.query)
                    entities = extract_entities(q)
                    start = time.perf_counter()
                    hybrid = await retriever.retrieve(
                        [SubQuery(subquery_id="q0", query=q, purpose="eval")], entities,
                        filters=RetrievalFilters(), candidate_k=max_k * 3, sources=RETRIEVAL_MODES[mode],
                    )
                    ranked = hybrid.candidates
                    if reranker is not None:
                        ranked = await reranker.rerank(q, ranked, entities, max_k)
                    ranked = ranked[:max_k]
                    latencies.append((time.perf_counter() - start) * 1000)
                    flags, units = judge(ex, ranked, self._spans)
                    row = {"mrr": metrics.mrr(flags), "complexity": ex.complexity}  # type: ignore[dict-item]
                    for k in self._ks:
                        row[f"recall@{k}"] = metrics.recall_at_k(units, ex.expected_units, k)
                        row[f"precision@{k}"] = metrics.precision_at_k(flags, k)
                        row[f"hit@{k}"] = metrics.hit_rate_at_k(flags, k)
                        row[f"ndcg@{k}"] = metrics.ndcg_at_k(units, ex.expected_units, k)
                    per_example.append(row)
                    context_tokens.append(sum(c.metadata.token_count for c in ranked[: self._ks[0]]))

                def aggregate(rows: list[dict[str, float]]) -> dict[str, float]:
                    keys = [k for k in rows[0] if k != "complexity"] if rows else []
                    return {k: round(statistics.fmean(r[k] for r in rows), 4) for k in keys}

                by_complexity = {
                    level: aggregate([r for r in per_example if r["complexity"] == level])
                    for level in sorted({str(r["complexity"]) for r in per_example})
                }
                results.append(ConfigResult(
                    profile=profile.name, strategy=profile.strategy, chunk_size=profile.chunk_size,
                    overlap=profile.overlap, retrieval=mode, reranker="lexical" if rerank else "none",
                    chunks=n_chunks, mean_chunk_tokens=round(mean_tokens, 1), index_seconds=round(index_s, 3),
                    embedded_tokens=embedded, metrics=aggregate(per_example), by_complexity=by_complexity,
                    mean_latency_ms=round(statistics.fmean(latencies), 2), p95_latency_ms=round(_percentile(latencies, 95), 2),
                    mean_context_tokens=round(statistics.fmean(context_tokens), 1),
                ))
        finally:
            await store.close()
        return results

    @staticmethod
    def recommend(
        results: list[ConfigResult], metric: str, baseline: str | None = None, min_gain: float = 0.02
    ) -> dict[str, dict[str, str]]:
        """Best chunk profile per complexity class (and overall) by the primary metric.

        A profile only displaces ``baseline`` when it beats the baseline's best score by at least
        ``min_gain``; otherwise the baseline is kept and the decision is marked "no_clear_winner".
        Ties are broken by smaller LLM context (mean_context_tokens), then cheaper indexing.
        """

        def key(r: ConfigResult, value: float) -> tuple[float, float, float]:
            return (value, -r.mean_context_tokens, -r.embedded_tokens)

        recommendations: dict[str, dict[str, str]] = {"chunk_profile_by_complexity": {}, "overall": {}, "decision": {}}
        levels = sorted({lvl for r in results for lvl in r.by_complexity})
        for level in levels:
            scored = [r for r in results if metric in r.by_complexity.get(level, {})]
            if not scored:
                continue
            best = max(scored, key=lambda r: key(r, r.by_complexity[level][metric]))
            base = [r.by_complexity[level][metric] for r in scored if r.profile == baseline]
            margin = best.by_complexity[level][metric] - max(base) if base else None
            if baseline and margin is not None and margin < min_gain:
                recommendations["chunk_profile_by_complexity"][level] = baseline
                recommendations["decision"][level] = f"no_clear_winner (best gain {margin:+.4f} < {min_gain})"
            else:
                recommendations["chunk_profile_by_complexity"][level] = best.profile
                recommendations["decision"][level] = f"selected (gain {margin:+.4f})" if margin is not None else "selected"
        if results:
            best = max(results, key=lambda r: key(r, r.metrics.get(metric, 0.0)))
            recommendations["overall"] = {"profile": best.profile, "retrieval": best.retrieval, "reranker": best.reranker}
        return recommendations
