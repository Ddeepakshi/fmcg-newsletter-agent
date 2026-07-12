"""Stage: Credibility Scoring (spec section 7).

Runs before LLM-based structured extraction, so `has_company_names` and
`has_deal_value` use lightweight regex/heuristics rather than the eventual
extraction output — good enough as a scoring signal, not meant to be a full
NER system. Articles below CREDIBILITY_THRESHOLD are dropped and logged.
"""
import logging
import re
from datetime import datetime, timezone

from dateutil import parser as date_parser

import config

logger = logging.getLogger(__name__)

_MONEY_RE = re.compile(
    r"(\$|₹|£|€|\bUSD\b|\bINR\b|\bRs\.?\b|\bcrore\b|\bcr\b|\blakh\b|\bmillion\b|"
    r"\bbillion\b|\bmn\b|\bbn\b)",
    re.IGNORECASE,
)

_STOPWORD_LEADERS = {"the", "a", "an", "this", "that", "these", "those", "in", "on", "for", "to"}
_CAP_WORD_RE = re.compile(r"\b([A-Z][\w&.-]*(?:\s+[A-Z][\w&.-]*)*)\b")


def _named_entity_count(text: str) -> int:
    """Heuristic proxy for named-entity presence: counts distinct runs of
    consecutive capitalized words, ignoring common sentence-leading words.
    """
    runs = _CAP_WORD_RE.findall(text or "")
    entities = set()
    for run in runs:
        words = run.split()
        if len(words) == 1 and words[0].lower() in _STOPWORD_LEADERS:
            continue
        entities.add(run.strip())
    return len(entities)


def _has_deal_value(text: str) -> bool:
    return bool(_MONEY_RE.search(text or ""))


def _recency_weight(published_date: str, now: datetime) -> float:
    try:
        dt = date_parser.parse(published_date)
    except (ValueError, TypeError, OverflowError):
        return 0.2
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    age_days = (now - dt).total_seconds() / 86400
    if age_days <= 3:
        return 1.0
    if age_days <= 7:
        return 0.6
    return 0.2


def score_record(record: dict, now: datetime = None) -> float:
    now = now or datetime.now(timezone.utc)
    text = f"{record.get('title', '')} {record.get('snippet', '')}"

    source_tier_weight = config.SOURCE_TIER_WEIGHTS.get(record.get("source_tier", 3), 0.3)
    has_company_names = 1 if _named_entity_count(text) >= 2 else 0
    has_deal_value = 1 if _has_deal_value(text) else 0
    recency_weight = _recency_weight(record.get("published_date", ""), now)
    completeness = 1 if all([record.get("title"), record.get("snippet"), record.get("published_date")]) else 0

    w = config.CREDIBILITY_WEIGHTS
    score = (
        w["source_tier"] * source_tier_weight
        + w["has_company_names"] * has_company_names
        + w["has_deal_value"] * has_deal_value
        + w["recency"] * recency_weight
        + w["completeness"] * completeness
    )
    return round(score, 4)


def score_credibility(records: list, threshold: float = None, now: datetime = None) -> tuple:
    """Returns (kept_records, excluded_log_entries). Mutates records with credibility_score."""
    threshold = threshold if threshold is not None else config.CREDIBILITY_THRESHOLD
    now = now or datetime.now(timezone.utc)

    kept, excluded = [], []
    for r in records:
        score = score_record(r, now=now)
        r["credibility_score"] = score
        if score < threshold:
            excluded.append({
                "url": r.get("url"), "title": r.get("title"),
                "credibility_score": score, "reason": f"below_threshold_{threshold}",
            })
        else:
            kept.append(r)

    logger.info(
        "Credibility scoring (threshold=%.2f): kept %d, excluded %d",
        threshold, len(kept), len(excluded),
    )
    return kept, excluded


if __name__ == "__main__":
    import json
    from datetime import datetime, timezone

    fixed_now = datetime(2026, 7, 12, tzinfo=timezone.utc)
    sample = [
        {"title": "ITC Ltd Acquires Prasuma Foods for $150 Million", "snippet": "Deal announced Friday",
         "source_tier": 1, "published_date": "2026-07-11T00:00:00+00:00", "url": "https://a.com/1"},
        {"title": "Small blog rumor about a deal", "snippet": "unverified", "source_tier": 3,
         "published_date": "2026-06-01T00:00:00+00:00", "url": "https://b.com/2"},
    ]
    kept, excluded = score_credibility(sample, now=fixed_now)
    print("Kept:", json.dumps(kept, indent=2))
    print("Excluded:", json.dumps(excluded, indent=2))
