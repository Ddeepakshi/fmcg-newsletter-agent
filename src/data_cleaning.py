"""Stage: Data Cleaning.

Strips HTML/boilerplate, normalizes whitespace, standardizes dates to ISO
8601, tags source_tier and region, and drops incomplete records (missing
title, URL, or date).
"""
import logging
import re

from bs4 import BeautifulSoup
from dateutil import parser as date_parser

import config

logger = logging.getLogger(__name__)

_WHITESPACE_RE = re.compile(r"\s+")


def strip_html(text: str) -> str:
    if not text:
        return ""
    return BeautifulSoup(text, "html.parser").get_text(separator=" ")


def normalize_whitespace(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text or "").strip()


def to_iso8601(date_str: str) -> str:
    if not date_str:
        return ""
    try:
        dt = date_parser.parse(date_str)
        return dt.isoformat()
    except (ValueError, TypeError, OverflowError):
        logger.debug("Unparseable date: %r", date_str)
        return ""


def assign_source_tier(source_name: str) -> int:
    name = (source_name or "").strip().lower()
    for tier, names in config.SOURCE_TIERS.items():
        if any(known in name for known in names):
            return tier
    return 3


def assign_region(title: str, snippet: str) -> str:
    text = f"{title} {snippet}".lower()
    if any(kw in text for kw in config.INDIA_KEYWORDS):
        return "India"
    # If it clearly names a known non-India geography we still bucket as
    # Global by default, since the FMCG scope per the brief is India + Global.
    return "Global"


def clean_record(record: dict) -> dict | None:
    """Returns a cleaned copy of `record`, or None if it's incomplete."""
    title = normalize_whitespace(strip_html(record.get("title", "")))
    snippet = normalize_whitespace(strip_html(record.get("snippet", "")))
    url = (record.get("url") or "").strip()
    published_date = to_iso8601(record.get("published_date", ""))

    if not title or not url or not published_date:
        return None

    cleaned = dict(record)
    cleaned["title"] = title
    cleaned["snippet"] = snippet
    cleaned["url"] = url
    cleaned["published_date"] = published_date
    cleaned["source"] = normalize_whitespace(record.get("source", "")) or "Unknown"
    cleaned["source_tier"] = assign_source_tier(cleaned["source"])
    cleaned["region"] = assign_region(title, snippet)
    return cleaned


def clean_batch(records: list) -> list:
    cleaned = []
    dropped = 0
    for r in records:
        c = clean_record(r)
        if c is None:
            dropped += 1
            continue
        cleaned.append(c)
    logger.info("Cleaning: kept %d, dropped %d incomplete records", len(cleaned), dropped)
    return cleaned


if __name__ == "__main__":
    import json

    sample = [
        {"title": "  <b>ITC</b> to Acquire  Prasuma\n", "snippet": "<p>ITC acquires Prasuma foods</p>",
         "source": "Economic Times", "published_date": "Fri, 11 Jul 2026 10:00:00 GMT",
         "url": "https://example.com/a", "query_tag": "FMCG acquisition"},
        {"title": "", "snippet": "missing title", "source": "X", "published_date": "2026-07-11",
         "url": "https://example.com/b", "query_tag": "test"},
    ]
    out = clean_batch(sample)
    print(json.dumps(out, indent=2))
