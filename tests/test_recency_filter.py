"""Tests for src/recency_filter.py."""
from datetime import datetime, timezone

from src.recency_filter import filter_recency
from src.schema import new_record


def test_keeps_recent_drops_old():
    fixed_now = datetime(2026, 7, 12, tzinfo=timezone.utc)
    records = [
        new_record(title="Fresh", url="https://a.com/1", published_date="2026-07-11T00:00:00+00:00"),
        new_record(title="Old", url="https://b.com/2", published_date="2026-06-01T00:00:00+00:00"),
    ]
    kept, dropped = filter_recency(records, now=fixed_now)
    assert len(kept) == 1
    assert kept[0]["title"] == "Fresh"
    assert len(dropped) == 1
    assert dropped[0]["reason"].startswith("older_than_")


def test_drops_unparseable_date():
    records = [new_record(title="Bad date", url="https://a.com/1", published_date="not-a-date")]
    kept, dropped = filter_recency(records)
    assert not kept
    assert dropped[0]["reason"] == "unparseable_date"


def test_custom_window_days():
    fixed_now = datetime(2026, 7, 12, tzinfo=timezone.utc)
    records = [new_record(title="10 days old", url="https://a.com/1", published_date="2026-07-02T00:00:00+00:00")]
    kept, _ = filter_recency(records, days=14, now=fixed_now)
    assert len(kept) == 1
    kept, _ = filter_recency(records, days=7, now=fixed_now)
    assert len(kept) == 0
