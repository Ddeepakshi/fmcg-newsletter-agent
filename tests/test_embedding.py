"""Tests for src/embedding.py.

Loading all-MiniLM-L6-v2 needs network on first run (HuggingFace Hub); once
cached locally it works offline. We still guard with has_network() per the
project's policy of skipping real-dependency tests when unavailable rather
than mocking them.
"""
import pytest

from src.embedding import cosine_similarity_matrix, embed_texts
from tests.conditions import has_network

pytestmark = pytest.mark.skipif(not has_network(), reason="no network available for model load/download")


def test_embed_texts_returns_matrix_of_expected_shape():
    texts = ["ITC acquires Prasuma Foods", "Unrelated headline about tea prices"]
    embeddings = embed_texts(texts)
    assert embeddings.shape[0] == 2
    assert embeddings.shape[1] > 0


def test_similar_titles_score_higher_than_unrelated():
    texts = [
        "ITC acquires Prasuma Foods in FMCG expansion push",
        "ITC to buy Prasuma Foods, strengthening food portfolio",
        "Tea prices rise sharply amid supply concerns",
    ]
    embeddings = embed_texts(texts)
    sim = cosine_similarity_matrix(embeddings)
    assert sim[0, 1] > sim[0, 2]
    assert sim[0, 1] > 0.6
