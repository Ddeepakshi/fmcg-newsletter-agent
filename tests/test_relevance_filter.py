"""Tests for src/relevance_filter.py.

Rule-based stage tests run unconditionally (no network). The batched
Ambiguous-Pending -> LLM stage is exercised against the real Groq API and
skipped when no GROQ_API_KEY is configured.
"""
import pytest

from src.relevance_filter import filter_relevance_llm_batch, filter_relevance_rule_based
from src.schema import new_record
from tests.conditions import has_groq_key


def test_rule_based_relevant_needs_no_llm_call():
    records = [new_record(title="ITC to acquire Prasuma Foods for $150 million", snippet="FMCG major expands", url="https://a.com/1")]
    kept, dropped = filter_relevance_rule_based(records)
    assert len(kept) == 1
    assert kept[0]["relevance_flag"] == "Relevant"
    assert not dropped


def test_excludes_product_launch():
    records = [new_record(title="Nestle launches new chocolate flavor", snippet="product news", url="https://b.com/2")]
    kept, dropped = filter_relevance_rule_based(records)
    assert not kept
    assert dropped[0]["reason"] == "rule_not_relevant"


def test_excludes_marketing_campaign_even_with_fmcg_and_dealtype_keywords():
    # Guardrail: exclude list wins even when both the industry and deal-type
    # lists would otherwise match (e.g. "FMCG" + "investment"-adjacent wording).
    records = [new_record(title="FMCG brand launches marketing campaign investment push",
                           snippet="consumer goods advertising", url="https://z.com/9")]
    kept, dropped = filter_relevance_rule_based(records)
    assert not kept
    assert dropped[0]["reason"] == "rule_not_relevant"


def test_drops_no_keyword_match():
    records = [new_record(title="Weather forecast for the week", snippet="sunny", url="https://c.com/3")]
    kept, dropped = filter_relevance_rule_based(records)
    assert not kept
    assert len(dropped) == 1


def test_single_list_match_is_tagged_ambiguous_pending_not_dropped():
    records = [new_record(title="FMCG major expands cosmetics portfolio", snippet="quarterly update", url="https://d.com/4")]
    kept, dropped = filter_relevance_rule_based(records)
    assert len(kept) == 1
    assert kept[0]["relevance_flag"] == "Ambiguous-Pending"
    assert not dropped


def test_llm_batch_passes_through_already_decided_relevant_records_untouched():
    records = [new_record(title="Already decided", url="https://a.com/1", relevance_flag="Relevant")]
    kept, dropped = filter_relevance_llm_batch(records)
    assert kept == records
    assert not dropped


def test_llm_batch_without_key_fails_open_and_flags_unreviewed():
    if has_groq_key():
        pytest.skip("GROQ_API_KEY is set; this test only covers the no-key fail-open path")
    records = [new_record(title="FMCG major expands cosmetics portfolio", snippet="quarterly update",
                           url="https://d.com/4", relevance_flag="Ambiguous-Pending")]
    kept, dropped = filter_relevance_llm_batch(records)
    assert len(kept) == 1
    assert kept[0]["relevance_flag"] == "Ambiguous-LLM-Unavailable"
    assert not dropped


@pytest.mark.skipif(not has_groq_key(), reason="GROQ_API_KEY not set")
def test_llm_batch_with_real_call_reviews_all_pending_in_one_pass():
    relevant_ambiguous = new_record(
        title="ITC in advanced talks to acquire a stake in Prasuma", snippet="",
        url="https://e.com/5", relevance_flag="Ambiguous-Pending",
    )
    not_relevant_ambiguous = new_record(
        title="CloudTech announces acquisition of analytics startup", snippet="enterprise software deal",
        url="https://f.com/6", relevance_flag="Ambiguous-Pending",
    )
    kept, dropped = filter_relevance_llm_batch([relevant_ambiguous, not_relevant_ambiguous])
    kept_urls = {r["url"] for r in kept}
    assert "https://e.com/5" in kept_urls
    if kept:
        assert kept[0]["relevance_flag"] == "Ambiguous-LLM-Reviewed"
