"""Tests for src/pipeline.py — runs the real end-to-end pipeline.

Redirects config.CACHE_DIR / OUTPUT_DIR / LOGS_DIR to a tmp_path for the
duration of the test so this never overwrites the real last-known-good
dataset the Streamlit demo relies on. Uses a single query and no GDELT to
keep the real-network run fast.
"""
import json

import pytest

import config
from src import pipeline
from tests.conditions import has_network

pytestmark = pytest.mark.skipif(not has_network(), reason="no network available")


@pytest.fixture
def redirected_data_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    for d in (config.CACHE_DIR, config.OUTPUT_DIR, config.LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_run_pipeline_end_to_end(redirected_data_dirs):
    summary = pipeline.run_pipeline(queries=["FMCG acquisition"], use_gdelt=False, verbose=False)

    assert summary["raw_count"] > 0
    assert summary["cleaned_count"] <= summary["raw_count"]
    assert summary["after_dedup_count"] <= summary["cleaned_count"]
    assert summary["recent_count"] <= summary["after_dedup_count"]
    assert summary["credible_count"] <= summary["recent_count"]
    assert summary["relevant_count"] <= summary["credible_count"]
    assert summary["final_count"] == summary["relevant_count"]
    assert isinstance(summary["newsletter_markdown"], str) and len(summary["newsletter_markdown"]) > 0
    assert set(summary["output_paths"].keys()) == {"csv", "json", "docx", "xlsx", "pptx"}

    cache_path = config.CACHE_DIR / "last_known_good.json"
    assert cache_path.exists()
    with open(cache_path, encoding="utf-8") as f:
        cached = json.load(f)
    assert cached["final_count"] == summary["final_count"]


def test_load_last_known_good_reads_back_cache(redirected_data_dirs):
    pipeline.run_pipeline(queries=["FMCG acquisition"], use_gdelt=False, verbose=False)
    cached = pipeline.load_last_known_good()
    assert cached is not None
    assert "records" in cached


def test_load_last_known_good_returns_none_when_absent(redirected_data_dirs):
    assert pipeline.load_last_known_good() is None


def test_run_pipeline_safe_falls_back_to_cache_on_failure(redirected_data_dirs, monkeypatch):
    pipeline.run_pipeline(queries=["FMCG acquisition"], use_gdelt=False, verbose=False)

    def boom(*args, **kwargs):
        raise RuntimeError("simulated live-run failure")

    monkeypatch.setattr(pipeline, "run_pipeline", boom)
    summary, used_cache = pipeline.run_pipeline_safe()
    assert used_cache is True
    assert summary is not None
