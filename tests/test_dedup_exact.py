"""Tests for src/dedup_exact.py."""
from src.dedup_exact import dedup_exact
from src.schema import new_record


def test_merges_identical_url_keeping_higher_tier():
    records = [
        new_record(title="A", url="https://a.com/1", source_tier=2, published_date="2026-07-10"),
        new_record(title="A duplicate wording", url="https://a.com/1", source_tier=1, published_date="2026-07-10"),
    ]
    survivors, dups = dedup_exact(records)
    assert len(survivors) == 1
    assert len(dups) == 1
    assert survivors[0]["source_tier"] == 1


def test_merges_near_identical_titles():
    records = [
        new_record(title="ITC to acquire Prasuma Foods", url="https://a.com/1", source_tier=1, published_date="2026-07-10"),
        new_record(title="ITC to Acquire Prasuma Foods.", url="https://b.com/2", source_tier=2, published_date="2026-07-10"),
        new_record(title="Completely unrelated headline here", url="https://c.com/3", source_tier=3, published_date="2026-07-09"),
    ]
    survivors, dups = dedup_exact(records)
    assert len(survivors) == 2
    assert len(dups) == 1


def test_no_duplicates_returns_all_records_unchanged():
    records = [
        new_record(title="First unrelated headline", url="https://a.com/1", source_tier=1, published_date="2026-07-10"),
        new_record(title="Second unrelated headline", url="https://b.com/2", source_tier=1, published_date="2026-07-10"),
    ]
    survivors, dups = dedup_exact(records)
    assert len(survivors) == 2
    assert len(dups) == 0
