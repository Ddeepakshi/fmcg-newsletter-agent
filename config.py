"""Central configuration for the FMCG Deal Intelligence pipeline.

All tunable constants live here so behavior can be adjusted without touching
pipeline logic. Values are overridable via environment variables / .env.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
LOGS_DIR = DATA_DIR / "logs"
OUTPUT_DIR = DATA_DIR / "output"
for d in (CACHE_DIR, LOGS_DIR, OUTPUT_DIR):
    d.mkdir(parents=True, exist_ok=True)

# --- LLM (Groq) ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
# Fast/cheap model for binary relevance classification.
GROQ_MODEL_FAST = os.getenv("GROQ_MODEL_FAST", "llama-3.1-8b-instant")
# Stronger model for structured extraction and newsletter drafting.
GROQ_MODEL_STRONG = os.getenv("GROQ_MODEL_STRONG", "llama-3.3-70b-versatile")
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))
# Rule-based filtering (keywords, recency, credibility) runs first to shrink
# the dataset; whatever survives is classified/extracted in batches of this
# size rather than one Groq request per article, to stay well clear of the
# free-tier rate limit.
LLM_BATCH_SIZE = int(os.getenv("LLM_BATCH_SIZE", "40"))

# --- Recency ---
# 7 days was cutting an 88-relevant-article funnel down to 4 survivors —
# widened so the newsletter has enough material to be worth reading.
RECENCY_DAYS = int(os.getenv("RECENCY_DAYS", "14"))

# --- De-duplication ---
DEDUP_SIMILARITY_THRESHOLD = float(os.getenv("DEDUP_SIMILARITY_THRESHOLD", "0.85"))
# Stage 1 (RapidFuzz) near-exact match threshold on normalized titles, 0-100 scale.
FUZZY_TITLE_THRESHOLD = float(os.getenv("FUZZY_TITLE_THRESHOLD", "92"))
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")

# --- Credibility scoring ---
CREDIBILITY_THRESHOLD = float(os.getenv("CREDIBILITY_THRESHOLD", "0.5"))

SOURCE_TIER_WEIGHTS = {1: 1.0, 2: 0.6, 3: 0.3}

# Starter tier list — extendable. Matched case-insensitively against the
# article's `source` field (publisher name).
SOURCE_TIERS = {
    1: [
        "reuters", "bloomberg", "economic times", "mint", "business standard",
        "the hindu businessline", "livemint", "financial express",
    ],
    2: [
        "moneycontrol", "business today", "cnbc", "forbes india", "vccircle",
        "entrackr", "inc42", "livemint", "the economic times", "ft.com",
        "wall street journal", "techcrunch",
    ],
    # Anything not matched above falls back to tier 3.
}

CREDIBILITY_WEIGHTS = {
    "source_tier": 0.35,
    "has_company_names": 0.20,
    "has_deal_value": 0.20,
    "recency": 0.15,
    "completeness": 0.10,
}

# --- Relevance filtering ---
FMCG_INDUSTRY_KEYWORDS = [
    "fmcg", "consumer goods", "food", "beverage", "dairy", "snack", "snacks",
    "personal care", "cosmetics", "household products", "home care",
    "packaged food", "confectionery", "beauty", "hygiene", "nutraceutical",
    "d2c", "cpg",
]

DEAL_TYPE_KEYWORDS = [
    "acquisition", "acquire", "acquires", "merger", "merge", "investment",
    "invests", "funding", "fund round", "strategic stake", "stake", "buyout",
    "raises", "raised", "series a", "series b", "series c", "stake sale",
]

EXCLUDE_KEYWORDS = [
    "product launch", "launches new", "appoints", "appointment", "steps down",
    "resigns", "advertisement", "ad campaign", "marketing campaign",
]

# --- Region tagging ---
INDIA_KEYWORDS = [
    "india", "indian", "mumbai", "delhi", "bengaluru", "bangalore", "pune",
    "chennai", "hyderabad", "gurugram", "gurgaon", "rupee", "inr", "crore",
    "lakh",
]

# --- News source queries ---
# Trimmed from 8 to 5 focused queries — fewer Google News round-trips per
# run without materially narrowing FMCG deal-type/industry coverage.
SEARCH_QUERIES = [
    "FMCG acquisition",
    "consumer goods merger",
    "food and beverage investment",
    "personal care acquisition",
    "beauty brand funding",
]

GOOGLE_NEWS_RSS_TEMPLATE = (
    "https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
)
GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"

# Extensible: add company investor-relations / press-release RSS feed URLs here.
# Each entry is fetched as-is and tagged query_tag="press_release".
PRESS_RELEASE_RSS_FEEDS = []

REQUEST_TIMEOUT_SECONDS = 15
REQUEST_MAX_RETRIES = 3

# A daily/6-hourly newsletter doesn't need hundreds of raw articles per
# query — cap each source client-side to keep runs fast and the funnel small.
GOOGLE_NEWS_MAX_RESULTS = 20
GDELT_MAX_RESULTS = 15

# GDELT's free API is aggressively rate-limited by IP and often just hangs
# or 429s — fail fast with a short timeout and a single attempt rather than
# retrying a source that's unlikely to recover within the same run.
GDELT_TIMEOUT_SECONDS = 8
GDELT_MAX_RETRIES = 1

# Matches the top-N-by-credibility cap used by the extractive newsletter
# fallback (src/newsletter_generator.py) — kept here so the pipeline summary
# banner can report the same number without duplicating the constant.
NEWSLETTER_TOP_N = 15

# --- Data schema fields (see README section 6) ---
SCHEMA_FIELDS = [
    "title", "snippet", "source", "source_tier", "published_date", "url",
    "region", "is_duplicate_of", "credibility_score", "acquirer", "target",
    "deal_type", "deal_value", "currency", "relevance_flag",
]


if __name__ == "__main__":
    assert sum(SOURCE_TIER_WEIGHTS.values()) > 0
    assert abs(sum(CREDIBILITY_WEIGHTS.values()) - 1.0) < 1e-9, "credibility weights should sum to 1.0"
    assert RECENCY_DAYS > 0
    assert 0 <= DEDUP_SIMILARITY_THRESHOLD <= 1
    assert 0 <= CREDIBILITY_THRESHOLD <= 1
    assert GOOGLE_NEWS_MAX_RESULTS > 0 and GDELT_MAX_RESULTS > 0
    assert GDELT_TIMEOUT_SECONDS < REQUEST_TIMEOUT_SECONDS, "GDELT should fail fast relative to the general timeout"
    assert LLM_BATCH_SIZE > 0
    for d in (CACHE_DIR, LOGS_DIR, OUTPUT_DIR):
        assert d.exists(), f"{d} should have been created on import"

    print(f"GROQ_API_KEY set: {bool(GROQ_API_KEY)}")
    print(f"RECENCY_DAYS={RECENCY_DAYS} DEDUP_SIMILARITY_THRESHOLD={DEDUP_SIMILARITY_THRESHOLD} "
          f"CREDIBILITY_THRESHOLD={CREDIBILITY_THRESHOLD}")
    print(f"{len(SEARCH_QUERIES)} search queries, {len(FMCG_INDUSTRY_KEYWORDS)} industry keywords, "
          f"{len(DEAL_TYPE_KEYWORDS)} deal-type keywords")
    print("config: all assertions passed")
