"""Tests for config.py — validates invariants the rest of the pipeline relies on."""
import config


def test_credibility_weights_sum_to_one():
    assert abs(sum(config.CREDIBILITY_WEIGHTS.values()) - 1.0) < 1e-9


def test_thresholds_in_valid_range():
    assert config.RECENCY_DAYS > 0
    assert 0 <= config.DEDUP_SIMILARITY_THRESHOLD <= 1
    assert 0 <= config.CREDIBILITY_THRESHOLD <= 1
    assert 0 <= config.FUZZY_TITLE_THRESHOLD <= 100


def test_fetch_limits_and_timeouts_are_sane():
    assert config.GOOGLE_NEWS_MAX_RESULTS > 0
    assert config.GDELT_MAX_RESULTS > 0
    assert config.GDELT_TIMEOUT_SECONDS < config.REQUEST_TIMEOUT_SECONDS
    assert config.GDELT_MAX_RETRIES >= 1
    assert config.NEWSLETTER_TOP_N > 0
    assert config.LLM_BATCH_SIZE > 0


def test_source_tier_weights_cover_all_tiers():
    assert set(config.SOURCE_TIER_WEIGHTS.keys()) == {1, 2, 3}
    assert config.SOURCE_TIER_WEIGHTS[1] > config.SOURCE_TIER_WEIGHTS[2] > config.SOURCE_TIER_WEIGHTS[3]


def test_keyword_lists_non_empty():
    assert len(config.FMCG_INDUSTRY_KEYWORDS) > 0
    assert len(config.DEAL_TYPE_KEYWORDS) > 0
    assert len(config.SEARCH_QUERIES) > 0


def test_data_dirs_created_on_import():
    for d in (config.CACHE_DIR, config.LOGS_DIR, config.OUTPUT_DIR):
        assert d.exists()
