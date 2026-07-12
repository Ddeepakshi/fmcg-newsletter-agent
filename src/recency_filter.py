"""Stage: Recency Filter.

Drops articles older than the configured window (config.RECENCY_DAYS, 14 by
default), even if they already passed dedup and relevance. This is what
keeps the newsletter reflecting current activity rather than an accumulated
archive.
"""
import logging
from datetime import datetime, timedelta, timezone

from dateutil import parser as date_parser

import config

logger = logging.getLogger(__name__)


def _parse_dt(value: str):
    try:
        dt = date_parser.parse(value)
    except (ValueError, TypeError, OverflowError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def filter_recency(records: list, days: int = None, now: datetime = None) -> tuple:
    """Returns (kept_records, dropped_log_entries). `now` is injectable for tests."""
    days = days if days is not None else config.RECENCY_DAYS
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    kept, dropped = [], []
    for r in records:
        dt = _parse_dt(r.get("published_date", ""))
        if dt is None:
            dropped.append({"url": r.get("url"), "title": r.get("title"), "reason": "unparseable_date"})
            continue
        if dt < cutoff:
            dropped.append({
                "url": r.get("url"), "title": r.get("title"),
                "reason": f"older_than_{days}_days", "published_date": r.get("published_date"),
            })
            continue
        kept.append(r)

    logger.info("Recency filter (<=%d days): kept %d, dropped %d", days, len(kept), len(dropped))
    return kept, dropped


if __name__ == "__main__":
    import json
    from datetime import datetime, timezone

    fixed_now = datetime(2026, 7, 12, tzinfo=timezone.utc)
    sample = [
        {"title": "Fresh deal", "url": "https://a.com/1", "published_date": "2026-07-11T00:00:00+00:00"},
        {"title": "Old deal", "url": "https://b.com/2", "published_date": "2026-06-01T00:00:00+00:00"},
    ]
    kept, dropped = filter_recency(sample, now=fixed_now)
    print("Kept:", json.dumps(kept, indent=2))
    print("Dropped:", json.dumps(dropped, indent=2))
