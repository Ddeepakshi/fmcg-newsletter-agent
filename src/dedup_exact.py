"""Stage: De-duplication, Stage 1 — exact/near-exact match.

Cheap pass before embeddings: merges records sharing an identical URL, then
merges remaining records whose normalized titles are near-identical per
RapidFuzz (no semantic model needed for these obvious cases).
"""
import logging

from rapidfuzz import fuzz

import config
from src.dedup_common import build_duplicate_entry, normalize_title, pick_canonical

logger = logging.getLogger(__name__)


def _merge_by_url(records: list) -> tuple:
    """Collapses records with an identical URL. Returns (survivors, dup_log)."""
    by_url = {}
    dup_log = []
    for r in records:
        url = r.get("url")
        if url not in by_url:
            by_url[url] = r
            continue
        canonical, duplicate = pick_canonical(by_url[url], r)
        by_url[url] = canonical
        dup_log.append(build_duplicate_entry(canonical, duplicate, method="exact_url", score=100.0))
    return list(by_url.values()), dup_log


def _merge_by_title(records: list, threshold: float) -> tuple:
    """Collapses records whose normalized titles are near-identical."""
    survivors = []
    dup_log = []
    normalized = [normalize_title(r["title"]) for r in records]

    absorbed = [False] * len(records)
    for i in range(len(records)):
        if absorbed[i]:
            continue
        current = records[i]
        for j in range(i + 1, len(records)):
            if absorbed[j]:
                continue
            score = fuzz.ratio(normalized[i], normalized[j])
            if score >= threshold:
                canonical, duplicate = pick_canonical(current, records[j])
                current = canonical
                absorbed[j] = True
                dup_log.append(
                    build_duplicate_entry(canonical, duplicate, method="fuzzy_title", score=score)
                )
        survivors.append(current)
    return survivors, dup_log


def dedup_exact(records: list, fuzzy_threshold: float = None) -> tuple:
    """Runs the two exact-stage passes. Returns (survivors, duplicate_log_entries)."""
    threshold = fuzzy_threshold if fuzzy_threshold is not None else config.FUZZY_TITLE_THRESHOLD

    after_url, url_dups = _merge_by_url(records)
    logger.info("Exact URL merge: %d -> %d", len(records), len(after_url))

    after_title, title_dups = _merge_by_title(after_url, threshold)
    logger.info("Fuzzy title merge: %d -> %d", len(after_url), len(after_title))

    return after_title, url_dups + title_dups


if __name__ == "__main__":
    import json

    sample = [
        {"title": "ITC to acquire Prasuma Foods", "url": "https://a.com/1", "source_tier": 1,
         "published_date": "2026-07-10"},
        {"title": "ITC to Acquire Prasuma Foods.", "url": "https://a.com/1", "source_tier": 1,
         "published_date": "2026-07-10"},
        {"title": "ITC acquires Prasuma Foods in FMCG push", "url": "https://b.com/2", "source_tier": 2,
         "published_date": "2026-07-10"},
        {"title": "Unrelated headline about tea prices", "url": "https://c.com/3", "source_tier": 3,
         "published_date": "2026-07-09"},
    ]
    survivors, dups = dedup_exact(sample)
    print("Survivors:", json.dumps(survivors, indent=2))
    print("Duplicates logged:", json.dumps(dups, indent=2))
