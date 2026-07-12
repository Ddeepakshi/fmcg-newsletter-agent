"""Stage: Structured Deal Extraction (spec section 8).

Converts each surviving article into normalized acquirer/target/deal_type/
deal_value/currency fields via constrained Groq JSON calls, so the CSV/JSON
deliverable is genuinely structured data rather than raw headlines.

Records are extracted in chunks of config.LLM_BATCH_SIZE — one Groq request
per chunk — rather than one request per article. If a batch call fails, its
articles keep empty deal fields and stay in the dataset (title/snippet/
source still usable for the extractive newsletter fallback) rather than
being dropped outright.

Extracted fields are validated before being written: a deal_type outside
the known set is rejected (nulled) rather than passed through as whatever
string the model produced, and a deal_value is rejected unless it's a
positive, finite number — the LLM is instructed not to guess, but a
constrained JSON schema doesn't stop it from hallucinating a type name or a
nonsensical value, so this stage is the actual enforcement point.
"""
import logging
import math

import config
from src.llm_client import LLMUnavailableError, extract_deals_batch

logger = logging.getLogger(__name__)

_ALLOWED_DEAL_TYPES = {"acquisition", "merger", "investment", "funding", "stake", "buyout"}


def _normalize_deal_type(value):
    if not value or not isinstance(value, str):
        return None
    lowered = value.strip().lower()
    for allowed in _ALLOWED_DEAL_TYPES:
        if allowed in lowered:
            return allowed.capitalize()
    logger.warning("Rejecting unrecognized deal_type %r (not in %s)", value, sorted(_ALLOWED_DEAL_TYPES))
    return None


def _normalize_deal_value(value):
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed <= 0:
        logger.warning("Rejecting invalid deal_value %r (must be a positive, finite number)", value)
        return None
    return parsed


def _apply_extraction(record: dict, extracted: dict) -> dict:
    record["acquirer"] = extracted.get("acquirer") or None
    record["target"] = extracted.get("target") or None
    record["deal_type"] = _normalize_deal_type(extracted.get("deal_type"))
    record["deal_value"] = _normalize_deal_value(extracted.get("deal_value"))
    currency = extracted.get("currency")
    record["currency"] = currency.strip().upper() if isinstance(currency, str) and currency.strip() else None
    return record


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def extract_deal_for_record(record: dict) -> dict:
    """Single-article convenience wrapper around extract_deals_batch (see extract_deals)."""
    try:
        results = extract_deals_batch([{"index": 0, "title": record.get("title", ""), "snippet": record.get("snippet", "")}])
    except LLMUnavailableError:
        logger.warning("Extraction unavailable for %r; leaving deal fields empty", record.get("url"))
        return record

    extracted = results.get(0)
    if extracted:
        _apply_extraction(record, extracted)
    return record


def extract_deals(records: list, batch_size: int = None) -> list:
    """Batch-extracts deal fields for every record, config.LLM_BATCH_SIZE at a time."""
    batch_size = batch_size or config.LLM_BATCH_SIZE
    extracted_count = 0
    llm_batches = 0

    for chunk in _chunks(records, batch_size):
        items = [{"index": i, "title": r.get("title", ""), "snippet": r.get("snippet", "")} for i, r in enumerate(chunk)]
        llm_batches += 1
        try:
            results = extract_deals_batch(items)
        except LLMUnavailableError:
            logger.warning("Extraction unavailable for a batch of %d article(s); leaving deal fields empty", len(chunk))
            continue

        for i, r in enumerate(chunk):
            extracted = results.get(i)
            if not extracted:
                continue
            _apply_extraction(r, extracted)
            if r.get("acquirer") or r.get("target"):
                extracted_count += 1

    logger.info(
        "Structured extraction: %d/%d records got acquirer/target populated across %d Groq call(s)",
        extracted_count, len(records), llm_batches,
    )
    return records


if __name__ == "__main__":
    import json

    sample = [
        {"title": "ITC to acquire Prasuma Foods for $150 million", "snippet": "Deal expected to close in Q3",
         "url": "https://a.com/1"},
    ]
    print(json.dumps(extract_deals(sample), indent=2))
