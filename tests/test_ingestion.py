"""Tests for src/ingestion.py — hits the real Google News RSS / GDELT endpoints.

GDELT's free API rate-limits aggressively by IP (429s/timeouts are common
even after retries) — that's an external constraint, not a bug, so the GDELT
test only asserts it degrades to ([], status) instead of raising, not that
it returns results.
"""
import pytest

import config
from src import ingestion
from tests.conditions import has_network

pytestmark = pytest.mark.skipif(not has_network(), reason="no network available")


def test_fetch_google_news_returns_articles():
    records = ingestion.fetch_google_news("FMCG acquisition")
    assert len(records) > 0
    first = records[0]
    assert first["title"]
    assert first["url"]
    assert first["query_tag"] == "FMCG acquisition"


def test_fetch_google_news_respects_max_results():
    records = ingestion.fetch_google_news("FMCG acquisition")
    assert len(records) <= config.GOOGLE_NEWS_MAX_RESULTS


def test_fetch_gdelt_degrades_gracefully_on_failure():
    records, status = ingestion.fetch_gdelt("FMCG acquisition")
    assert isinstance(records, list)  # [] on 429/rate-limit/timeout, populated list otherwise
    assert status in ("ok", "timeout", "unavailable")
    if status == "ok":
        assert len(records) <= config.GDELT_MAX_RESULTS
    else:
        assert records == []


def test_collect_all_merges_sources_without_gdelt():
    records = ingestion.collect_all(queries=["FMCG acquisition"], use_gdelt=False, verbose=False)
    assert len(records) > 0
    assert all(r["query_tag"] == "FMCG acquisition" for r in records)


def test_collect_all_disables_gdelt_after_first_failure(monkeypatch):
    call_count = 0

    def failing_gdelt(query, max_records=None):
        nonlocal call_count
        call_count += 1
        return [], "timeout"

    monkeypatch.setattr(ingestion, "fetch_gdelt", failing_gdelt)

    ingestion.collect_all(
        queries=["FMCG acquisition", "consumer goods merger", "beauty brand funding"],
        use_gdelt=True, verbose=False, sleep_between=0,
    )

    assert call_count == 1  # GDELT tried once, then skipped for the remaining queries
