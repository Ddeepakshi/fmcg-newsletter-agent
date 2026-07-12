"""Tests for src/llm_client.py.

The no-key fail-fast path always runs (it's a regression guard for a real bug
we hit: a missing key used to retry 3x with exponential backoff before
failing). The real-Groq-call tests are skipped when no GROQ_API_KEY is set.

The malformed-response-retry tests mock `_chat` directly, so they run
unconditionally (no real network/key needed) and assert on call counts to
prove a *fresh* LLM call is made on retry, not just a re-parse of the same
broken string.
"""
import json
import time

import pytest

import config
from src.llm_client import (
    LLMUnavailableError,
    classify_relevance,
    classify_relevance_batch,
    extract_deal,
    extract_deals_batch,
    generate_newsletter,
)
from tests.conditions import has_groq_key


def test_missing_key_fails_fast_not_after_retries(monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", "")
    t0 = time.time()
    with pytest.raises(LLMUnavailableError):
        classify_relevance("Some title", "Some snippet")
    elapsed = time.time() - t0
    assert elapsed < 2, f"expected an immediate failure, took {elapsed:.1f}s (retry-storm regression?)"


def test_batch_functions_return_empty_dict_for_no_items_without_a_key(monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", "")
    assert classify_relevance_batch([]) == {}
    assert extract_deals_batch([]) == {}


def test_malformed_json_response_retries_with_a_fresh_call_then_succeeds(monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", "fake-key-for-this-test")
    calls = {"n": 0}

    def flaky_chat(model, messages, json_mode=False, temperature=0.0):
        calls["n"] += 1
        if calls["n"] == 1:
            return "not valid json {{{"
        return json.dumps({"results": [{"index": 0, "verdict": "Relevant"}]})

    monkeypatch.setattr("src.llm_client._chat", flaky_chat)

    result = classify_relevance_batch([{"index": 0, "title": "t", "snippet": "s"}])

    assert result == {0: "Relevant"}
    assert calls["n"] == 2, "expected a fresh LLM call on retry, not a re-parse of the same output"


def test_response_missing_required_key_is_treated_as_malformed_and_retried(monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", "fake-key-for-this-test")
    calls = {"n": 0}

    def flaky_chat(model, messages, json_mode=False, temperature=0.0):
        calls["n"] += 1
        if calls["n"] == 1:
            return json.dumps({"unexpected_key": []})  # valid JSON, wrong shape
        return json.dumps({"results": [{"index": 0, "acquirer": "ITC"}]})

    monkeypatch.setattr("src.llm_client._chat", flaky_chat)

    result = extract_deals_batch([{"index": 0, "title": "t", "snippet": "s"}])

    assert result[0]["acquirer"] == "ITC"
    assert calls["n"] == 2


def test_persistently_malformed_response_exhausts_retries_and_raises_unavailable(monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", "fake-key-for-this-test")
    calls = {"n": 0}

    def always_malformed(model, messages, json_mode=False, temperature=0.0):
        calls["n"] += 1
        return "still not json"

    monkeypatch.setattr("src.llm_client._chat", always_malformed)

    with pytest.raises(LLMUnavailableError):
        classify_relevance_batch([{"index": 0, "title": "t", "snippet": "s"}])

    assert calls["n"] == config.LLM_MAX_RETRIES


@pytest.mark.skipif(not has_groq_key(), reason="GROQ_API_KEY not set")
def test_classify_relevance_real_call():
    verdict = classify_relevance("ITC to acquire Prasuma Foods for $150 million", "FMCG major expands food portfolio")
    assert verdict in ("Relevant", "Not Relevant")


@pytest.mark.skipif(not has_groq_key(), reason="GROQ_API_KEY not set")
def test_classify_relevance_batch_real_call_covers_all_items():
    items = [
        {"index": 0, "title": "ITC to acquire Prasuma Foods for $150 million", "snippet": "FMCG major expands food portfolio"},
        {"index": 1, "title": "Local team wins regional cricket match", "snippet": "sports news"},
    ]
    verdicts = classify_relevance_batch(items)
    assert set(verdicts.keys()) == {0, 1}
    assert verdicts[0] in ("Relevant", "Not Relevant")
    assert verdicts[1] in ("Relevant", "Not Relevant")


@pytest.mark.skipif(not has_groq_key(), reason="GROQ_API_KEY not set")
def test_extract_deal_real_call():
    result = extract_deal("ITC to acquire Prasuma Foods for $150 million", "Deal expected to close in Q3")
    assert isinstance(result, dict)
    assert set(result.keys()) >= {"acquirer", "target", "deal_type", "deal_value", "currency"}


@pytest.mark.skipif(not has_groq_key(), reason="GROQ_API_KEY not set")
def test_extract_deals_batch_real_call_covers_all_items():
    items = [
        {"index": 0, "title": "ITC to acquire Prasuma Foods for $150 million", "snippet": "Deal expected to close in Q3"},
        {"index": 1, "title": "Marico invests in D2C beauty brand for $10 million", "snippet": "strategic stake"},
    ]
    results = extract_deals_batch(items)
    assert set(results.keys()) == {0, 1}


@pytest.mark.skipif(not has_groq_key(), reason="GROQ_API_KEY not set")
def test_generate_newsletter_real_call():
    records = [{
        "title": "ITC to acquire Prasuma Foods for $150 million", "acquirer": "ITC", "target": "Prasuma Foods",
        "deal_type": "Acquisition", "deal_value": 150, "currency": "USD", "region": "India",
        "source": "Economic Times", "url": "https://a.com/1", "published_date": "2026-07-11",
    }]
    newsletter = generate_newsletter(records)
    assert isinstance(newsletter, str) and len(newsletter) > 0
