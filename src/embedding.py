"""Embedding utilities backing semantic de-duplication.

Isolated from dedup_semantic.py so the (slow-loading) sentence-transformers
model is a single, mockable dependency boundary.
"""
import logging

import numpy as np

import config

logger = logging.getLogger(__name__)

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model %s", config.EMBEDDING_MODEL_NAME)
        _model = SentenceTransformer(config.EMBEDDING_MODEL_NAME)
    return _model


def embed_texts(texts: list) -> np.ndarray:
    """Returns an (n, dim) L2-normalized embedding matrix for `texts`."""
    model = _get_model()
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(embeddings)


def cosine_similarity_matrix(embeddings: np.ndarray) -> np.ndarray:
    """Pairwise cosine similarity. Embeddings must already be L2-normalized."""
    return embeddings @ embeddings.T


if __name__ == "__main__":
    texts = [
        "ITC acquires Prasuma Foods in FMCG expansion push",
        "ITC to buy Prasuma Foods, strengthening food portfolio",
        "Tea prices rise sharply amid supply concerns",
    ]
    emb = embed_texts(texts)
    sim = cosine_similarity_matrix(emb)
    print(sim)
