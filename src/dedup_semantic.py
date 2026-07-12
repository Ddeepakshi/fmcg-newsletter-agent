"""Stage: De-duplication, Stage 2 — semantic match.

Runs on whatever survives the exact/fuzzy pass (dedup_exact.py). Embeds each
remaining article's title with MiniLM and merges pairs above the configured
cosine-similarity threshold, since these are near-certainly covering the same
underlying deal even when wording differs substantially.
"""
import logging

import config
from src.dedup_common import build_duplicate_entry, pick_canonical
from src.embedding import cosine_similarity_matrix, embed_texts

logger = logging.getLogger(__name__)


def dedup_semantic(records: list, threshold: float = None) -> tuple:
    """Returns (survivors, duplicate_log_entries)."""
    threshold = threshold if threshold is not None else config.DEDUP_SIMILARITY_THRESHOLD

    if len(records) < 2:
        return records, []

    texts = [f"{r.get('title', '')}. {r.get('snippet', '')}".strip() for r in records]
    embeddings = embed_texts(texts)
    sim = cosine_similarity_matrix(embeddings)

    absorbed = [False] * len(records)
    current_records = list(records)
    dup_log = []

    for i in range(len(records)):
        if absorbed[i]:
            continue
        for j in range(i + 1, len(records)):
            if absorbed[j]:
                continue
            score = float(sim[i, j])
            if score >= threshold:
                canonical, duplicate = pick_canonical(current_records[i], current_records[j])
                current_records[i] = canonical
                absorbed[j] = True
                dup_log.append(
                    build_duplicate_entry(canonical, duplicate, method="semantic_embedding", score=score)
                )

    survivors = [r for r, gone in zip(current_records, absorbed) if not gone]
    logger.info("Semantic merge: %d -> %d", len(records), len(survivors))
    return survivors, dup_log


if __name__ == "__main__":
    import json

    sample = [
        {"title": "ITC acquires Prasuma Foods in FMCG expansion push", "snippet": "",
         "url": "https://a.com/1", "source_tier": 1, "published_date": "2026-07-10"},
        {"title": "ITC to buy Prasuma Foods, strengthening food portfolio", "snippet": "",
         "url": "https://b.com/2", "source_tier": 2, "published_date": "2026-07-10"},
        {"title": "Tea prices rise sharply amid supply concerns", "snippet": "",
         "url": "https://c.com/3", "source_tier": 3, "published_date": "2026-07-09"},
    ]
    survivors, dups = dedup_semantic(sample)
    print("Survivors:", json.dumps(survivors, indent=2))
    print("Duplicates logged:", json.dumps(dups, indent=2))
