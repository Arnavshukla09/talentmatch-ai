"""
src/pipeline.py  —  TalentMatch v2 inference pipeline.

Python responsibilities (only):
  1. Extract plain text from PDF (PyMuPDF)
  2. Generate embeddings (sentence-transformers, local, no network)
  3. Call C++ engine via ctypes bridge
  4. Return JSON result
  5. Optionally request Groq coaching after numerical scoring

Python does NOT:
  - parse the resume structure
  - extract or normalize skills
  - compute any ATS score or feature
  - rank or generate rule-based scoring factors
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.bridge import score as cpp_score
from src.config import get_logger
from src.embeddings.generator import embed

logger = get_logger("pipeline")


class InferencePipeline:
    """
    Single-resume, single-JD orchestration.

    Usage:
        pipeline = InferencePipeline()
        result = pipeline.run(resume_pdf_path=Path("resume.pdf"),
                              job_description_text="Senior backend engineer...")
    """

    def run(
        self,
        resume_pdf_path: Optional[Path] = None,
        job_description_text: str = "",
        resume_text: Optional[str] = None,
        return_resume_text: bool = False,
    ) -> dict:
        """
        Args:
            resume_pdf_path:       Path to resume PDF (mutually exclusive with resume_text).
            job_description_text:  Raw job description text.
            resume_text:           Plain text resume (mutually exclusive with resume_pdf_path).
            return_resume_text:    Include extracted_resume_text for requested local profile saving.

        Returns:
            {
              "overall_score":        float,   # 0–100
              "scores":               dict,    # per-category 0–100
              "matched_skills":       list,
              "missing_skills":       list,
              "partial_skills":       list,
              "top_positive_factors": list,
              "top_negative_factors": list,
              "feature_vector":       dict,    # all ~85 features (for debug)
              "ranking_method":       str,     # "xgboost" or "linear_fallback"
            }
        """
        if not job_description_text or not job_description_text.strip():
            raise ValueError("job_description_text cannot be empty")

        # --- Step 1: Get resume plain text ---
        if resume_text:
            raw_text = resume_text
        elif resume_pdf_path:
            raw_text = self._extract_pdf_text(Path(resume_pdf_path))
        else:
            raise ValueError("Either resume_pdf_path or resume_text must be provided")

        if not raw_text.strip():
            raise ValueError("No readable text found. Upload a text-based PDF or use a saved text profile.")
        if len(raw_text) > 100_000:
            raise ValueError("Resume text exceeds 100000 characters.")

        logger.info(f"Resume text extracted: {len(raw_text)} chars")

        # --- Step 2: Generate embeddings (Python, local, sentence-transformers) ---
        logger.info("Generating embeddings...")
        resume_emb = embed(raw_text).tolist()
        jd_emb     = embed(job_description_text).tolist()
        logger.info(f"Embeddings ready: dim={len(resume_emb)}")

        # --- Step 3: Call C++ engine ---
        logger.info("Calling C++ engine...")
        result = cpp_score(
            resume_text=raw_text,
            jd_text=job_description_text,
            resume_embedding=resume_emb,
            jd_embedding=jd_emb,
        )

        logger.info(
            f"Score: {result.get('overall_score')} | "
            f"Method: {result.get('ranking_method')} | "
            f"Matched skills: {len(result.get('matched_skills', []))}"
        )

        import os
        if os.environ.get("GROQ_API_KEY") or os.environ.get("MOCK_LLM") == "1":
            try:
                from src.suggestions.generator import generate_ai_insights
                insights = generate_ai_insights(
                    missing_skills=result.get("missing_skills", []),
                    matched_skills=result.get("matched_skills", []),
                    raw_resume_text=raw_text,
                    job_description_text=job_description_text,
                )
                result["match_summary"] = insights.get("match_summary", "")
                result["suggestions"] = insights.get("suggestions", [])
            except Exception as e:
                logger.warning(f"Failed to generate AI insights: {e}")
        
        if return_resume_text:
            result["extracted_resume_text"] = raw_text
        return result

    @staticmethod
    def _extract_pdf_text(pdf_path: Path) -> str:
        """Extract plain text from a PDF using PyMuPDF."""
        try:
            import fitz  # PyMuPDF

            with fitz.open(str(pdf_path)) as doc:
                pages = []
                for page in doc:
                    text = page.get_text("text").strip()
                    if text:
                        pages.append(text)
                full_text = "\n\n".join(pages)

                if not full_text.strip():
                    # Text blocks can recover native text; this is not OCR.
                    blocks = []
                    for page in doc:
                        for block in page.get_text("blocks"):
                            if block[6] == 0:
                                blocks.append(block[4])
                    full_text = "\n".join(blocks)

            return full_text.strip()

        except Exception as exc:
            raise ValueError("Unable to read this PDF. Upload a valid, unencrypted PDF.") from exc
