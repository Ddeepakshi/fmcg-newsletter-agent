"""Shared helpers used by both de-duplication stages (exact + semantic).

Kept separate so dedup_exact.py and dedup_semantic.py can each be tested and
reasoned about independently while sharing one tie-break rule.
"""
import re

import config

_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    text = (title or "").lower()
    text = _PUNCT_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def pick_canonical(record_a: dict, record_b: dict) -> tuple:
    """Returns (canonical, duplicate) between two records covering the same deal.

    Tie-break: higher source_tier weight wins; ties broken by more recent
    published_date. Mirrors the credibility formula's source_tier_weight term
    since the full credibility_score isn't computed until a later stage.
    """
    weight_a = config.SOURCE_TIER_WEIGHTS.get(record_a.get("source_tier", 3), 0.3)
    weight_b = config.SOURCE_TIER_WEIGHTS.get(record_b.get("source_tier", 3), 0.3)

    if weight_a != weight_b:
        return (record_a, record_b) if weight_a > weight_b else (record_b, record_a)

    date_a = record_a.get("published_date", "") or ""
    date_b = record_b.get("published_date", "") or ""
    if date_a >= date_b:
        return record_a, record_b
    return record_b, record_a


def build_duplicate_entry(canonical: dict, duplicate: dict, method: str, score: float) -> dict:
    return {
        "duplicate_url": duplicate.get("url"),
        "duplicate_title": duplicate.get("title"),
        "retained_url": canonical.get("url"),
        "retained_title": canonical.get("title"),
        "method": method,
        "score": round(score, 4),
    }


if __name__ == "__main__":
    assert normalize_title("ITC to Acquire Prasuma Foods.") == "itc to acquire prasuma foods"
    assert normalize_title("  Multiple   spaces! ") == "multiple spaces"

    higher_tier = {"source_tier": 1, "published_date": "2026-07-01", "url": "https://a.com"}
    lower_tier = {"source_tier": 3, "published_date": "2026-07-10", "url": "https://b.com"}
    canonical, duplicate = pick_canonical(higher_tier, lower_tier)
    assert canonical is higher_tier and duplicate is lower_tier, "higher source_tier should win regardless of date"

    same_tier_newer = {"source_tier": 2, "published_date": "2026-07-10", "url": "https://c.com"}
    same_tier_older = {"source_tier": 2, "published_date": "2026-07-01", "url": "https://d.com"}
    canonical, duplicate = pick_canonical(same_tier_newer, same_tier_older)
    assert canonical is same_tier_newer, "on a tier tie, more recent date should win"

    entry = build_duplicate_entry(higher_tier, lower_tier, method="test", score=0.9)
    assert entry["retained_url"] == "https://a.com" and entry["duplicate_url"] == "https://b.com"

    print("dedup_common: all assertions passed")
