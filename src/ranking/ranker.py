from __future__ import annotations

from typing import Dict

import numpy as np

from src.config import get_logger
from src.features.engineering import CandidateFeatureVector

logger = get_logger("ranker")

# Saturating caps used to squash each unbounded numeric feature into [0, 1]
# before weighting. Features that are already ratios/booleans in [0, 1] use
# a cap of 1.0 (a no-op clip). This mirrors the notebook's per-batch
# min-max normalization, but works for a single upload where there is no
# batch to normalize against (LightGBM's LambdaRank needs >=3 JDs with
# >=3 candidates each to train meaningfully — see the execution plan,
# Stage 3 — so this heuristic scorer is the v1 default, not a fallback).
_FEATURE_CAPS: Dict[str, float] = {
    "total_experience_months": 240.0,
    "num_positions": 10.0,
    "avg_tenure_months": 60.0,
    "is_currently_employed": 1.0,
    "max_seniority_score": 5.0,
    "has_experience": 1.0,
    "num_degrees": 3.0,
    "highest_degree_level": 5.0,
    "gpa_normalized": 1.0,
    "has_gpa": 1.0,
    "is_currently_studying": 1.0,
    "num_institutions": 3.0,
    "total_canonical_skills": 30.0,
    "high_confidence_skill_ratio": 1.0,
    "unmatched_skill_ratio": 1.0,  # inverted below — high is bad
    "category_diversity": 10.0,
    "primary_domain_confidence": 1.0,
    "avg_skill_confidence": 1.0,
    "num_projects": 10.0,
    "avg_technologies_per_project": 10.0,
    "project_link_ratio": 1.0,
    "has_projects": 1.0,
    "num_certifications": 10.0,
    "num_unique_issuers": 5.0,
    "has_certifications": 1.0,
    "summary_embedding_norm": 1.5,
    "skills_text_embedding_norm": 1.5,
    "summary_skills_semantic_consistency": 1.0,  # remapped from [-1,1] below
}

# Features where a larger raw value is a *negative* signal.
_INVERTED_FEATURES = {"unmatched_skill_ratio"}


def _normalize_feature(name: str, value: float) -> float:
    if name == "summary_skills_semantic_consistency":
        normalized = (value + 1.0) / 2.0
    else:
        cap = _FEATURE_CAPS.get(name, 1.0)
        normalized = value / cap if cap > 0 else 0.0
    normalized = float(np.clip(normalized, 0.0, 1.0))
    if name in _INVERTED_FEATURES:
        normalized = 1.0 - normalized
    return normalized


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


class HeuristicRanker:
    """
    Transparent weighted-sum scorer: semantic (resume <-> JD) similarity
    carries 60% of the score, the fused numeric feature signals share the
    remaining 40% evenly. Every term is auditable, which is what
    src/explainability builds its narrative on top of.
    """

    similarity_weight: float = 0.6
    feature_weight: float = 0.4

    def score(self, features: CandidateFeatureVector, resume_emb: np.ndarray, jd_emb: np.ndarray) -> Dict[str, float]:
        similarity = _cosine_similarity(resume_emb, jd_emb)
        similarity_normalized = float(np.clip((similarity + 1.0) / 2.0, 0.0, 1.0))

        feature_names = features.feature_names
        per_feature_weight = self.feature_weight / max(1, len(feature_names))

        contributions: Dict[str, float] = {
            "retrieval_similarity": round(similarity_normalized * self.similarity_weight, 4)
        }
        for name in feature_names:
            normalized_value = _normalize_feature(name, features.features[name])
            contributions[name] = round(normalized_value * per_feature_weight, 4)

        total = round(sum(contributions.values()), 4)
        return {"score": total, "raw_similarity": round(similarity, 4), "contributions": contributions}


_ranker = HeuristicRanker()


def rank(features: CandidateFeatureVector, resume_emb: np.ndarray, jd_emb: np.ndarray) -> float:
    """The Stage 3 pipeline contract: fused features + both embeddings in,
    a single 0-1 ATS match score out."""
    result = _ranker.score(features, resume_emb, jd_emb)
    logger.info(f"Scored candidate: {result['score']} (raw_similarity={result['raw_similarity']})")
    return result["score"]


def rank_with_breakdown(features: CandidateFeatureVector, resume_emb: np.ndarray, jd_emb: np.ndarray) -> Dict[str, float]:
    """Same as rank(), but also returns the per-signal contribution
    breakdown — used by src/explainability."""
    return _ranker.score(features, resume_emb, jd_emb)
