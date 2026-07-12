"""Tests for src/newsletter_generator.py."""
import pytest

from src.newsletter_generator import build_newsletter, extractive_fallback
from tests.conditions import has_groq_key

SAMPLE_RECORDS = [
    {"title": "ITC to acquire Prasuma Foods for $150 million", "acquirer": "ITC", "target": "Prasuma Foods",
     "deal_value": 150, "currency": "USD", "credibility_score": 0.91, "source": "Economic Times", "url": "https://a.com/1"},
    {"title": "Low credibility rumor", "acquirer": None, "target": None, "deal_value": None, "currency": None,
     "credibility_score": 0.4, "source": "Blog", "url": "https://b.com/2"},
]


def test_extractive_fallback_ranks_by_credibility():
    text = extractive_fallback(SAMPLE_RECORDS)
    assert "ITC to acquire Prasuma Foods" in text
    first_idx = text.index("ITC to acquire Prasuma Foods")
    second_idx = text.index("Low credibility rumor")
    assert first_idx < second_idx  # higher credibility ranked first


def test_extractive_fallback_handles_empty_list():
    text = extractive_fallback([])
    assert "No deals met the relevance/credibility bar" in text


def test_build_newsletter_no_records_short_circuits():
    text, used_fallback = build_newsletter([])
    assert "No qualifying deals" in text
    assert used_fallback is False


def test_build_newsletter_without_key_uses_fallback():
    if has_groq_key():
        pytest.skip("GROQ_API_KEY is set; this test only covers the no-key fallback path")
    text, used_fallback = build_newsletter(SAMPLE_RECORDS)
    assert used_fallback is True
    assert "extractive fallback" in text.lower()


@pytest.mark.skipif(not has_groq_key(), reason="GROQ_API_KEY not set")
def test_build_newsletter_with_real_llm_call():
    text, used_fallback = build_newsletter(SAMPLE_RECORDS)
    assert used_fallback is False
    assert len(text) > 0
