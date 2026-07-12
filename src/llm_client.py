"""Thin wrapper around the Groq API.

Centralizes retry/backoff and the three LLM-backed operations the pipeline
needs: relevance classification, structured deal extraction, and newsletter
drafting. Every public function degrades gracefully (returns None / raises a
typed error) so calling stages can implement their documented fallbacks
instead of crashing the whole run.

Relevance classification and extraction are batched — one Groq request
covers many articles (a JSON array in, a JSON array out) rather than one
request per article, since rule-based filtering (keywords, recency,
credibility) already does the heavy lifting of shrinking the dataset before
any article reaches the LLM. The single-article `classify_relevance`/
`extract_deal` wrappers exist for convenience/testing and are themselves
just 1-item batches — there's only one real implementation of each call.

Both JSON-mode calls go through `_chat_json`, which retries with a fresh LLM
call (not a re-parse) if the response isn't valid JSON or doesn't match the
expected shape — a malformed response is treated as retryable flakiness,
distinct from a genuine API failure (which `_chat`'s own retry covers).
"""
import json
import logging

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

import config

logger = logging.getLogger(__name__)

_client = None


class LLMUnavailableError(Exception):
    """Raised when Groq cannot be reached/authenticated after retries."""


class _MalformedResponseError(Exception):
    """Internal: the model's response wasn't valid JSON, or didn't match the
    requested shape. Retried with a fresh LLM call (not a re-parse of the
    same broken output) before giving up as LLMUnavailableError.
    """


def _get_client():
    global _client
    if _client is None:
        from groq import Groq

        _client = Groq(api_key=config.GROQ_API_KEY)
    return _client


def _ensure_configured():
    """Fails fast on missing config, before entering the retry-wrapped call —
    a missing API key is not a transient failure and retrying it just adds
    ~15-20s of pointless backoff per call.
    """
    if not config.GROQ_API_KEY:
        raise LLMUnavailableError("GROQ_API_KEY is not set")


def _retryable():
    return retry(
        reraise=True,
        stop=stop_after_attempt(config.LLM_MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=20),
        retry=retry_if_exception_type(Exception),
    )


@_retryable()
def _chat(model: str, messages: list, json_mode: bool = False, temperature: float = 0.0) -> str:
    client = _get_client()
    kwargs = {}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    completion = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        **kwargs,
    )
    return completion.choices[0].message.content


def _malformed_retryable():
    return retry(
        reraise=True,
        stop=stop_after_attempt(config.LLM_MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(_MalformedResponseError),
    )


@_malformed_retryable()
def _chat_json(model: str, messages: list, required_key: str, temperature: float = 0.0) -> dict:
    """Calls the LLM in JSON mode and validates the response shape.

    Retries with a FRESH LLM call (not a re-parse of the same broken text)
    if the response isn't valid JSON or is missing `required_key` as a list
    — a malformed response is exactly the kind of transient LLM flakiness
    retries are meant to smooth over, distinct from a genuine API failure
    (which `_chat`'s own retry already covers).
    """
    raw = _chat(model, messages, json_mode=True, temperature=temperature)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _MalformedResponseError(f"non-JSON response: {exc}") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get(required_key), list):
        raise _MalformedResponseError(f"response missing a {required_key!r} array")
    return parsed


def classify_relevance_batch(items: list) -> dict:
    """Classifies many articles in a single Groq request.

    `items`: list of {"index": int, "title": str, "snippet": str}.
    Returns {index: "Relevant"|"Not Relevant"} for every index the response
    actually covered — a missing index means the model's JSON didn't address
    that article (parse gap), which callers treat as "unreviewed" rather
    than silently assuming either verdict.
    Raises LLMUnavailableError if the call itself fails. Returns {} for an
    empty `items` list without making a request.
    """
    if not items:
        return {}
    _ensure_configured()

    prompt = (
        "You are a strict classifier for an FMCG (fast-moving consumer goods) "
        "deal newsletter. For EACH article below, decide if it describes a "
        "genuine FMCG deal: an M&A transaction, majority/minority investment, "
        "funding round, strategic stake, or buyout involving a food, beverage, "
        "dairy, personal care, cosmetics, or household products company.\n\n"
        "Exclude: product launches, marketing news, leadership/personnel "
        "changes, and deals in unrelated industries.\n\n"
        f"Articles (JSON):\n{json.dumps(items, indent=2)}\n\n"
        "Respond with ONLY JSON matching exactly this shape — one entry per "
        "article, in any order:\n"
        '{"results": [{"index": <int>, "verdict": "Relevant" or "Not Relevant"}, ...]}'
    )
    try:
        parsed = _chat_json(config.GROQ_MODEL_FAST, [{"role": "user", "content": prompt}], required_key="results")
    except Exception as exc:
        raise LLMUnavailableError(str(exc)) from exc

    return {
        entry["index"]: entry.get("verdict")
        for entry in parsed.get("results", [])
        if isinstance(entry, dict) and "index" in entry
    }


def classify_relevance(title: str, snippet: str) -> str:
    """Single-article convenience wrapper around classify_relevance_batch."""
    verdicts = classify_relevance_batch([{"index": 0, "title": title, "snippet": snippet}])
    return "Relevant" if verdicts.get(0) == "Relevant" else "Not Relevant"


EXTRACTION_SCHEMA_HINT = {
    "acquirer": "string or null - the company making the acquisition/investment",
    "target": "string or null - the company being acquired/invested in",
    "deal_type": "one of: Acquisition, Merger, Investment, Funding, Stake, Buyout, or null",
    "deal_value": "number or null - the disclosed deal value, numeric only (no currency symbol)",
    "currency": "ISO currency code string or null (e.g. USD, INR)",
}


def extract_deals_batch(items: list) -> dict:
    """Extracts structured deal fields for many articles in a single Groq request.

    `items`: list of {"index": int, "title": str, "snippet": str}.
    Returns {index: {acquirer, target, deal_type, deal_value, currency}} for
    every index the response actually covered — missing indices mean the
    model's JSON didn't address that article.
    Raises LLMUnavailableError if the call itself fails. Returns {} for an
    empty `items` list without making a request.
    """
    if not items:
        return {}
    _ensure_configured()

    prompt = (
        "Extract structured deal information from EACH FMCG news article "
        "below. Use null for anything not stated — do not guess.\n\n"
        f"Field meanings: {json.dumps(EXTRACTION_SCHEMA_HINT, indent=2)}\n\n"
        "Respond with ONLY JSON matching exactly this shape — one entry per "
        "article, in any order:\n"
        '{"results": [{"index": <int>, "acquirer": ..., "target": ..., '
        '"deal_type": ..., "deal_value": ..., "currency": ...}, ...]}\n\n'
        f"Articles (JSON):\n{json.dumps(items, indent=2)}"
    )
    try:
        parsed = _chat_json(config.GROQ_MODEL_STRONG, [{"role": "user", "content": prompt}], required_key="results")
    except Exception as exc:
        raise LLMUnavailableError(str(exc)) from exc

    return {
        entry["index"]: entry
        for entry in parsed.get("results", [])
        if isinstance(entry, dict) and "index" in entry
    }


def extract_deal(title: str, snippet: str) -> dict:
    """Single-article convenience wrapper around extract_deals_batch."""
    results = extract_deals_batch([{"index": 0, "title": title, "snippet": snippet}])
    return results.get(0) or {field: None for field in EXTRACTION_SCHEMA_HINT}


def generate_newsletter(deal_records: list) -> str:
    """Drafts the newsletter from structured deal records. Raises LLMUnavailableError on failure."""
    _ensure_configured()
    slim = [
        {
            "title": r.get("title"),
            "acquirer": r.get("acquirer"),
            "target": r.get("target"),
            "deal_type": r.get("deal_type"),
            "deal_value": r.get("deal_value"),
            "currency": r.get("currency"),
            "region": r.get("region"),
            "source": r.get("source"),
            "url": r.get("url"),
            "published_date": r.get("published_date"),
        }
        for r in deal_records
    ]
    prompt = (
        "You are drafting a concise business newsletter for FMCG industry "
        "professionals summarizing recent deal activity. Using ONLY the "
        "structured deal records below (do not invent facts not present), "
        "write a newsletter in Markdown with these sections:\n"
        "1. Major M&A Deals\n2. Investment Highlights\n3. Emerging Trends\n"
        "4. Key Takeaways\n\n"
        "For every deal mentioned, cite the source name and include the URL "
        "as a Markdown link. Keep it concise and business-toned.\n\n"
        f"Deal records (JSON):\n{json.dumps(slim, indent=2)}"
    )
    try:
        return _chat(
            config.GROQ_MODEL_STRONG,
            [{"role": "user", "content": prompt}],
            temperature=0.3,
        )
    except Exception as exc:
        raise LLMUnavailableError(str(exc)) from exc


if __name__ == "__main__":
    sample = [
        {"title": "ITC to acquire Prasuma Foods for $150 million", "snippet": "Deal expected to close in Q3",
         "acquirer": "ITC", "target": "Prasuma Foods", "deal_value": 150, "currency": "USD",
         "region": "India", "source": "Economic Times", "url": "https://a.com/1",
         "published_date": "2026-07-11"},
    ]

    batch_items = [{"index": 0, "title": sample[0]["title"], "snippet": sample[0]["snippet"]}]

    if not config.GROQ_API_KEY:
        print("GROQ_API_KEY not set — exercising the documented fallback path (expected).")
        for name, fn in [
            ("classify_relevance", lambda: classify_relevance(sample[0]["title"], sample[0]["snippet"])),
            ("classify_relevance_batch", lambda: classify_relevance_batch(batch_items)),
            ("extract_deal", lambda: extract_deal(sample[0]["title"], sample[0]["snippet"])),
            ("extract_deals_batch", lambda: extract_deals_batch(batch_items)),
            ("generate_newsletter", lambda: generate_newsletter(sample)),
        ]:
            try:
                fn()
                print(f"{name}: unexpectedly succeeded without a key")
            except LLMUnavailableError:
                print(f"{name}: raised LLMUnavailableError as expected")
    else:
        print("classify_relevance:", classify_relevance(sample[0]["title"], sample[0]["snippet"]))
        print("classify_relevance_batch:", classify_relevance_batch(batch_items))
        print("extract_deal:", extract_deal(sample[0]["title"], sample[0]["snippet"]))
        print("extract_deals_batch:", extract_deals_batch(batch_items))
        print("generate_newsletter:\n", generate_newsletter(sample))
