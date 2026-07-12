"""Orchestrates the full FMCG deal intelligence pipeline (spec section 4).

    ingestion -> data_cleaning -> dedup_exact -> dedup_semantic ->
    relevance_filter (rule-based stage) -> recency_filter ->
    credibility_scoring -> relevance_filter (batched LLM stage) ->
    structured_extraction (batched) -> newsletter_generator -> output_writers

Rule-based filters (keywords, recency, credibility) run before either LLM
stage on purpose: they're free, and running them first means the LLM only
ever reviews/extracts articles that already survived every cheap filter —
in one real run, reviewing ambiguous articles before recency/credibility
cost 71 individual Groq calls for only 2 eventual survivors. Both remaining
LLM stages are batched (config.LLM_BATCH_SIZE articles per Groq request), so
the whole run now makes a handful of calls instead of one per article.

Every stage's drop/exclude log is written under data/logs/ for auditability.
A successful run also overwrites the "last known good" cache under
data/cache/ so the Streamlit app can always render something even if a live
run fails mid-way (spec section 10).
"""
import json
import logging
import time
from datetime import datetime, timezone

import config
from src import (
    credibility_scoring,
    data_cleaning,
    dedup_exact,
    dedup_semantic,
    ingestion,
    newsletter_generator,
    output_writers,
    recency_filter,
    relevance_filter,
    structured_extraction,
)

logger = logging.getLogger(__name__)


def _write_log(filename: str, entries: list) -> None:
    path = config.LOGS_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
    logger.info("Logged %d entries to %s", len(entries), path)


def _dotted_line(label: str, value, width: int = 42) -> str:
    value_str = str(value)
    dots = "." * max(1, width - len(label) - len(value_str))
    return f"{label} {dots} {value_str}"


def _print_summary_banner(summary: dict, elapsed_seconds: float) -> None:
    newsletter_items = min(summary["final_count"], config.NEWSLETTER_TOP_N)
    duplicates_removed = summary["cleaned_count"] - summary["after_dedup_count"]

    print("-" * 46)
    print(_dotted_line("Raw Articles", summary["raw_count"]))
    print(_dotted_line("Duplicates Removed", duplicates_removed))
    # "Credible" narrows before "Relevant" here on purpose — credibility and
    # recency are cheap rule-based filters applied before the batched LLM
    # relevance review, so this stage is deliberately the bigger number.
    print(_dotted_line("Credible Articles", summary["credible_count"]))
    print(_dotted_line("Relevant Articles", summary["relevant_count"]))
    print(_dotted_line("Newsletter Items", newsletter_items))
    print(f"Completed in {elapsed_seconds:.1f} sec")
    print("=" * 46 + "\n")


def run_pipeline(queries: list = None, use_gdelt: bool = True, verbose: bool = True) -> dict:
    """Runs every stage end-to-end. Returns a summary dict with records/newsletter/paths."""
    started_at_monotonic = time.time()
    run_started_at = datetime.now(timezone.utc).isoformat()

    raw = ingestion.collect_all(queries=queries, use_gdelt=use_gdelt, verbose=verbose)
    cleaned = data_cleaning.clean_batch(raw)

    after_exact, exact_dups = dedup_exact.dedup_exact(cleaned)
    after_semantic, semantic_dups = dedup_semantic.dedup_semantic(after_exact)
    _write_log("duplicates.json", exact_dups + semantic_dups)

    # Rule-based filters first (free) — the LLM only ever sees what survives
    # keyword filtering, recency, and credibility.
    rule_relevant, rule_dropped = relevance_filter.filter_relevance_rule_based(after_semantic)
    _write_log("relevance_dropped_rule.json", rule_dropped)

    recent, recency_dropped = recency_filter.filter_recency(rule_relevant)
    _write_log("recency_dropped.json", recency_dropped)

    credible, excluded_low_credibility = credibility_scoring.score_credibility(recent)
    _write_log("excluded_low_credibility.json", excluded_low_credibility)

    # Batched LLM stages: a handful of Groq requests instead of one per article.
    relevant, llm_dropped = relevance_filter.filter_relevance_llm_batch(credible)
    _write_log("relevance_dropped_llm.json", llm_dropped)

    final_records = structured_extraction.extract_deals(relevant)

    newsletter_markdown, used_fallback = newsletter_generator.build_newsletter(final_records)

    output_paths = output_writers.write_all_outputs(final_records, newsletter_markdown, config.OUTPUT_DIR)

    summary = {
        "run_started_at": run_started_at,
        "run_completed_at": datetime.now(timezone.utc).isoformat(),
        "raw_count": len(raw),
        "cleaned_count": len(cleaned),
        "after_dedup_count": len(after_semantic),
        "recent_count": len(recent),
        "credible_count": len(credible),
        "relevant_count": len(relevant),
        "final_count": len(final_records),
        "newsletter_used_fallback": used_fallback,
        "records": final_records,
        "newsletter_markdown": newsletter_markdown,
        "output_paths": output_paths,
    }

    _save_last_known_good(summary)

    if verbose:
        _print_summary_banner(summary, time.time() - started_at_monotonic)

    return summary


def _save_last_known_good(summary: dict) -> None:
    cache_path = config.CACHE_DIR / "last_known_good.json"
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    logger.info("Saved last-known-good cache: %s", cache_path)


def load_last_known_good() -> dict:
    cache_path = config.CACHE_DIR / "last_known_good.json"
    if not cache_path.exists():
        return None
    with open(cache_path, encoding="utf-8") as f:
        return json.load(f)


def run_pipeline_safe(queries: list = None, use_gdelt: bool = True, verbose: bool = True) -> tuple:
    """Runs the pipeline, falling back to the cached last-known-good summary on failure.

    Returns (summary, used_cache: bool).
    """
    try:
        return run_pipeline(queries=queries, use_gdelt=use_gdelt, verbose=verbose), False
    except Exception:
        logger.exception("Live pipeline run failed; falling back to last-known-good cache")
        cached = load_last_known_good()
        if cached is None:
            raise
        return cached, True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_pipeline()
    print(f"Final deal count: {result['final_count']}")
    print(f"Newsletter fallback used: {result['newsletter_used_fallback']}")
    print(result["newsletter_markdown"][:1000])
