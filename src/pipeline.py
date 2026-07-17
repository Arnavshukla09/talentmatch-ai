from __future__ import annotations

from pathlib import Path

from src.embeddings.generator import embed
from src.explainability.explainer import explain
from src.features.engineering import build_features
from src.parsing.llm_parser import parse_resume
from src.ranking.ranker import rank_with_breakdown
from src.skills.extractor import extract_skills


class InferencePipeline:
    """
    Single-resume, single-JD orchestration: the exact call chain
    app.py needs for the "upload one resume, score against one JD" use
    case described in the execution plan (Stage 3). No FAISS, no
    LightGBM — see src/ranking/ranker.py for why.
    """

    def run(self, resume_pdf_path: Path, job_description_text: str) -> dict:
        resume = parse_resume(resume_pdf_path)
        skills = extract_skills(resume)
        features = build_features(resume, skills)

        resume_emb = embed(resume.raw_extracted_text)
        jd_emb = embed(job_description_text)

        ranked = rank_with_breakdown(features, resume_emb, jd_emb)
        explanation = explain(
            score=ranked["score"],
            features=features,
            contributions=ranked["contributions"],
            resume=resume,
            skills=skills,
            job_description_text=job_description_text,
        )

        return {
            "score": ranked["score"],
            "explanation": explanation,
            "parsed_resume": resume.model_dump(),
        }
