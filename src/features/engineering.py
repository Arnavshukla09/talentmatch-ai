from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np
from dateutil import parser as date_parser
from pydantic import BaseModel, ConfigDict, Field

from src.config import get_logger, utc_now_iso
from src.embeddings.generator import embed_batch
from src.parsing.schema import ResumeSchema
from src.skills.extractor import SkillExtractionResult

logger = get_logger("feature_engineering")


class DateRangeParser:
    """
    Centralized, defensive date parsing shared by any extractor that needs
    duration math. Handles free-text resume dates like 'Jan 2022', '2023',
    'Present' without crashing on unparseable or missing values.
    """

    PRESENT_TOKENS = {"present", "current", "now", "ongoing"}

    @classmethod
    def parse(cls, raw_date: Optional[str], reference_now: datetime) -> Optional[datetime]:
        if not raw_date or not raw_date.strip():
            return None
        normalized = raw_date.strip().lower()
        if normalized in cls.PRESENT_TOKENS:
            return reference_now
        try:
            return date_parser.parse(raw_date, default=datetime(1900, 1, 1), fuzzy=True)
        except (ValueError, OverflowError):
            return None

    @classmethod
    def duration_months(cls, start_raw: Optional[str], end_raw: Optional[str], reference_now: datetime) -> float:
        start = cls.parse(start_raw, reference_now)
        end = cls.parse(end_raw, reference_now) if end_raw else reference_now
        if start is None:
            return 0.0
        if end is None:
            end = reference_now
        months = (end.year - start.year) * 12 + (end.month - start.month)
        return max(0.0, float(months))


class BaseFeatureExtractor(ABC):
    """Interface every feature group implements. Adding a new feature group
    means adding one class here — no other code changes."""

    @property
    @abstractmethod
    def feature_names(self) -> List[str]:
        raise NotImplementedError

    @abstractmethod
    def extract(self, resume: dict, skills: dict) -> Dict[str, float]:
        raise NotImplementedError


class CandidateFeatureVector(BaseModel):
    """The Stage 3 features -> embeddings/ranking contract."""
    model_config = ConfigDict(extra="ignore")

    source_file: str
    feature_names: List[str]
    features: Dict[str, float]
    generated_at: str = Field(default_factory=utc_now_iso)


class ExperienceFeatureExtractor(BaseFeatureExtractor):
    SENIORITY_KEYWORDS = {
        "principal": 5.0, "staff": 4.5, "lead": 4.0, "senior": 3.5,
        "sr.": 3.5, "sr ": 3.5, "mid-level": 2.5, "associate": 2.0,
        "junior": 1.5, "jr.": 1.5, "intern": 1.0, "trainee": 1.0,
    }

    @property
    def feature_names(self) -> List[str]:
        return [
            "total_experience_months", "num_positions", "avg_tenure_months",
            "is_currently_employed", "max_seniority_score", "has_experience",
        ]

    def extract(self, resume: dict, skills: dict) -> Dict[str, float]:
        experience_entries = resume.get("experience", []) or []
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        if not experience_entries:
            return {name: 0.0 for name in self.feature_names}

        durations = [
            DateRangeParser.duration_months(entry.get("start_date"), entry.get("end_date"), now)
            for entry in experience_entries
        ]
        total_months = sum(durations)
        is_current = any(bool(entry.get("is_current")) for entry in experience_entries)

        seniority_scores = []
        for entry in experience_entries:
            title = (entry.get("job_title") or "").lower()
            matched = [score for kw, score in self.SENIORITY_KEYWORDS.items() if kw in title]
            seniority_scores.append(max(matched) if matched else 2.0)

        return {
            "total_experience_months": round(total_months, 2),
            "num_positions": float(len(experience_entries)),
            "avg_tenure_months": round(total_months / len(experience_entries), 2),
            "is_currently_employed": 1.0 if is_current else 0.0,
            "max_seniority_score": round(max(seniority_scores), 2),
            "has_experience": 1.0,
        }


class EducationFeatureExtractor(BaseFeatureExtractor):
    DEGREE_LEVELS = [
        (["phd", "doctorate", "doctoral"], 5.0),
        (["master", "m.tech", "mtech", "msc", "m.s.", "mba"], 4.0),
        (["bachelor", "b.tech", "btech", "bsc", "b.s.", "be ", "b.e."], 3.0),
        (["associate", "diploma"], 2.0),
        (["high school", "secondary"], 1.0),
    ]

    @property
    def feature_names(self) -> List[str]:
        return [
            "num_degrees", "highest_degree_level", "gpa_normalized",
            "has_gpa", "is_currently_studying", "num_institutions",
        ]

    def _degree_level(self, degree_text: str) -> float:
        lowered = degree_text.lower()
        for keywords, level in self.DEGREE_LEVELS:
            if any(keyword in lowered for keyword in keywords):
                return level
        return 0.0

    def _normalize_gpa(self, gpa_text: Optional[str]) -> Optional[float]:
        if not gpa_text:
            return None
        match = re.search(r"([\d.]+)\s*/\s*([\d.]+)", gpa_text)
        if match:
            numerator, denominator = float(match.group(1)), float(match.group(2))
            return round(numerator / denominator, 4) if denominator > 0 else None
        match = re.search(r"([\d.]+)", gpa_text)
        if match:
            value = float(match.group(1))
            scale = 4.0 if value <= 4.0 else 100.0
            return round(value / scale, 4)
        return None

    def extract(self, resume: dict, skills: dict) -> Dict[str, float]:
        education_entries = resume.get("education", []) or []
        if not education_entries:
            return {name: 0.0 for name in self.feature_names}

        levels = [self._degree_level(entry.get("degree") or "") for entry in education_entries]
        gpas = [self._normalize_gpa(entry.get("gpa")) for entry in education_entries]
        gpas = [g for g in gpas if g is not None]
        is_studying = any(
            (entry.get("end_date") or "").strip().lower() in DateRangeParser.PRESENT_TOKENS
            for entry in education_entries
        )
        institutions = {entry.get("institution") for entry in education_entries if entry.get("institution")}

        return {
            "num_degrees": float(len(education_entries)),
            "highest_degree_level": max(levels) if levels else 0.0,
            "gpa_normalized": round(sum(gpas) / len(gpas), 4) if gpas else 0.0,
            "has_gpa": 1.0 if gpas else 0.0,
            "is_currently_studying": 1.0 if is_studying else 0.0,
            "num_institutions": float(len(institutions)),
        }


class SkillFeatureExtractor(BaseFeatureExtractor):
    @property
    def feature_names(self) -> List[str]:
        return [
            "total_canonical_skills", "high_confidence_skill_ratio",
            "unmatched_skill_ratio", "category_diversity",
            "primary_domain_confidence", "avg_skill_confidence",
        ]

    def extract(self, resume: dict, skills: dict) -> Dict[str, float]:
        canonical_skills = skills.get("canonical_skills", []) or []
        if not canonical_skills:
            return {name: 0.0 for name in self.feature_names}

        confidences = [s["confidence"] for s in canonical_skills]
        high_confidence = sum(1 for c in confidences if c >= 0.8)
        unmatched = sum(1 for s in canonical_skills if s["match_method"] == "unmatched")
        categories = {s["category"] for s in canonical_skills}
        domain_distribution = skills.get("domain", {}).get("domain_distribution", {})
        primary_domain = skills.get("domain", {}).get("primary_domain")
        primary_domain_confidence = domain_distribution.get(primary_domain, 0.0)

        return {
            "total_canonical_skills": float(len(canonical_skills)),
            "high_confidence_skill_ratio": round(high_confidence / len(canonical_skills), 4),
            "unmatched_skill_ratio": round(unmatched / len(canonical_skills), 4),
            "category_diversity": float(len(categories)),
            "primary_domain_confidence": round(float(primary_domain_confidence), 4),
            "avg_skill_confidence": round(sum(confidences) / len(confidences), 4),
        }


class ProjectFeatureExtractor(BaseFeatureExtractor):
    @property
    def feature_names(self) -> List[str]:
        return ["num_projects", "avg_technologies_per_project", "project_link_ratio", "has_projects"]

    def extract(self, resume: dict, skills: dict) -> Dict[str, float]:
        projects = resume.get("projects", []) or []
        if not projects:
            return {name: 0.0 for name in self.feature_names}

        tech_counts = [len(p.get("technologies_used") or []) for p in projects]
        with_links = sum(1 for p in projects if p.get("url"))

        return {
            "num_projects": float(len(projects)),
            "avg_technologies_per_project": round(sum(tech_counts) / len(projects), 2),
            "project_link_ratio": round(with_links / len(projects), 4),
            "has_projects": 1.0,
        }


class CertificationFeatureExtractor(BaseFeatureExtractor):
    @property
    def feature_names(self) -> List[str]:
        return ["num_certifications", "num_unique_issuers", "has_certifications"]

    def extract(self, resume: dict, skills: dict) -> Dict[str, float]:
        certifications = resume.get("certifications", []) or []
        if not certifications:
            return {name: 0.0 for name in self.feature_names}

        issuers = {c.get("issuing_organization") for c in certifications if c.get("issuing_organization")}
        return {
            "num_certifications": float(len(certifications)),
            "num_unique_issuers": float(len(issuers)),
            "has_certifications": 1.0,
        }


class EmbeddingFeatureExtractor(BaseFeatureExtractor):
    """
    Computes lightweight scalar features derived from the embedding space.
    Full dense embeddings for JD matching are src/embeddings' responsibility;
    this extractor does not duplicate or persist them.
    """

    @property
    def feature_names(self) -> List[str]:
        return ["summary_embedding_norm", "skills_text_embedding_norm", "summary_skills_semantic_consistency"]

    def extract(self, resume: dict, skills: dict) -> Dict[str, float]:
        summary_text = (resume.get("summary") or "").strip()
        skill_names = [s["canonical_name"] for s in (skills.get("canonical_skills") or [])]
        skills_text = ", ".join(skill_names)

        if not summary_text and not skills_text:
            return {name: 0.0 for name in self.feature_names}

        texts = [summary_text or " ", skills_text or " "]
        embeddings = embed_batch(texts)
        summary_embedding, skills_embedding = embeddings[0], embeddings[1]

        summary_norm = float(np.linalg.norm(summary_embedding))
        skills_norm = float(np.linalg.norm(skills_embedding))

        if summary_norm > 0 and skills_norm > 0:
            cosine_sim = float(np.dot(summary_embedding, skills_embedding) / (summary_norm * skills_norm))
        else:
            cosine_sim = 0.0

        return {
            "summary_embedding_norm": round(summary_norm, 4),
            "skills_text_embedding_norm": round(skills_norm, 4),
            "summary_skills_semantic_consistency": round(cosine_sim, 4),
        }


class FeatureFusionEngine:
    """
    Runs every extractor and merges results into one fixed-schema flat
    vector. Guarantees identical column order across all candidates.
    """

    def __init__(self, extractors: List[BaseFeatureExtractor]) -> None:
        self._extractors = extractors

    @property
    def full_feature_names(self) -> List[str]:
        names: List[str] = []
        for extractor in self._extractors:
            names.extend(extractor.feature_names)
        return names

    def fuse(self, resume: dict, skills: dict) -> Dict[str, float]:
        fused: Dict[str, float] = {}
        for extractor in self._extractors:
            try:
                fused.update(extractor.extract(resume, skills))
            except Exception as exc:
                logger.error(f"{type(extractor).__name__} failed: {exc}")
                fused.update({name: 0.0 for name in extractor.feature_names})
        return {name: fused.get(name, 0.0) for name in self.full_feature_names}


_fusion_engine = FeatureFusionEngine(
    extractors=[
        ExperienceFeatureExtractor(),
        EducationFeatureExtractor(),
        SkillFeatureExtractor(),
        ProjectFeatureExtractor(),
        CertificationFeatureExtractor(),
        EmbeddingFeatureExtractor(),
    ]
)


def build_features(resume: ResumeSchema, skills: SkillExtractionResult) -> CandidateFeatureVector:
    """The Stage 3 pipeline contract: parsed resume + extracted skills in,
    a fixed-schema numeric feature vector out."""
    resume_dict = resume.model_dump()
    skills_dict = skills.model_dump()

    features = _fusion_engine.fuse(resume_dict, skills_dict)

    return CandidateFeatureVector(
        source_file=resume.metadata.source_file,
        feature_names=_fusion_engine.full_feature_names,
        features=features,
    )
