"""
Embedding-based pre-filter and semantic dedup for Zone 2 extraction.

Uses TF-IDF + cosine similarity (no ML dependencies required).
Optionally upgrades to fastembed (BGE-small) if available.

Replaces the LLM pre-filter for speed (~20ms vs ~3s per candidate)
and consistency (no LLM false negatives rejecting real laws).
"""

import re
import time
import logging
from typing import Optional

from src.zone2.config import log

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    import numpy as np
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    TfidfVectorizer = None
    cosine_similarity = None
    np = None

HAS_FASTEMBED = False
try:
    from fastembed import TextEmbedding as FastTextEmbedding
    HAS_FASTEMBED = True
except ImportError:
    FastTextEmbedding = None

_fastembed_model = None


def _get_fastembed():
    global _fastembed_model
    if _fastembed_model is None and HAS_FASTEMBED:
        try:
            _fastembed_model = FastTextEmbedding(model_name="BAAI/bge-small-en-v1.5")
            log.info("  Embedding: using fastembed (BGE-small-en-v1.5)")
        except Exception as e:
            log.warning("  Embedding: fastembed init failed: %s — falling back to TF-IDF", e)
    return _fastembed_model


def _compute_similarities_tfidf(indicator_text: str, candidate_texts: list[str]) -> list[float]:
    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),
        max_features=5000,
        sublinear_tf=True,
    )
    all_texts = [indicator_text] + candidate_texts
    tfidf = vectorizer.fit_transform(all_texts)
    sims = cosine_similarity(tfidf[0:1], tfidf[1:]).flatten()
    return [float(s) for s in sims]


def _compute_similarities_fastembed(indicator_text: str, candidate_texts: list[str]) -> list[float]:
    model = _get_fastembed()
    if model is None:
        return _compute_similarities_tfidf(indicator_text, candidate_texts)
    all_texts = [indicator_text] + candidate_texts
    embeddings = list(model.embed(all_texts))
    if len(embeddings) < 2:
        return [0.0] * len(candidate_texts)
    ind_emb = np.array(embeddings[0])
    cand_embs = np.array(embeddings[1:])
    norms = np.linalg.norm(cand_embs, axis=1, keepdims=True)
    ind_norm = np.linalg.norm(ind_emb)
    if ind_norm == 0 or (norms == 0).any():
        return [0.0] * len(candidate_texts)
    sims = (cand_embs @ ind_emb) / (norms.flatten() * ind_norm)
    return [float(s) for s in sims]


def compute_similarities(indicator_text: str, candidate_texts: list[str]) -> list[float]:
    if HAS_FASTEMBED:
        return _compute_similarities_fastembed(indicator_text, candidate_texts)
    if HAS_SKLEARN:
        return _compute_similarities_tfidf(indicator_text, candidate_texts)
    return []


def _build_indicator_text(indicator_data: dict) -> str:
    parts = [
        indicator_data.get("question", ""),
        indicator_data.get("name", ""),
    ]
    instructions = indicator_data.get("extraction_instructions", "")
    if isinstance(instructions, list):
        parts.extend(instructions)
    elif isinstance(instructions, str):
        parts.append(instructions)
    keywords = indicator_data.get("keywords", [])
    if isinstance(keywords, list):
        parts.extend(keywords)
    return " ".join(parts)


def _build_candidate_text(candidate: dict) -> str:
    title = candidate.get("title", "")
    snippet = candidate.get("snippet", "")
    return f"{title} {snippet}"


SIMILARITY_THRESHOLDS = {
    "6.1": 0.05,
    "6.2": 0.04,
    "6.3": 0.04,
    "6.4": 0.04,
    "6.5": 0.04,
    "7.1": 0.05,
    "7.2": 0.04,
    "7.3": 0.04,
    "7.4": 0.04,
    "7.5": 0.04,
}

SEMANTIC_DEDUP_THRESHOLD = 0.88


def filter_candidates(
    indicator_id: str,
    indicator_data: dict,
    candidates: list[dict],
    top_n: int = 10,
) -> list[dict]:
    """Batch pre-filter candidates using embedding similarity.

    Uses TF-IDF or fastembed to score each candidate against the indicator
    definition. Filters out candidates below a per-indicator threshold.
    Seeds (query_used == seed_url) are always kept.

    Returns candidates sorted by score, top_n max.
    """
    if not candidates:
        return []

    seeds = [c for c in candidates if c.get("query_used") == "seed_url (curated)"]
    others = [c for c in candidates if c.get("query_used") != "seed_url (curated)"]

    if not others:
        return seeds[:top_n]

    indicator_text = _build_indicator_text(indicator_data)
    candidate_texts = [_build_candidate_text(c) for c in others]

    sims = compute_similarities(indicator_text, candidate_texts)
    if not sims:
        log.info("  Embedding: no similarity engine available — keeping all candidates")
        return candidates[:top_n]

    threshold = SIMILARITY_THRESHOLDS.get(indicator_id, 0.10)

    passed = []
    for c, sim in zip(others, sims):
        c["_embedding_score"] = sim
        if sim >= threshold:
            passed.append(c)
        else:
            log.info("  x [emb %.2f < %.2f] %s", sim, threshold, _short(c.get("title", ""), 50))

    log.info("  Embedding: %d/%d passed (threshold=%.2f)", len(passed), len(others), threshold)

    passed.sort(key=lambda c: c.get("_embedding_score", 0), reverse=True)
    result = seeds + passed
    return result[:top_n]


def deduplicate_candidates(candidates: list[dict], threshold: float = SEMANTIC_DEDUP_THRESHOLD) -> list[dict]:
    """Remove near-duplicate candidates by computing pairwise similarity.

    If two candidates have cosine > threshold, keeps the higher-scored one.
    Seeds are never deduped against each other.
    """
    if len(candidates) < 2:
        return candidates

    seeds = {i for i, c in enumerate(candidates) if c.get("query_used") == "seed_url (curated)"}

    texts = [_build_candidate_text(c) for c in candidates]
    sims = compute_similarities(texts[0], texts[1:]) if len(texts) > 1 else []
    if not sims or len(sims) < len(candidates) - 1:
        return candidates

    all_texts = texts
    if HAS_FASTEMBED:
        model = _get_fastembed()
        if model:
            embs = list(model.embed(all_texts))
            emb_array = np.array(embs)
        else:
            return candidates
    elif HAS_SKLEARN:
        vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=5000, sublinear_tf=True)
        tfidf = vectorizer.fit_transform(all_texts)
        emb_array = tfidf.toarray()
    else:
        return candidates

    keep = set(range(len(candidates)))
    for i in range(len(candidates)):
        if i not in keep:
            continue
        for j in range(i + 1, len(candidates)):
            if j not in keep:
                continue
            if i in seeds and j in seeds:
                continue
            vec_i = emb_array[i].reshape(1, -1)
            vec_j = emb_array[j].reshape(1, -1)
            sim = float(cosine_similarity(vec_i, vec_j)[0, 0])
            if sim > threshold:
                score_i = candidates[i].get("_embedding_score", candidates[i].get("relevance_score", 0))
                score_j = candidates[j].get("_embedding_score", candidates[j].get("relevance_score", 0))
                if score_j > score_i:
                    keep.discard(i)
                else:
                    keep.discard(j)

    deduped = [candidates[i] for i in sorted(keep)]
    if len(deduped) < len(candidates):
        log.info("  Dedup: %d -> %d (removed %d near-duplicates)", len(candidates), len(deduped), len(candidates) - len(deduped))
    return deduped


def _short(text: str, n: int = 55) -> str:
    return text[:n] + "..." if len(text) > n else text
