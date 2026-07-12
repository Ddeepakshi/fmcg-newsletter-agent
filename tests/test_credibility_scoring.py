"""Tests for src/credibility_scoring.py."""
from datetime import datetime, timezone

from src.credibility_scoring import score_credibility, score_record
from src.schema import new_record

FIXED_NOW = datetime(2026, 7, 12, tzinfo=timezone.utc)


def test_high_quality_article_scores_above_threshold():
    record = new_record(
        title="ITC Ltd Acquires Prasuma Foods for $150 Million",
        snippet="Deal announced Friday by ITC Limited",
        source_tier=1,
        published_date="2026-07-11T00:00:00+00:00",
        url="https://a.com/1",
    )
    score = score_record(record, now=FIXED_NOW)
    assert score > 0.5


def test_low_quality_article_scores_below_threshold():
    record = new_record(title="rumor", snippet="", source_tier=3, published_date="2026-06-01T00:00:00+00:00", url="https://b.com/2")
    score = score_record(record, now=FIXED_NOW)
    assert score < 0.5


def test_score_credibility_splits_kept_and_excluded():
    high = new_record(
        title="ITC Ltd Acquires Prasuma Foods for $150 Million", snippet="Deal announced Friday by ITC Limited",
        source_tier=1, published_date="2026-07-11T00:00:00+00:00", url="https://a.com/1",
    )
    low = new_record(title="rumor", snippet="", source_tier=3, published_date="2026-06-01T00:00:00+00:00", url="https://b.com/2")
    kept, excluded = score_credibility([high, low], now=FIXED_NOW)
    assert len(kept) == 1 and kept[0]["url"] == "https://a.com/1"
    assert len(excluded) == 1 and excluded[0]["url"] == "https://b.com/2"
    assert "credibility_score" in high  # mutated in place


def test_recency_component_decays_with_age():
    fresh = new_record(title="Fresh", snippet="s", source_tier=1, published_date="2026-07-11T00:00:00+00:00", url="https://a.com/1")
    stale = new_record(title="Stale", snippet="s", source_tier=1, published_date="2026-06-01T00:00:00+00:00", url="https://b.com/2")
    assert score_record(fresh, now=FIXED_NOW) > score_record(stale, now=FIXED_NOW)
