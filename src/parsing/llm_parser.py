from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from groq import APIError, APITimeoutError, Groq
from pydantic import ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config import CONFIG, DIRS, get_groq_api_key, get_logger
from src.parsing.extractor import HybridPDFExtractor, TextCleaner
from src.parsing.schema import ResumeSchema

logger = get_logger("llm_parser")


class PromptBuilder:
    """
    Builds the JSON-only extraction prompt and the error-feedback repair
    prompt. Schema knowledge lives here, not scattered across the pipeline.
    """

    SYSTEM_PROMPT = (
        "You are a precise resume parsing engine. You extract structured "
        "information from resume text and output ONLY a single valid JSON "
        "object. You never invent information that is not present in the "
        "text. You never summarize, translate, or rephrase skill names — "
        "copy every skill exactly as it appears in the source text, "
        "including capitalization, punctuation, and abbreviations. Do not "
        "categorize, group, deduplicate, or normalize skills in any way. "
        "If a field is not present in the resume, use null or an empty "
        "list as appropriate. Output no text before or after the JSON."
    )

    JSON_SCHEMA_DESCRIPTION = """
{
  "contact": {"full_name": str|null, "email": str|null, "phone": str|null,
              "location": str|null, "linkedin_url": str|null,
              "github_url": str|null, "portfolio_url": str|null},
  "summary": str|null,
  "experience": [{"company": str|null, "job_title": str|null,
                  "location": str|null, "start_date": str|null,
                  "end_date": str|null, "is_current": bool|null,
                  "responsibilities": [str]}],
  "education": [{"institution": str|null, "degree": str|null,
                 "field_of_study": str|null, "start_date": str|null,
                 "end_date": str|null, "gpa": str|null}],
  "raw_skills": [str],
  "projects": [{"name": str|null, "description": str|null,
                "technologies_used": [str], "url": str|null}],
  "certifications": [{"name": str|null, "issuing_organization": str|null,
                       "issue_date": str|null, "credential_id": str|null}],
  "languages": [str],
  "awards": [str],
  "publications": [str]
}
""".strip()

    def build_parsing_prompt(self, resume_text: str) -> str:
        return (
            f"Extract the following resume text into this exact JSON schema:\n\n"
            f"{self.JSON_SCHEMA_DESCRIPTION}\n\n"
            f'RESUME TEXT:\n"""\n{resume_text}\n"""\n\n'
            f"Return ONLY the JSON object."
        )

    def build_repair_prompt(self, malformed_output: str, error_message: str) -> str:
        return (
            f"Your previous output was invalid for this reason:\n{error_message}\n\n"
            f'Here is your previous output:\n"""\n{malformed_output}\n"""\n\n'
            f"Fix it and return ONLY a corrected, valid JSON object matching this "
            f"schema:\n\n{self.JSON_SCHEMA_DESCRIPTION}"
        )


class GroqClientWrapper:
    """Thin retrying wrapper around the Groq chat completions API."""

    def __init__(self) -> None:
        self._client = Groq(api_key=get_groq_api_key())
        self._model = CONFIG.groq_model_name
        self._max_retries = CONFIG.groq_max_retries

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        @retry(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=1, min=2, max=20),
            retry=retry_if_exception_type((APIError, APITimeoutError)),
            reraise=True,
        )
        def _call() -> str:
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            return response.choices[0].message.content

        return _call()


class JSONAutoRepair:
    """Repairs and validates JSON returned by the LLM."""

    def __init__(self, groq_client: GroqClientWrapper, prompt_builder: PromptBuilder) -> None:
        self.groq_client = groq_client
        self.prompt_builder = prompt_builder

    def repair(self, raw_output: str) -> dict:
        try:
            return json.loads(raw_output)
        except Exception:
            pass

        repair_prompt = self.prompt_builder.build_repair_prompt(
            malformed_output=raw_output, error_message="Invalid JSON"
        )
        repaired = self.groq_client.complete(
            system_prompt=self.prompt_builder.SYSTEM_PROMPT, user_prompt=repair_prompt
        )
        return json.loads(repaired)


@dataclass
class ParsingResult:
    success: bool
    source_file: str
    resume: Optional[ResumeSchema]
    error: Optional[str]
    latency_seconds: float
    ocr_used: bool


class ResumeParsingPipeline:
    """
    End-to-end single-resume orchestration. Every intermediate artifact is
    written to its own directory so a failed run can be diagnosed
    stage-by-stage without re-calling the LLM.
    """

    def __init__(self, max_validation_retries: int = 2) -> None:
        self.extractor = HybridPDFExtractor(ocr_gpu=(CONFIG.device == "cuda"))
        self.cleaner = TextCleaner()
        self.prompt_builder = PromptBuilder()
        self.groq_client = GroqClientWrapper()
        self.json_repairer = JSONAutoRepair(self.groq_client, self.prompt_builder)
        self.max_validation_retries = max_validation_retries

    def _save_json(self, directory_key: str, filename: str, payload: dict) -> None:
        path = DIRS.get(directory_key) / filename
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    def parse_single(self, pdf_path: Path) -> ParsingResult:
        start_time = time.monotonic()
        stem = pdf_path.stem

        try:
            extraction = self.extractor.extract(pdf_path)
            cleaned_text = self.cleaner.clean(extraction.full_text)

            self._save_json(
                "extracted_text",
                f"{stem}.json",
                {
                    "source_file": pdf_path.name,
                    "raw_text": extraction.full_text,
                    "cleaned_text": cleaned_text,
                    "page_count": extraction.page_count,
                    "used_ocr": extraction.used_ocr,
                    "average_confidence": extraction.average_confidence,
                },
            )

            prompt = self.prompt_builder.build_parsing_prompt(cleaned_text)
            raw_llm_output = self.groq_client.complete(
                system_prompt=self.prompt_builder.SYSTEM_PROMPT, user_prompt=prompt
            )

            parsed_dict = self.json_repairer.repair(raw_llm_output)
            self._save_json("parsed_json", f"{stem}.json", parsed_dict)

            parsed_dict["raw_extracted_text"] = cleaned_text
            parsed_dict["metadata"] = {
                "source_file": pdf_path.name,
                "llm_model_used": CONFIG.groq_model_name,
                "ocr_used": extraction.used_ocr,
                "page_count": extraction.page_count,
                "extraction_confidence": extraction.average_confidence,
            }

            resume = self._validate_with_retry(parsed_dict, raw_llm_output)
            self._save_json("validated_json", f"{stem}.json", resume.model_dump())

            latency = time.monotonic() - start_time
            logger.info(f"Parsed '{pdf_path.name}' successfully in {latency:.2f}s.")
            return ParsingResult(
                success=True,
                source_file=pdf_path.name,
                resume=resume,
                error=None,
                latency_seconds=latency,
                ocr_used=extraction.used_ocr,
            )

        except Exception as exc:
            latency = time.monotonic() - start_time
            logger.error(f"Failed to parse '{pdf_path.name}': {exc}")
            return ParsingResult(
                success=False,
                source_file=pdf_path.name,
                resume=None,
                error=str(exc),
                latency_seconds=latency,
                ocr_used=False,
            )

    def _validate_with_retry(self, parsed_dict: dict, raw_llm_output: str) -> ResumeSchema:
        current_dict = parsed_dict
        current_raw = raw_llm_output

        for attempt in range(self.max_validation_retries + 1):
            try:
                return ResumeSchema(**current_dict)
            except ValidationError as validation_error:
                if attempt == self.max_validation_retries:
                    raise
                logger.warning(f"Validation failed (attempt {attempt + 1}); requesting LLM correction.")
                repair_prompt = self.prompt_builder.build_repair_prompt(
                    malformed_output=current_raw, error_message=str(validation_error)
                )
                current_raw = self.groq_client.complete(
                    system_prompt=self.prompt_builder.SYSTEM_PROMPT, user_prompt=repair_prompt
                )
                current_dict = self.json_repairer.repair(current_raw)
                current_dict["raw_extracted_text"] = parsed_dict["raw_extracted_text"]
                current_dict["metadata"] = parsed_dict["metadata"]

        raise RuntimeError("Unreachable: validation retry loop exhausted without return.")


_pipeline: Optional[ResumeParsingPipeline] = None


def _get_pipeline() -> ResumeParsingPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = ResumeParsingPipeline()
    return _pipeline


def parse_resume(pdf_path: Path) -> ResumeSchema:
    """The Stage 3 pipeline contract: PDF path in, validated ResumeSchema out."""
    result = _get_pipeline().parse_single(Path(pdf_path))
    if not result.success:
        raise RuntimeError(f"Failed to parse '{pdf_path}': {result.error}")
    return result.resume
