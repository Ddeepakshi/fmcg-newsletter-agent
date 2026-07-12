"""Tests for src/structured_extraction.py."""
import pytest

import config
from src.structured_extraction import _apply_extraction, _normalize_deal_type, _normalize_deal_value, extract_deal_for_record, extract_deals
from src.schema import new_record
from tests.conditions import has_groq_key


def test_apply_extraction_nulls_invalid_fields_instead_of_saving_them():
    record = new_record(title="Suspicious article", url="https://a.com/1")
    hallucinated = {"acquirer": "ITC", "target": "Prasuma", "deal_type": "Rumor", "deal_value": -150, "currency": "usd"}

    _apply_extraction(record, hallucinated)

    assert record["acquirer"] == "ITC"  # untouched fields still pass through
    assert record["target"] == "Prasuma"
    assert record["deal_type"] is None  # rejected: not a known deal type
    assert record["deal_value"] is None  # rejected: negative
    assert record["currency"] == "USD"


def test_normalize_deal_type_matches_known_types():
    assert _normalize_deal_type("acquisition") == "Acquisition"
    assert _normalize_deal_type("This was a MERGER of equals") == "Merger"
    assert _normalize_deal_type(None) is None
    assert _normalize_deal_type("") is None


def test_normalize_deal_type_rejects_unrecognized_values():
    # Guardrail: an LLM hallucinating a deal_type outside the known set
    # must be nulled, not passed through as an arbitrary capitalized string.
    assert _normalize_deal_type("Rumor") is None
    assert _normalize_deal_type("Partnership announcement") is None


def test_normalize_deal_value_parses_numeric_strings():
    assert _normalize_deal_value("150") == 150.0
    assert _normalize_deal_value(150) == 150.0
    assert _normalize_deal_value("not a number") is None
    assert _normalize_deal_value(None) is None


def test_normalize_deal_value_rejects_non_positive_and_non_finite():
    # Guardrail: a deal_value must be a positive, finite number before saving.
    assert _normalize_deal_value(0) is None
    assert _normalize_deal_value(-150) is None
    assert _normalize_deal_value(float("inf")) is None
    assert _normalize_deal_value(float("nan")) is None


def test_extract_deal_for_record_without_key_leaves_fields_empty():
    if has_groq_key():
        pytest.skip("GROQ_API_KEY is set; this test only covers the no-key fallback path")
    record = new_record(title="ITC to acquire Prasuma Foods for $150 million", snippet="Deal expected to close", url="https://a.com/1")
    result = extract_deal_for_record(record)
    assert result["acquirer"] is None
    assert result["target"] is None


@pytest.mark.skipif(not has_groq_key(), reason="GROQ_API_KEY not set")
def test_extract_deal_for_record_real_call():
    record = new_record(title="ITC to acquire Prasuma Foods for $150 million", snippet="Deal expected to close in Q3", url="https://a.com/1")
    result = extract_deal_for_record(record)
    assert result["acquirer"] or result["target"]


@pytest.mark.skipif(not has_groq_key(), reason="GROQ_API_KEY not set")
def test_extract_deals_batches_multiple_records_in_one_groq_call():
    records = [
        new_record(title="ITC to acquire Prasuma Foods for $150 million", snippet="Deal expected to close in Q3", url="https://a.com/1"),
        new_record(title="Marico invests in D2C beauty brand for $10 million", snippet="strategic stake", url="https://b.com/2"),
    ]
    result = extract_deals(records, batch_size=config.LLM_BATCH_SIZE)
    assert result[0]["acquirer"] or result[0]["target"]
    assert result[1]["acquirer"] or result[1]["target"]


def test_extract_deals_chunks_across_multiple_batches(monkeypatch):
    calls = []

    def fake_extract_deals_batch(items):
        calls.append(len(items))
        return {i: {"acquirer": f"Acquirer{item['index']}", "target": None, "deal_type": None,
                    "deal_value": None, "currency": None} for i, item in enumerate(items)}

    monkeypatch.setattr("src.structured_extraction.extract_deals_batch", fake_extract_deals_batch)

    records = [new_record(title=f"Article {i}", url=f"https://a.com/{i}") for i in range(5)]
    extract_deals(records, batch_size=2)

    assert calls == [2, 2, 1]  # 5 records chunked into batches of 2
    assert all(r["acquirer"] for r in records)
