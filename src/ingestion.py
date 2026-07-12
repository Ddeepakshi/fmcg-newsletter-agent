"""Stage: Data Collection.

Fetches recent news via Google News RSS, GDELT, and (optionally) company
press-release RSS feeds. Stores only title/snippet/url/source/date/query_tag
per section 9 (compliance) — never full article bodies.
"""
import logging
import time
from datetime import datetime, timezone
from urllib.parse import quote

import feedparser
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

import config
from src.schema import new_record

logger = logging.getLogger(__name__)


def _retryable():
    return retry(
        reraise=True,
        stop=stop_after_attempt(config.REQUEST_MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=15),
    )


def _gdelt_retryable():
    # GDELT's free API is aggressively rate-limited and rarely recovers
    # within a single run — one attempt, no backoff, so a stuck source can't
    # slow down the rest of the pipeline.
    return retry(
        reraise=True,
        stop=stop_after_attempt(config.GDELT_MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=1, max=4),
    )


@_retryable()
def _fetch_url(url: str) -> bytes:
    resp = requests.get(
        url,
        timeout=config.REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": "Mozilla/5.0 (FMCG-Deal-Intelligence-Agent/1.0)"},
    )
    resp.raise_for_status()
    return resp.content


def fetch_google_news(query: str) -> list:
    """Fetch articles for a single query from Google News RSS."""
    url = config.GOOGLE_NEWS_RSS_TEMPLATE.format(query=quote(query))
    try:
        raw = _fetch_url(url)
    except Exception:
        logger.exception("Google News RSS fetch failed for query=%r", query)
        return []

    parsed = feedparser.parse(raw)
    records = []
    for entry in parsed.entries[: config.GOOGLE_NEWS_MAX_RESULTS]:
        source_name = getattr(getattr(entry, "source", None), "title", None) or "Google News"
        records.append(
            new_record(
                title=getattr(entry, "title", "") or "",
                snippet=getattr(entry, "summary", "") or "",
                source=source_name,
                published_date=getattr(entry, "published", "") or "",
                url=getattr(entry, "link", "") or "",
                query_tag=query,
            )
        )
    return records


@_gdelt_retryable()
def _fetch_gdelt_json(params: dict) -> dict:
    resp = requests.get(
        config.GDELT_DOC_API,
        params=params,
        timeout=config.GDELT_TIMEOUT_SECONDS,
        headers={"User-Agent": "Mozilla/5.0 (FMCG-Deal-Intelligence-Agent/1.0)"},
    )
    resp.raise_for_status()
    return resp.json()


def fetch_gdelt(query: str, max_records: int = None) -> tuple:
    """Fetch articles for a single query from the GDELT Doc API.

    Returns (records, status) where status is "ok", "timeout", or
    "unavailable" — GDELT is frequently rate-limited/slow, so callers use
    this to report a clean "skipped" state instead of a stack trace and keep
    going with Google News alone.
    """
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": max_records or config.GDELT_MAX_RESULTS,
        "sort": "datedesc",
    }
    try:
        data = _fetch_gdelt_json(params)
    except requests.exceptions.Timeout:
        logger.warning("GDELT unavailable for query=%r (timeout after %ss)", query, config.GDELT_TIMEOUT_SECONDS)
        return [], "timeout"
    except Exception as exc:
        logger.warning("GDELT unavailable for query=%r (%s)", query, exc)
        return [], "unavailable"

    records = []
    for art in data.get("articles", []):
        records.append(
            new_record(
                title=art.get("title", ""),
                snippet=art.get("title", ""),  # GDELT artlist has no snippet field
                source=art.get("domain", "GDELT"),
                published_date=art.get("seendate", ""),
                url=art.get("url", ""),
                query_tag=query,
            )
        )
    return records, "ok"


def fetch_press_releases() -> list:
    """Fetch configured company press-release RSS feeds, if any are set."""
    records = []
    for feed_url in config.PRESS_RELEASE_RSS_FEEDS:
        try:
            raw = _fetch_url(feed_url)
        except Exception:
            logger.exception("Press release feed fetch failed for %r", feed_url)
            continue
        parsed = feedparser.parse(raw)
        for entry in parsed.entries:
            records.append(
                new_record(
                    title=getattr(entry, "title", "") or "",
                    snippet=getattr(entry, "summary", "") or "",
                    source=parsed.feed.get("title", "Press Release"),
                    published_date=getattr(entry, "published", "") or "",
                    url=getattr(entry, "link", "") or "",
                    query_tag="press_release",
                )
            )
    return records


def _dotted_line(label: str, value, width: int = 42) -> str:
    value_str = str(value)
    dots = "." * max(1, width - len(label) - len(value_str))
    return f"{label} {dots} {value_str}"


def collect_all(queries: list = None, use_gdelt: bool = True, sleep_between: float = 0.5, verbose: bool = True) -> list:
    """Run ingestion across all configured queries and sources.

    Returns a flat list of raw article dicts (schema.EMPTY_RECORD shape).
    When `verbose`, prints a per-query fetch banner so a demo/reviewer sees
    exactly what was fetched from where, instead of a wall of raw log lines.

    GDELT is a circuit breaker, not a per-query retry: the first timeout/
    failure disables it for the rest of this run, so an unavailable GDELT
    costs one 8s wait total instead of one per remaining query.
    """
    queries = queries or config.SEARCH_QUERIES
    all_records = []
    gdelt_available = use_gdelt

    if verbose:
        print("\n" + "=" * 46)
        print("FMCG Deal Intelligence Pipeline".center(46))
        print("=" * 46 + "\n")

    for i, query in enumerate(queries, 1):
        if verbose:
            print(f"Query {i}/{len(queries)} : {query}")

        gn = fetch_google_news(query)
        all_records.extend(gn)
        if verbose:
            print(f"  {_dotted_line('Google RSS', len(gn))}")
        time.sleep(sleep_between)

        if use_gdelt:
            if gdelt_available:
                gd, status = fetch_gdelt(query)
                all_records.extend(gd)
                if status != "ok":
                    gdelt_available = False
                if verbose:
                    display = len(gd) if status == "ok" else f"{status.capitalize()} (Skipped)"
                    print(f"  {_dotted_line('GDELT', display)}")
                time.sleep(sleep_between)
            elif verbose:
                print(f"  {_dotted_line('GDELT', 'Disabled (prior failure)')}")

        if verbose:
            print()

    all_records.extend(fetch_press_releases())

    logger.info("Ingestion complete: %d raw records", len(all_records))
    return all_records


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = collect_all(queries=config.SEARCH_QUERIES[:2])
    print(f"Fetched {len(results)} raw records")
    for r in results[:5]:
        print(f"- [{r['source']}] {r['title']} ({r['published_date']})")
