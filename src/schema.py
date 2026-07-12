"""Canonical article/deal record shape used across every pipeline stage.

Every stage reads and writes dicts shaped like `EMPTY_RECORD`, so modules can
be tested independently by handing them plain dicts/lists of dicts.
"""
from dataclasses import asdict, dataclass
from typing import Optional

EMPTY_RECORD = {
    "title": "",
    "snippet": "",
    "source": "",
    "source_tier": 3,
    "published_date": "",  # ISO 8601
    "url": "",
    "query_tag": "",
    "region": "Other",  # India / Global / Other
    "is_duplicate_of": None,
    "credibility_score": None,
    "acquirer": None,
    "target": None,
    "deal_type": None,
    "deal_value": None,
    "currency": None,
    "relevance_flag": None,  # Relevant / Not Relevant / Ambiguous-LLM-Reviewed
}


def new_record(**overrides) -> dict:
    record = dict(EMPTY_RECORD)
    record.update(overrides)
    return record


@dataclass
class DealExtraction:
    """Structured output contract for the LLM extraction stage (section 8)."""

    acquirer: Optional[str] = None
    target: Optional[str] = None
    deal_type: Optional[str] = None
    deal_value: Optional[float] = None
    currency: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


CSV_COLUMN_ORDER = [
    "title", "snippet", "source", "source_tier", "published_date", "url",
    "region", "is_duplicate_of", "credibility_score", "acquirer", "target",
    "deal_type", "deal_value", "currency", "relevance_flag",
]


if __name__ == "__main__":
    record = new_record(title="Test", acquirer="ITC")
    assert record["title"] == "Test"
    assert record["acquirer"] == "ITC"
    assert record["source_tier"] == 3  # default preserved
    assert set(record.keys()) == set(EMPTY_RECORD.keys())

    extraction = DealExtraction(acquirer="ITC", target="Prasuma", deal_type="Acquisition", deal_value=150.0, currency="USD")
    d = extraction.to_dict()
    assert d["acquirer"] == "ITC" and d["deal_value"] == 150.0

    assert set(CSV_COLUMN_ORDER) == set(EMPTY_RECORD.keys()) - {"query_tag"}

    print("schema: all assertions passed")
