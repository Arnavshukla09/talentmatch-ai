from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.config import utc_now_iso


class ContactInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None


class ExperienceEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    company: Optional[str] = None
    job_title: Optional[str] = None
    location: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_current: Optional[bool] = None
    responsibilities: List[str] = Field(default_factory=list)


class EducationEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    institution: Optional[str] = None
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    gpa: Optional[str] = None


class ProjectEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: Optional[str] = None
    description: Optional[str] = None
    technologies_used: List[str] = Field(default_factory=list)
    url: Optional[str] = None


class CertificationEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: Optional[str] = None
    issuing_organization: Optional[str] = None
    issue_date: Optional[str] = None
    credential_id: Optional[str] = None


class ExtractionMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")
    source_file: str
    parsed_at: str = Field(default_factory=utc_now_iso)
    llm_model_used: str
    ocr_used: bool
    page_count: int
    extraction_confidence: float


class ResumeSchema(BaseModel):
    """
    The structured contract handed to skill extraction (src/skills).
    raw_skills must remain exactly as extracted — normalization is
    strictly out of scope here.
    """
    model_config = ConfigDict(extra="ignore")

    contact: ContactInfo = Field(default_factory=ContactInfo)
    summary: Optional[str] = None
    experience: List[ExperienceEntry] = Field(default_factory=list)
    education: List[EducationEntry] = Field(default_factory=list)
    raw_skills: List[str] = Field(default_factory=list)
    projects: List[ProjectEntry] = Field(default_factory=list)
    certifications: List[CertificationEntry] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list)
    awards: List[str] = Field(default_factory=list)
    publications: List[str] = Field(default_factory=list)
    raw_extracted_text: str
    metadata: ExtractionMetadata
