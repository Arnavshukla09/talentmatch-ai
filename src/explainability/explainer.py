from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from src.config import get_logger
from src.embeddings.generator import embed_batch
from src.features.engineering import CandidateFeatureVector
from src.parsing.schema import ResumeSchema
from src.skills.extractor import SkillExtractionResult
from src.skills.taxonomy import load_or_seed_taxonomy

logger = get_logger("explainer")


def _full_skill_vocab() -> List[str]:
    """All canonical skill names known to the taxonomy — used as the pool
    of skills a JD might be asking for, independent of what this
    particular candidate happens to have."""
    taxonomy = load_or_seed_taxonomy()
    return [entry.canonical_name for entry in taxonomy.skills]


@dataclass
class SkillGapResult:
    matched_skills: List[str]
    missing_skills: List[str]
    partial_matches: List[Tuple[str, str, float]]
    match_ratio: float


class SkillGapAnalyzer:
    """
    Extracts which of the candidate's canonical skills the JD text
    actually mentions, then embeds any still-missing JD skills against the
    candidate's skill list to catch near-synonyms ("LLM orchestration" ~
    "LangChain") before calling them a true gap.
    """

    def __init__(self, partial_match_threshold: float = 0.55) -> None:
        self.partial_match_threshold = partial_match_threshold

    @staticmethod
    def _extract_jd_skills(jd_text: str, canonical_skill_vocab: List[str]) -> List[str]:
        jd_lower = jd_text.lower()
        return [skill for skill in canonical_skill_vocab if skill.lower() in jd_lower]

    def analyze(self, candidate_skills: List[str], jd_text: str) -> SkillGapResult:
        jd_skills = self._extract_jd_skills(jd_text, _full_skill_vocab())
        candidate_skills_set = {s.lower() for s in candidate_skills}
        jd_skills_set = {s.lower() for s in jd_skills}

        matched = sorted(candidate_skills_set & jd_skills_set)
        missing = sorted(jd_skills_set - candidate_skills_set)

        partial_matches: List[Tuple[str, str, float]] = []
        remaining_missing: List[str] = []

        if missing and candidate_skills:
            candidate_list = list(candidate_skills_set)
            candidate_embeddings = embed_batch(candidate_list)
            missing_embeddings = embed_batch(missing)

            for i, missing_skill in enumerate(missing):
                similarities = candidate_embeddings @ missing_embeddings[i]
                best_idx = int(np.argmax(similarities))
                best_score = float(similarities[best_idx])
                if best_score >= self.partial_match_threshold:
                    partial_matches.append((missing_skill, candidate_list[best_idx], round(best_score, 4)))
                else:
                    remaining_missing.append(missing_skill)
        else:
            remaining_missing = missing

        total_required = len(jd_skills_set) if jd_skills_set else 1
        match_ratio = round(len(matched) / total_required, 4)

        return SkillGapResult(
            matched_skills=matched,
            missing_skills=remaining_missing,
            partial_matches=partial_matches,
            match_ratio=match_ratio,
        )


def _top_contributions(contributions: Dict[str, float], positive: bool, top_n: int = 3) -> List[Tuple[str, float]]:
    filtered = [(k, v) for k, v in contributions.items() if (v > 0) == positive and k != "retrieval_similarity"]
    filtered.sort(key=lambda item: abs(item[1]), reverse=True)
    return filtered[:top_n]


def _build_narrative(
    score: float,
    contributions: Dict[str, float],
    skill_gap: Optional[SkillGapResult],
) -> str:
    sentence_parts = [f"ATS match score: {score:.2f} (0-1 scale)."]

    top_positive = _top_contributions(contributions, positive=True)
    if top_positive:
        drivers = ", ".join(name for name, _ in top_positive)
        sentence_parts.append(f"Strongest signals: {drivers}.")

    if skill_gap is not None:
        if skill_gap.matched_skills:
            preview = ", ".join(skill_gap.matched_skills[:5])
            sentence_parts.append(f"Matches {len(skill_gap.matched_skills)} required skill(s), including {preview}.")
        if skill_gap.missing_skills:
            preview = ", ".join(skill_gap.missing_skills[:5])
            sentence_parts.append(f"Missing from the resume: {preview}.")
        if skill_gap.partial_matches:
            preview = ", ".join(f"{jd_skill}~{cand_skill}" for jd_skill, cand_skill, _ in skill_gap.partial_matches[:3])
            sentence_parts.append(f"Related/partial matches: {preview}.")

    return " ".join(sentence_parts)


def explain(
    score: float,
    features: CandidateFeatureVector,
    *,
    contributions: Optional[Dict[str, float]] = None,
    resume: Optional[ResumeSchema] = None,
    skills: Optional[SkillExtractionResult] = None,
    job_description_text: Optional[str] = None,
) -> dict:
    """
    The Stage 3 pipeline contract: score + fused features in, a
    human-readable explanation dict out. `contributions`, `resume`,
    `skills`, and `job_description_text` are optional but strongly
    recommended — without them the explanation is limited to the raw
    feature values.
    """
    contributions = contributions or {}

    skill_gap: Optional[SkillGapResult] = None
    if skills is not None and job_description_text:
        candidate_skill_names = [s.canonical_name for s in skills.canonical_skills]
        skill_gap = SkillGapAnalyzer().analyze(candidate_skill_names, job_description_text)

    narrative = _build_narrative(score, contributions, skill_gap)

    result = {
        "score": round(score, 4),
        "narrative_summary": narrative,
        "feature_values": features.features,
        "feature_contributions": contributions,
    }
    if skill_gap is not None:
        result["skill_gap"] = {
            "matched_skills": skill_gap.matched_skills,
            "missing_skills": skill_gap.missing_skills,
            "partial_matches": [
                {"jd_skill": jd_s, "candidate_skill": cand_s, "similarity": sim}
                for jd_s, cand_s, sim in skill_gap.partial_matches
            ],
            "match_ratio": skill_gap.match_ratio,
        }

    logger.info(f"Explanation generated for score={score:.4f}")
    return result
