"""Tests for src/dedup_semantic.py (real embedding model, network-guarded)."""
import pytest

from src.dedup_semantic import dedup_semantic
from src.schema import new_record
from tests.conditions import has_network

pytestmark = pytest.mark.skipif(not has_network(), reason="no network available for model load/download")


def _sample_records():
    return [
        new_record(title="ITC acquires Prasuma Foods in FMCG expansion push", snippet="",
                    url="https://a.com/1", source_tier=1, published_date="2026-07-10"),
        new_record(title="ITC to buy Prasuma Foods, strengthening food portfolio", snippet="",
                    url="https://b.com/2", source_tier=2, published_date="2026-07-10"),
        new_record(title="Tea prices rise sharply amid supply concerns", snippet="",
                    url="https://c.com/3", source_tier=3, published_date="2026-07-09"),
    ]


def test_merges_when_similarity_crosses_a_lower_threshold():
    survivors, dups = dedup_semantic(_sample_records(), threshold=0.7)
    assert len(survivors) == 2
    assert len(dups) == 1
    survivor_tiers = {r["source_tier"] for r in survivors}
    assert 1 in survivor_tiers  # higher-tier source retained for the merged pair


def test_default_threshold_is_conservative_for_differently_worded_titles():
    # Real MiniLM cosine similarity for these two paraphrases of the same
    # deal lands around ~0.73 — below the project's default 0.85 threshold.
    # dedup_exact's fuzzy-title stage is what catches near-identical wording;
    # this semantic stage is deliberately reserved for near-verbatim
    # republication, not loose paraphrase, per the spec's own note that 0.85
    # was chosen by spot-checking sample pairs rather than a hard guarantee.
    survivors, dups = dedup_semantic(_sample_records())  # default threshold
    assert len(survivors) == 3
    assert len(dups) == 0


def test_single_record_returns_unchanged():
    records = [new_record(title="Solo article", url="https://a.com/1")]
    survivors, dups = dedup_semantic(records)
    assert survivors == records
    assert dups == []
