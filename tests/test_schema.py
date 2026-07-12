"""Tests for src/schema.py."""
from src.schema import CSV_COLUMN_ORDER, EMPTY_RECORD, DealExtraction, new_record


def test_new_record_applies_overrides_and_defaults():
    record = new_record(title="Test", acquirer="ITC")
    assert record["title"] == "Test"
    assert record["acquirer"] == "ITC"
    assert record["source_tier"] == 3  # untouched default
    assert set(record.keys()) == set(EMPTY_RECORD.keys())


def test_deal_extraction_to_dict():
    extraction = DealExtraction(acquirer="ITC", target="Prasuma", deal_type="Acquisition", deal_value=150.0, currency="USD")
    d = extraction.to_dict()
    assert d == {"acquirer": "ITC", "target": "Prasuma", "deal_type": "Acquisition", "deal_value": 150.0, "currency": "USD"}


def test_csv_column_order_matches_schema_minus_query_tag():
    assert set(CSV_COLUMN_ORDER) == set(EMPTY_RECORD.keys()) - {"query_tag"}
