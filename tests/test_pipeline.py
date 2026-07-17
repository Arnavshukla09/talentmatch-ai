"""
Stage 3 checkpoint test.

Run with:
    export GROQ_API_KEY=your_key
    python -m pytest tests/ -v

Requires network access (Groq + sentence-transformers model download) and
a real GROQ_API_KEY, so this is an integration test rather than a pure
unit test — that's intentional, per the execution plan's Stage 3
checkpoint ("one real sample PDF and a sample JD string").
"""

from pathlib import Path

import fitz  # PyMuPDF
import pytest

from src.pipeline import InferencePipeline

SAMPLE_RESUME_TEXT = """Jordan Ellis
Email: jordan.ellis@example.com | Phone: 555-201-4477
Location: Austin, TX | LinkedIn: linkedin.com/in/jordanellis

SUMMARY
Backend engineer with 6 years building distributed systems in fintech.

EXPERIENCE
Senior Backend Engineer, Northwind Payments, Austin, TX
Jan 2022 - Present
- Led migration of the ledger service from monolith to microservices
- Reduced p99 latency by 40 percent using Redis caching layer

Backend Engineer, Fintech Labs, Austin, TX
Jun 2019 - Dec 2021
- Built the fraud detection pipeline using Kafka and PostgreSQL

EDUCATION
B.S. Computer Science, University of Texas at Austin, 2015 - 2019

SKILLS
Python, Golang, PostgreSQL, Kafka, Redis, AWS, Docker, Node JS

PROJECTS
OpenLedger - Open source double-entry ledger library. github.com/jellis/openledger

CERTIFICATIONS
AWS Certified Solutions Architect - Associate, Amazon, 2023
"""

SAMPLE_JD_TEXT = (
    "Senior Backend Engineer with experience in distributed systems, "
    "Python or Go, PostgreSQL, and cloud deployment on AWS."
)


@pytest.fixture(scope="module")
def sample_resume_pdf(tmp_path_factory) -> Path:
    output_dir = tmp_path_factory.mktemp("sample_resumes")
    pdf_path = output_dir / "jordan_ellis.pdf"

    document = fitz.open()
    page = document.new_page()
    page.insert_text((50, 50), SAMPLE_RESUME_TEXT, fontsize=10, fontname="helv")
    document.save(pdf_path)
    document.close()

    return pdf_path


def test_pipeline_returns_score_without_exceptions(sample_resume_pdf):
    pipeline = InferencePipeline()
    result = pipeline.run(sample_resume_pdf, SAMPLE_JD_TEXT)

    assert "score" in result
    assert 0.0 <= result["score"] <= 1.0
    assert "explanation" in result
    assert "narrative_summary" in result["explanation"]
    assert "parsed_resume" in result
    assert result["parsed_resume"]["contact"]["full_name"]
