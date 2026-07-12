"""Stage: Relevance Filtering (two-stage, cost-aware).

Stage 1 (rule-based): keyword match against an FMCG industry list AND a deal
type list. Matching both passes immediately with no LLM call. An explicit
exclude list (product launches, appointments, etc.) short-circuits to
Not Relevant regardless of other matches. Single-list matches are tagged
'Ambiguous-Pending' and kept — final disposition is decided later, by
filter_relevance_llm_batch, AFTER recency/credibility filtering has shrunk
the dataset. This ordering matters: reviewing ambiguous articles before
recency/credibility filtering used to spend one Groq call per article on
articles that recency/credibility would drop anyway (71 calls for 3 eventual
survivors, in one real run) — running the cheap rule-based filters first
keeps that waste out of the LLM stage entirely.

Stage 2 (batched LLM): every remaining 'Ambiguous-Pending' record is
classified in chunks of config.LLM_BATCH_SIZE via one Groq request per
chunk, instead of one request per article. If a batch call fails, its
articles fail open (kept, flagged unreviewed) rather than being silently
dropped — same fail-open philosophy as the old per-article path, just
applied per chunk instead of per article.
"""
import logging

import config
from src.llm_client import LLMUnavailableError, classify_relevance_batch

logger = logging.getLogger(__name__)


def _matches_any(text: str, keywords: list) -> bool:
    return any(kw in text for kw in keywords)


def _rule_based_decision(title: str, snippet: str) -> str:
    """Returns 'relevant', 'not_relevant', or 'ambiguous'."""
    text = f"{title} {snippet}".lower()

    if _matches_any(text, config.EXCLUDE_KEYWORDS):
        return "not_relevant"

    industry_match = _matches_any(text, config.FMCG_INDUSTRY_KEYWORDS)
    dealtype_match = _matches_any(text, config.DEAL_TYPE_KEYWORDS)

    if industry_match and dealtype_match:
        return "relevant"
    if industry_match or dealtype_match:
        return "ambiguous"
    return "not_relevant"


def filter_relevance_rule_based(records: list) -> tuple:
    """Stage 1: keyword-only, no LLM. Returns (kept_records, dropped_log_entries).

    `kept` includes both dual-list matches (flagged 'Relevant') and
    single-list matches (flagged 'Ambiguous-Pending' — still awaiting a
    verdict from filter_relevance_llm_batch).
    """
    kept, dropped = [], []
    for r in records:
        decision = _rule_based_decision(r.get("title", ""), r.get("snippet", ""))
        if decision == "relevant":
            r["relevance_flag"] = "Relevant"
            kept.append(r)
        elif decision == "not_relevant":
            dropped.append({"url": r.get("url"), "title": r.get("title"), "reason": "rule_not_relevant"})
        else:
            r["relevance_flag"] = "Ambiguous-Pending"
            kept.append(r)

    logger.info("Rule-based relevance filter: kept %d, dropped %d", len(kept), len(dropped))
    return kept, dropped


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def filter_relevance_llm_batch(records: list, batch_size: int = None) -> tuple:
    """Stage 2: batch-classifies only records still flagged 'Ambiguous-Pending'.

    Records already decided (flagged 'Relevant') pass through untouched, at
    no LLM cost. Returns (kept_records, dropped_log_entries).
    """
    batch_size = batch_size or config.LLM_BATCH_SIZE
    to_review = [r for r in records if r.get("relevance_flag") == "Ambiguous-Pending"]
    kept = [r for r in records if r.get("relevance_flag") != "Ambiguous-Pending"]
    dropped = []

    if not to_review:
        return kept, dropped

    llm_batches = 0
    for chunk in _chunks(to_review, batch_size):
        items = [{"index": i, "title": r.get("title", ""), "snippet": r.get("snippet", "")} for i, r in enumerate(chunk)]
        llm_batches += 1
        try:
            verdicts = classify_relevance_batch(items)
        except LLMUnavailableError:
            logger.warning(
                "LLM unavailable during batched relevance review; keeping %d article(s) for manual review",
                len(chunk),
            )
            for r in chunk:
                r["relevance_flag"] = "Ambiguous-LLM-Unavailable"
                kept.append(r)
            continue

        for i, r in enumerate(chunk):
            verdict = verdicts.get(i)
            if verdict == "Relevant":
                r["relevance_flag"] = "Ambiguous-LLM-Reviewed"
                kept.append(r)
            elif verdict == "Not Relevant":
                dropped.append({"url": r.get("url"), "title": r.get("title"), "reason": "llm_not_relevant"})
            else:
                # response didn't cover this index — fail open rather than guess
                r["relevance_flag"] = "Ambiguous-LLM-Batch-Incomplete"
                kept.append(r)

    logger.info(
        "Batched LLM relevance filter: %d article(s) reviewed across %d Groq call(s), kept %d, dropped %d",
        len(to_review), llm_batches, len(kept), len(dropped),
    )
    return kept, dropped


if __name__ == "__main__":
    import json

    sample = [
        {"title": "ITC to acquire Prasuma Foods for $150 million", "snippet": "FMCG major ITC expands",
         "url": "https://a.com/1"},
        {"title": "Nestle launches new chocolate flavor", "snippet": "product news", "url": "https://b.com/2"},
        {"title": "Local firm appoints new regional head", "snippet": "leadership update", "url": "https://c.com/3"},
        {"title": "FMCG major expands cosmetics portfolio", "snippet": "quarterly update", "url": "https://d.com/4"},
    ]
    rule_kept, rule_dropped = filter_relevance_rule_based(sample)
    print("After rule-based stage:", json.dumps(rule_kept, indent=2))
    print("Dropped by rules:", json.dumps(rule_dropped, indent=2))

    final_kept, llm_dropped = filter_relevance_llm_batch(rule_kept)
    print("After LLM batch stage:", json.dumps(final_kept, indent=2))
    print("Dropped by LLM:", json.dumps(llm_dropped, indent=2))
