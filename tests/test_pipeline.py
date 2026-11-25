"""
tests/test_pipeline.py  —  TalentMatch v2 end-to-end pipeline test.

Does NOT require:
  - GROQ_API_KEY (use MOCK_LLM=1 to mock optional coaching)
  - Network access (embeddings model downloads on first run only)
  - Real labeled data

DOES require:
  - Built C++ engine (cpp_core/build/talentmatch.so or .dll)
  - sentence-transformers model (auto-downloaded on first run)

Run with:
    python -m pytest tests/ -v --no-header

For checks without native scoring or an embedding model:
    python -m pytest tests/test_api_security.py tests/test_coaching.py -q
Only TestCppBridge skips automatically when the native library is missing.
"""

from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
import pytest

SAMPLE_RESUME_TEXT = """\
Jordan Ellis
Email: jordan.ellis@example.com | Phone: 555-201-4477
Location: Austin, TX | LinkedIn: linkedin.com/in/jordanellis | GitHub: github.com/jellis

SUMMARY
Backend engineer with 6 years building distributed systems in fintech.

EXPERIENCE
Senior Backend Engineer, Northwind Payments, Austin, TX
Jan 2022 - Present
- Led migration of the ledger service from monolith to microservices reducing latency by 40%
- Reduced p99 latency by 40% using Redis caching layer
- Managed a team of 5 engineers across 3 time zones

Backend Engineer, Fintech Labs, Austin, TX
Jun 2019 - Dec 2021
- Built the fraud detection pipeline using Kafka and PostgreSQL processing 1M events/day
- Deployed ML models to production using Docker and Kubernetes

EDUCATION
B.S. Computer Science, University of Texas at Austin, 2015 - 2019
GPA: 3.8/4.0

SKILLS
Python, Golang, PostgreSQL, Kafka, Redis, AWS, Docker, Kubernetes, Node JS, SQL, Git

PROJECTS
OpenLedger - Open source double-entry ledger library built with Python and PostgreSQL
Technologies: Python, PostgreSQL, Docker
URL: github.com/jellis/openledger

CERTIFICATIONS
AWS Certified Solutions Architect - Associate, Amazon, 2023
"""

SAMPLE_JD_TEXT = (
    "Senior Backend Engineer with experience in distributed systems, "
    "Python or Go, PostgreSQL, and cloud deployment on AWS. "
    "Experience with Kafka, Redis, and microservices architecture. "
    "Kubernetes experience preferred."
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def sample_resume_pdf(tmp_path_factory) -> Path:
    """Create a test PDF from the sample resume text."""
    output_dir = tmp_path_factory.mktemp("sample_resumes")
    pdf_path = output_dir / "jordan_ellis.pdf"

    document = fitz.open()
    page = document.new_page()
    page.insert_text((50, 50), SAMPLE_RESUME_TEXT, fontsize=9, fontname="helv")
    document.save(pdf_path)
    document.close()

    return pdf_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPipelineContract:
    """Tests that the pipeline returns the correct v2 JSON contract."""

    def test_pipeline_returns_overall_score(self, sample_resume_pdf):
        from src.pipeline import InferencePipeline
        pipeline = InferencePipeline()
        result = pipeline.run(sample_resume_pdf, SAMPLE_JD_TEXT)
        assert "overall_score" in result
        assert 0.0 <= result["overall_score"] <= 100.0

    def test_pipeline_returns_score_breakdown(self, sample_resume_pdf):
        from src.pipeline import InferencePipeline
        pipeline = InferencePipeline()
        result = pipeline.run(sample_resume_pdf, SAMPLE_JD_TEXT)

        scores = result.get("scores", {})
        for key in ["skills", "experience", "education", "projects", "semantic", "resume_quality"]:
            assert key in scores, f"Missing score key: {key}"
            assert 0.0 <= scores[key] <= 100.0, f"{key}={scores[key]} out of range"

    def test_pipeline_returns_skill_lists(self, sample_resume_pdf):
        from src.pipeline import InferencePipeline
        pipeline = InferencePipeline()
        result = pipeline.run(sample_resume_pdf, SAMPLE_JD_TEXT)

        assert "matched_skills" in result
        assert "missing_skills" in result
        assert "partial_skills" in result
        assert isinstance(result["matched_skills"], list)
        assert isinstance(result["missing_skills"], list)

    def test_pipeline_returns_explanation_factors(self, sample_resume_pdf):
        from src.pipeline import InferencePipeline
        pipeline = InferencePipeline()
        result = pipeline.run(sample_resume_pdf, SAMPLE_JD_TEXT)

        assert "top_positive_factors" in result
        assert "top_negative_factors" in result
        assert len(result["top_positive_factors"]) > 0
        assert len(result["top_negative_factors"]) > 0

    def test_pipeline_with_text_input(self):
        """Pipeline works with raw text (no PDF upload)."""
        from src.pipeline import InferencePipeline
        pipeline = InferencePipeline()
        result = pipeline.run(resume_text=SAMPLE_RESUME_TEXT, job_description_text=SAMPLE_JD_TEXT)
        assert "overall_score" in result
        assert 0.0 <= result["overall_score"] <= 100.0

    def test_high_match_score_above_low_match(self, sample_resume_pdf):
        """A relevant resume should score higher than an irrelevant one."""
        from src.pipeline import InferencePipeline
        pipeline = InferencePipeline()

        # Highly relevant
        relevant = pipeline.run(resume_text=SAMPLE_RESUME_TEXT, job_description_text=SAMPLE_JD_TEXT)

        # Completely irrelevant — nurse JD vs software engineer resume
        irrelevant_jd = (
            "Registered Nurse with experience in patient care, clinical documentation, "
            "HIPAA compliance, and Electronic Health Records systems."
        )
        irrelevant = pipeline.run(resume_text=SAMPLE_RESUME_TEXT, job_description_text=irrelevant_jd)

        assert relevant["overall_score"] > irrelevant["overall_score"], (
            f"Expected relevant ({relevant['overall_score']}) > irrelevant ({irrelevant['overall_score']})"
        )

    def test_matched_skills_are_strings(self, sample_resume_pdf):
        from src.pipeline import InferencePipeline
        pipeline = InferencePipeline()
        result = pipeline.run(sample_resume_pdf, SAMPLE_JD_TEXT)
        for skill in result["matched_skills"]:
            assert isinstance(skill, str) and len(skill) > 0

    def test_ranking_method_is_set(self, sample_resume_pdf):
        from src.pipeline import InferencePipeline
        pipeline = InferencePipeline()
        result = pipeline.run(sample_resume_pdf, SAMPLE_JD_TEXT)
        assert result.get("ranking_method") in ("xgboost", "linear_fallback")

    def test_empty_jd_raises(self, sample_resume_pdf):
        from src.pipeline import InferencePipeline
        pipeline = InferencePipeline()
        with pytest.raises((ValueError, Exception)):
            pipeline.run(sample_resume_pdf, "")

    def test_no_input_raises(self):
        from src.pipeline import InferencePipeline
        pipeline = InferencePipeline()
        with pytest.raises((ValueError, Exception)):
            pipeline.run(job_description_text=SAMPLE_JD_TEXT)

    def test_extracted_resume_text_is_opt_in(self):
        from src.pipeline import InferencePipeline
        pipeline = InferencePipeline()
        result = pipeline.run(resume_text=SAMPLE_RESUME_TEXT, job_description_text=SAMPLE_JD_TEXT)
        assert "extracted_resume_text" not in result
        result = pipeline.run(resume_text=SAMPLE_RESUME_TEXT, job_description_text=SAMPLE_JD_TEXT,
                              return_resume_text=True)
        assert result["extracted_resume_text"] == SAMPLE_RESUME_TEXT

    def test_blank_resume_rejected_before_embedding(self):
        from src.pipeline import InferencePipeline
        with pytest.raises(ValueError, match="No readable text"):
            InferencePipeline().run(resume_text="   ", job_description_text=SAMPLE_JD_TEXT)


class TestPDFExtraction:
    """Tests that the Python PDF extraction layer works correctly."""

    def test_extracts_text_from_pdf(self, sample_resume_pdf):
        from src.pipeline import InferencePipeline
        text = InferencePipeline._extract_pdf_text(sample_resume_pdf)
        assert "jordan" in text.lower() or "Ellis" in text
        assert len(text) > 100

    def test_known_content_in_extracted_text(self, sample_resume_pdf):
        from src.pipeline import InferencePipeline
        text = InferencePipeline._extract_pdf_text(sample_resume_pdf)
        assert "Python" in text or "python" in text.lower()


class TestCppBridge:
    """Tests for the ctypes bridge (skipped if library not built)."""

    @pytest.fixture(autouse=True)
    def skip_if_no_lib(self):
        try:
            from src.bridge import _find_library
            if _find_library() is None:
                pytest.skip("C++ engine library not built — run scripts/build_engine.sh")
        except Exception:
            pytest.skip("C++ bridge unavailable")

    def test_engine_version_returns_string(self):
        from src.bridge import engine_version
        v = engine_version()
        assert isinstance(v, str)
        assert len(v) > 0

    def test_score_returns_valid_json(self):
        from src.bridge import score
        result = score(
            resume_text=SAMPLE_RESUME_TEXT,
            jd_text=SAMPLE_JD_TEXT,
            resume_embedding=[0.0] * 384,
            jd_embedding=[0.0] * 384,
        )
        assert "overall_score" in result
        assert "scores" in result
        assert "matched_skills" in result
