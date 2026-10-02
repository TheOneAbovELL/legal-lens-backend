from __future__ import annotations

import math

import pytest

from app.core.config import PROJECT_ROOT
from app.domain.query import Complexity, ComplexityResult
from app.rag.chunking.base import ChunkingProfile
from app.rag.evaluation import metrics
from app.rag.evaluation.dataset import EvalDataset, EvalExample
from app.rag.evaluation.runner import EvaluationRunner, build_unit_spans, judge
from app.rag.profiles import RetrievalProfileSelector
from tests.conftest import CORPUS
from tests.fakes import HashingEmbedder
from tests.rag.test_retrieval import _chunk

DATASET = PROJECT_ROOT / "evaluation" / "legal_queries.json"


def test_metrics_hand_computed() -> None:
    flags = [False, True, True, False]
    units = [{"d:9"}, {"d:1"}, {"d:2"}, {"d:1"}]
    expected = {"d:1", "d:2", "d:3"}
    assert metrics.precision_at_k(flags, 4) == 0.5
    assert metrics.recall_at_k(units, expected, 2) == pytest.approx(1 / 3)
    assert metrics.recall_at_k(units, expected, 4) == pytest.approx(2 / 3)
    assert metrics.hit_rate_at_k(flags, 1) == 0.0 and metrics.hit_rate_at_k(flags, 2) == 1.0
    assert metrics.mrr(flags) == 0.5
    dcg = 1 / math.log2(3) + 1 / math.log2(4)
    idcg = 1 / math.log2(2) + 1 / math.log2(3) + 1 / math.log2(4)
    assert metrics.ndcg_at_k(units, expected, 4) == pytest.approx(dcg / idcg)
    assert metrics.ndcg_at_k([{"d:1"}, {"d:2"}, {"d:3"}], expected, 3) == pytest.approx(1.0)


def test_dataset_loads_with_fingerprint_and_validates_labels() -> None:
    ds = EvalDataset.load(DATASET)
    assert ds.examples and ds.fingerprint
    assert {e.complexity for e in ds.examples} == {"SIMPLE", "MODERATE", "COMPLEX"}
    with pytest.raises(ValueError):
        EvalExample(id="x", query="q")


def test_structure_unaware_chunks_are_judged_by_text_location() -> None:
    """A chunk with no section metadata still counts if its text lies inside the labelled section."""
    spans = build_unit_spans(CORPUS)
    label, start, end = next(s for s in spans["fixture-ipc"] if s[0] == "420")
    chunk = _chunk("n", "x", 0.5, doc="fixture-ipc", section="1")
    chunk.metadata.section = None
    chunk.metadata.char_start, chunk.metadata.char_end = start + 5, end - 5
    example = EvalExample(id="e", query="q", expected_sections=["fixture-ipc:420"])
    flags, units = judge(example, [chunk], spans)
    assert flags == [True] and units == [{"fixture-ipc:420"}]


async def test_runner_end_to_end_with_test_embedder() -> None:
    ds = EvalDataset.load(DATASET)
    runner = EvaluationRunner(HashingEmbedder(64), CORPUS, ds, [5, 10])
    profiles = [ChunkingProfile(name="rec", strategy="recursive", chunk_size=300, overlap=30),
                ChunkingProfile(name="naive", strategy="fixed", chunk_size=300, overlap=30,
                                params={"respect_structure": False})]
    results = []
    for profile in profiles:
        results.extend(await runner.evaluate_profile(profile, ["sparse", "hybrid"], rerank=False))
    assert len(results) == 4
    for r in results:
        for key in ("recall@5", "precision@5", "ndcg@10", "mrr", "hit@10"):
            assert 0.0 <= r.metrics[key] <= 1.0
        assert r.chunks > 0 and r.embedded_tokens >= 0 and r.by_complexity
    naive = next(r for r in results if r.profile == "naive" and r.retrieval == "sparse")
    assert naive.metrics["hit@10"] > 0  # previously 0.0 because of metadata-based judging
    rec = EvaluationRunner.recommend(results, "ndcg@10")
    assert set(rec["chunk_profile_by_complexity"]) == {"SIMPLE", "MODERATE", "COMPLEX"}
    guarded = EvaluationRunner.recommend(results, "ndcg@10", baseline="rec", min_gain=1.1)  # impossible margin
    assert set(guarded["chunk_profile_by_complexity"].values()) == {"rec"}
    assert all(v.startswith("no_clear_winner") for v in guarded["decision"].values())
    report = runner.classifier_report()
    assert report.examples == len(ds.examples) and 0 <= report.accuracy <= 1


def test_data_driven_selector_uses_evaluation_recommendations(tmp_path) -> None:  # type: ignore[no-untyped-def]
    results = tmp_path / "latest.json"
    results.write_text('{"recommendations": {"chunk_profile_by_complexity": {"SIMPLE": "sentence-250"}}}')
    selector = RetrievalProfileSelector.from_file(
        PROJECT_ROOT / "config" / "retrieval_profiles.json", default_chunk_profile="hierarchical-400",
        mode="data_driven", evaluation_results=results,
    )
    simple = ComplexityResult(complexity=Complexity.SIMPLE, confidence=1, score=0)
    selection = selector.select(simple, None)
    assert selection.mode == "data_driven" and selection.profile.chunk_profiles == ["sentence-250"]
    moderate = ComplexityResult(complexity=Complexity.MODERATE, confidence=1, score=1)
    assert selector.select(moderate, None).profile.chunk_profiles == ["hierarchical-400"]  # rules fallback
    selector.indexed_chunk_profiles = {"hierarchical-400"}
    assert selector.select(simple, None).profile.chunk_profiles is None  # not indexed -> search all
