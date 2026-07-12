"""Tests for src/dedup_common.py."""
from src.dedup_common import build_duplicate_entry, normalize_title, pick_canonical


def test_normalize_title_strips_punctuation_and_case():
    assert normalize_title("ITC to Acquire Prasuma Foods.") == "itc to acquire prasuma foods"


def test_normalize_title_collapses_whitespace():
    assert normalize_title("  Multiple   spaces! ") == "multiple spaces"


def test_pick_canonical_higher_tier_wins_regardless_of_date():
    higher_tier = {"source_tier": 1, "published_date": "2026-07-01", "url": "https://a.com"}
    lower_tier = {"source_tier": 3, "published_date": "2026-07-10", "url": "https://b.com"}
    canonical, duplicate = pick_canonical(higher_tier, lower_tier)
    assert canonical is higher_tier and duplicate is lower_tier


def test_pick_canonical_tie_break_by_recency():
    newer = {"source_tier": 2, "published_date": "2026-07-10", "url": "https://c.com"}
    older = {"source_tier": 2, "published_date": "2026-07-01", "url": "https://d.com"}
    canonical, duplicate = pick_canonical(newer, older)
    assert canonical is newer and duplicate is older


def test_build_duplicate_entry_shape():
    canonical = {"url": "https://a.com", "title": "A"}
    duplicate = {"url": "https://b.com", "title": "B"}
    entry = build_duplicate_entry(canonical, duplicate, method="test", score=0.9)
    assert entry == {
        "duplicate_url": "https://b.com", "duplicate_title": "B",
        "retained_url": "https://a.com", "retained_title": "A",
        "method": "test", "score": 0.9,
    }
