from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from src.config import CONFIG, get_logger, utc_now_iso
from src.embeddings.generator import embed_batch
from src.parsing.schema import ResumeSchema
from src.skills.taxonomy import SkillTaxonomy, load_or_seed_taxonomy

logger = get_logger("skill_extractor")


def normalize_skill_text(text: str) -> str:
    """Lowercase, strip, collapse whitespace; keeps +, #, . so tokens like
    'C++', 'C#', 'Node.js' remain distinguishable after normalization."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s\+\#\.]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class TaxonomyManager:
    """Owns the loaded taxonomy and exposes a normalized-string ->
    (canonical_name, category) lookup index used by all matchers."""

    def __init__(self, taxonomy: SkillTaxonomy) -> None:
        self.taxonomy = taxonomy
        self.lookup: Dict[str, tuple] = {}
        self._build_lookup()

    def _build_lookup(self) -> None:
        for entry in self.taxonomy.skills:
            self.lookup[normalize_skill_text(entry.canonical_name)] = (entry.canonical_name, entry.category)
            for alias in entry.aliases:
                self.lookup[normalize_skill_text(alias)] = (entry.canonical_name, entry.category)


@dataclass(frozen=True)
class SkillMatchCandidate:
    canonical_name: str
    category: str
    confidence: float
    method: str


class BaseSkillMatcher(ABC):
    """Strategy interface. New matching strategies plug in here without
    modifying the canonicalizer (Open/Closed principle)."""

    @abstractmethod
    def match(self, normalized_skill: str) -> Optional[SkillMatchCandidate]:
        raise NotImplementedError


class ExactSkillMatcher(BaseSkillMatcher):
    def __init__(self, taxonomy_manager: TaxonomyManager) -> None:
        self._taxonomy = taxonomy_manager

    def match(self, normalized_skill: str) -> Optional[SkillMatchCandidate]:
        hit = self._taxonomy.lookup.get(normalized_skill)
        if hit is None:
            return None
        canonical_name, category = hit
        return SkillMatchCandidate(canonical_name, category, 1.0, "exact")


class FuzzySkillMatcher(BaseSkillMatcher):
    def __init__(self, taxonomy_manager: TaxonomyManager, threshold: float = 88.0) -> None:
        self._taxonomy = taxonomy_manager
        self._threshold = threshold
        self._keys = list(taxonomy_manager.lookup.keys())

    def match(self, normalized_skill: str) -> Optional[SkillMatchCandidate]:
        from rapidfuzz import fuzz, process

        result = process.extractOne(normalized_skill, self._keys, scorer=fuzz.WRatio)
        if result is None or result[1] < self._threshold:
            return None
        matched_key = result[0]
        canonical_name, category = self._taxonomy.lookup[matched_key]
        return SkillMatchCandidate(canonical_name, category, round(result[1] / 100.0, 4), "fuzzy")


class SemanticSkillMatcher(BaseSkillMatcher):
    """Embedding-based fallback for genuine synonyms not present as any
    exact or fuzzy taxonomy term."""

    def __init__(
        self,
        taxonomy_manager: TaxonomyManager,
        embed_fn: Callable[[List[str]], np.ndarray] = embed_batch,
        threshold: float = 0.62,
    ) -> None:
        self._taxonomy = taxonomy_manager
        self._embed_fn = embed_fn
        self._threshold = threshold
        self._canonical_terms: List[str] = []
        self._canonical_categories: List[str] = []
        self._canonical_embeddings: Optional[np.ndarray] = None

    def _ensure_ready(self) -> None:
        if self._canonical_embeddings is not None:
            return
        entries = self._taxonomy.taxonomy.skills
        self._canonical_terms = [entry.canonical_name for entry in entries]
        self._canonical_categories = [entry.category for entry in entries]
        self._canonical_embeddings = self._embed_fn(self._canonical_terms)

    def match(self, normalized_skill: str) -> Optional[SkillMatchCandidate]:
        self._ensure_ready()
        query_embedding = self._embed_fn([normalized_skill])[0]
        similarities = self._canonical_embeddings @ query_embedding
        best_index = int(np.argmax(similarities))
        best_score = float(similarities[best_index])
        if best_score < self._threshold:
            return None
        return SkillMatchCandidate(
            self._canonical_terms[best_index], self._canonical_categories[best_index], round(best_score, 4), "semantic"
        )


class SkillMatch(BaseModel):
    model_config = ConfigDict(extra="ignore")
    raw_forms: List[str]
    canonical_name: str
    category: str
    confidence: float
    match_method: str


class HybridSkillCanonicalizer:
    """
    Runs matchers in priority order per skill, merges duplicate raw forms
    into a single canonical entry, and applies a corroboration confidence
    boost when a skill is reinforced elsewhere in the text.
    """

    def __init__(self, matchers: List[BaseSkillMatcher], corroboration_boost: float = 0.05) -> None:
        self._matchers = matchers
        self._corroboration_boost = corroboration_boost

    def _match_one(self, raw_skill: str) -> SkillMatchCandidate:
        normalized = normalize_skill_text(raw_skill)
        for matcher in self._matchers:
            result = matcher.match(normalized)
            if result is not None:
                return result
        return SkillMatchCandidate(raw_skill.strip(), "Uncategorized", 0.30, "unmatched")

    def canonicalize_batch(self, raw_skills: List[str], source_text: str) -> List[SkillMatch]:
        grouped: Dict[str, dict] = {}
        source_lower = source_text.lower()

        for raw_skill in raw_skills:
            if not raw_skill or not raw_skill.strip():
                continue

            candidate = self._match_one(raw_skill)
            confidence = candidate.confidence
            if source_lower.count(raw_skill.lower()) > 1:
                confidence = min(1.0, confidence + self._corroboration_boost)
            confidence = round(confidence, 4)

            key = candidate.canonical_name
            if key not in grouped:
                grouped[key] = {
                    "raw_forms": [raw_skill],
                    "canonical_name": candidate.canonical_name,
                    "category": candidate.category,
                    "confidence": confidence,
                    "match_method": candidate.method,
                }
            else:
                grouped[key]["raw_forms"].append(raw_skill)
                if confidence > grouped[key]["confidence"]:
                    grouped[key]["confidence"] = confidence
                    grouped[key]["match_method"] = candidate.method
                    grouped[key]["category"] = candidate.category

        logger.info(f"Canonicalized {len(raw_skills)} raw skills into {len(grouped)} canonical entries.")
        return [SkillMatch(**entry) for entry in grouped.values()]


class DomainDetectionResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    primary_domain: str
    domain_distribution: Dict[str, float]


class DomainDetector:
    """
    Aggregates confidence-weighted category mass across a candidate's
    canonical skills. Entirely taxonomy-driven — adding a new industry to
    the taxonomy JSON automatically makes it detectable here.
    """

    def detect(self, skill_matches: List[SkillMatch]) -> DomainDetectionResult:
        weighted_counts: Dict[str, float] = defaultdict(float)
        for match in skill_matches:
            weighted_counts[match.category] += match.confidence

        total = sum(weighted_counts.values())
        if total == 0:
            return DomainDetectionResult(primary_domain="Unknown", domain_distribution={})

        distribution = {category: round(weight / total, 4) for category, weight in weighted_counts.items()}
        primary_domain = max(distribution, key=distribution.get)
        return DomainDetectionResult(primary_domain=primary_domain, domain_distribution=distribution)


class SkillExtractionResult(BaseModel):
    """The Stage 3 parsing -> skills contract."""
    model_config = ConfigDict(extra="ignore")

    source_file: str
    raw_skill_count: int
    canonical_skill_count: int
    canonical_skills: List[SkillMatch]
    domain: DomainDetectionResult
    extracted_at: str = Field(default_factory=utc_now_iso)


_taxonomy_manager: Optional[TaxonomyManager] = None
_canonicalizer: Optional[HybridSkillCanonicalizer] = None
_domain_detector = DomainDetector()


def _get_canonicalizer() -> HybridSkillCanonicalizer:
    global _taxonomy_manager, _canonicalizer
    if _canonicalizer is None:
        _taxonomy_manager = TaxonomyManager(taxonomy=load_or_seed_taxonomy())
        matchers: List[BaseSkillMatcher] = [
            ExactSkillMatcher(_taxonomy_manager),
            FuzzySkillMatcher(_taxonomy_manager, threshold=CONFIG.fuzzy_skill_match_threshold),
            SemanticSkillMatcher(_taxonomy_manager, threshold=CONFIG.semantic_skill_match_threshold),
        ]
        _canonicalizer = HybridSkillCanonicalizer(matchers=matchers)
    return _canonicalizer


def extract_skills(resume: ResumeSchema) -> SkillExtractionResult:
    """The Stage 3 pipeline contract: parsed resume in, canonicalized
    skills + detected domain out."""
    canonicalizer = _get_canonicalizer()
    canonical_skills = canonicalizer.canonicalize_batch(resume.raw_skills, resume.raw_extracted_text)
    domain = _domain_detector.detect(canonical_skills)

    return SkillExtractionResult(
        source_file=resume.metadata.source_file,
        raw_skill_count=len(resume.raw_skills),
        canonical_skill_count=len(canonical_skills),
        canonical_skills=canonical_skills,
        domain=domain,
    )
