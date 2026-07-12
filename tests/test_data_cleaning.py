"""Tests for src/data_cleaning.py."""
from src import data_cleaning
from src.schema import new_record


def test_strip_html():
    # BeautifulSoup's separator inserts an extra space at nested-tag
    # boundaries — normalize_whitespace (run right after it in clean_record)
    # is what collapses that, so we assert on the combination, matching how
    # the two are actually used together.
    stripped = data_cleaning.strip_html("<p>ITC acquires <b>Prasuma</b></p>")
    assert "<" not in stripped and ">" not in stripped
    assert data_cleaning.normalize_whitespace(stripped) == "ITC acquires Prasuma"


def test_normalize_whitespace():
    assert data_cleaning.normalize_whitespace("  ITC   to Acquire\nPrasuma\n") == "ITC to Acquire Prasuma"


def test_to_iso8601_parses_rfc822_date():
    iso = data_cleaning.to_iso8601("Fri, 11 Jul 2026 10:00:00 GMT")
    assert iso.startswith("2026-07-11")


def test_to_iso8601_unparseable_returns_empty():
    assert data_cleaning.to_iso8601("not a date") == ""


def test_assign_source_tier_known_and_unknown():
    assert data_cleaning.assign_source_tier("Economic Times") == 1
    assert data_cleaning.assign_source_tier("Some Random Blog") == 3


def test_assign_region_india_keyword():
    assert data_cleaning.assign_region("ITC acquires Mumbai based firm", "") == "India"


def test_assign_region_defaults_global():
    assert data_cleaning.assign_region("Nestle acquires European brand", "") == "Global"


def test_clean_record_strips_and_normalizes():
    raw = new_record(
        title="  <b>ITC</b> to Acquire  Prasuma\n",
        snippet="<p>ITC acquires Prasuma foods</p>",
        source="Economic Times",
        published_date="Fri, 11 Jul 2026 10:00:00 GMT",
        url="https://example.com/a",
    )
    cleaned = data_cleaning.clean_record(raw)
    assert cleaned is not None
    assert cleaned["title"] == "ITC to Acquire Prasuma"
    assert cleaned["snippet"] == "ITC acquires Prasuma foods"
    assert cleaned["published_date"].startswith("2026-07-11")
    assert cleaned["source_tier"] == 1


def test_clean_record_drops_incomplete():
    raw = new_record(title="", snippet="x", url="https://example.com/b", published_date="2026-07-11")
    assert data_cleaning.clean_record(raw) is None


def test_clean_batch_reports_kept_and_dropped():
    good = new_record(title="Good", snippet="s", source="Reuters", published_date="2026-07-11", url="https://a.com/1")
    bad = new_record(title="", snippet="s", source="X", published_date="2026-07-11", url="https://a.com/2")
    cleaned = data_cleaning.clean_batch([good, bad])
    assert len(cleaned) == 1
    assert cleaned[0]["title"] == "Good"
