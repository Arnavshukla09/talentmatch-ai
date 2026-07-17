from __future__ import annotations

import json
from pathlib import Path
from typing import List

from pydantic import BaseModel, ConfigDict, Field

from src.config import DIRS


class SkillTaxonomyEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    canonical_name: str
    category: str
    aliases: List[str] = Field(default_factory=list)


class SkillTaxonomy(BaseModel):
    model_config = ConfigDict(extra="ignore")
    version: str
    categories: List[str]
    skills: List[SkillTaxonomyEntry]


def _build_seed_taxonomy_entries() -> List[SkillTaxonomyEntry]:
    raw_entries: List[tuple] = [
        # (canonical_name, category, [aliases])
        ("Python", "Programming Languages", ["python3"]),
        ("C", "Programming Languages", []),
        ("C++", "Programming Languages", ["cpp"]),
        ("Java", "Programming Languages", []),
        ("Go", "Programming Languages", ["golang"]),
        ("Rust", "Programming Languages", []),
        ("R", "Programming Languages", []),
        ("Scala", "Programming Languages", []),
        ("JavaScript", "Programming Languages", ["js"]),
        ("TypeScript", "Programming Languages", ["ts"]),
        ("HTML", "Web Development", ["html5"]),
        ("CSS", "Web Development", ["css3"]),
        ("React", "Web Development", ["react.js", "reactjs"]),
        ("Node.js", "Web Development", ["node js", "nodejs"]),
        ("Express.js", "Web Development", ["express"]),
        ("Django", "Web Development", []),
        ("Flask", "Web Development", []),
        ("FastAPI", "Web Development", []),
        ("PyTorch", "Machine Learning & AI", []),
        ("TensorFlow", "Machine Learning & AI", []),
        ("Keras", "Machine Learning & AI", []),
        ("Scikit-learn", "Machine Learning & AI", ["sklearn"]),
        ("OpenCV", "Machine Learning & AI", []),
        ("NumPy", "Machine Learning & AI", []),
        ("Pandas", "Machine Learning & AI", []),
        ("CNN", "Machine Learning & AI", ["convolutional neural network", "convolutional neural networks"]),
        ("LSTM", "Machine Learning & AI", ["long short term memory"]),
        ("YOLO", "Machine Learning & AI", ["yolov8", "yolov5"]),
        ("Computer Vision", "Machine Learning & AI", []),
        ("Reinforcement Learning", "Machine Learning & AI", []),
        ("LightGBM", "Machine Learning & AI", ["light-gbm", "lgbm"]),
        ("XGBoost", "Machine Learning & AI", []),
        ("LangChain", "LLM & RAG", []),
        ("FAISS", "LLM & RAG", []),
        ("Prompt Engineering", "LLM & RAG", []),
        ("Retrieval Augmented Generation", "LLM & RAG", ["rag"]),
        ("Google Gemini", "LLM & RAG", ["gemini api", "gemini"]),
        ("OpenAI API", "LLM & RAG", []),
        ("Docker", "Cloud & DevOps", []),
        ("Kubernetes", "Cloud & DevOps", ["k8s"]),
        ("AWS", "Cloud & DevOps", ["amazon web services"]),
        ("GCP", "Cloud & DevOps", ["google cloud platform", "google cloud"]),
        ("Azure", "Cloud & DevOps", ["microsoft azure"]),
        ("Terraform", "Cloud & DevOps", []),
        ("GitHub Actions", "Cloud & DevOps", ["gh actions"]),
        ("CI/CD", "Cloud & DevOps", ["ci cd", "continuous integration"]),
        ("MLflow", "MLOps", []),
        ("DVC", "MLOps", ["data version control"]),
        ("Evidently AI", "MLOps", []),
        ("Airflow", "MLOps", ["apache airflow"]),
        ("SQL", "Databases", []),
        ("MySQL", "Databases", []),
        ("PostgreSQL", "Databases", ["postgres"]),
        ("MongoDB", "Databases", []),
        ("Redis", "Databases", []),
        ("Snowflake", "Databases", []),
        ("Kafka", "Data Engineering", ["apache kafka"]),
        ("Spark", "Data Engineering", ["apache spark", "pyspark"]),
        ("Hadoop", "Data Engineering", []),
        ("Git", "Tools & Platforms", []),
        ("Jupyter Notebook", "Tools & Platforms", ["jupyter"]),
        ("Tableau", "Tools & Platforms", []),
        ("Power BI", "Tools & Platforms", ["powerbi"]),
        ("Excel", "Tools & Platforms", ["advanced excel", "microsoft excel"]),
        ("Streamlit", "Tools & Platforms", []),
        ("Gradio", "Tools & Platforms", []),
        ("Data Structures and Algorithms", "Core CS Concepts", ["dsa"]),
        ("System Design", "Core CS Concepts", ["system design fundamentals"]),
        ("Statistics", "Core CS Concepts", ["statistical testing"]),
        ("Patient Care", "Healthcare", []),
        ("Clinical Documentation", "Healthcare", []),
        ("HIPAA Compliance", "Healthcare", ["hipaa"]),
        ("Electronic Health Records", "Healthcare", ["ehr", "ehr systems"]),
        ("Financial Modeling", "Finance & Accounting", []),
        ("GAAP", "Finance & Accounting", []),
        ("Bookkeeping", "Finance & Accounting", []),
        ("Tax Preparation", "Finance & Accounting", []),
        ("QuickBooks", "Finance & Accounting", []),
        ("SEO", "Sales & Marketing", ["search engine optimization"]),
        ("Content Marketing", "Sales & Marketing", []),
        ("CRM", "Sales & Marketing", ["salesforce crm", "customer relationship management"]),
        ("Google Analytics", "Sales & Marketing", []),
        ("Copywriting", "Sales & Marketing", []),
        ("Contract Drafting", "Legal", []),
        ("Legal Research", "Legal", []),
        ("Litigation", "Legal", []),
        ("Compliance", "Legal", ["regulatory compliance"]),
        ("Recruiting", "Human Resources", []),
        ("Onboarding", "Human Resources", []),
        ("Payroll Management", "Human Resources", ["payroll"]),
    ]
    return [
        SkillTaxonomyEntry(canonical_name=name, category=category, aliases=aliases)
        for name, category, aliases in raw_entries
    ]


def load_or_seed_taxonomy(taxonomy_path: Path | None = None) -> SkillTaxonomy:
    taxonomy_path = taxonomy_path or (DIRS.get("configs") / "skill_taxonomy.json")
    if taxonomy_path.exists():
        return SkillTaxonomy(**json.loads(taxonomy_path.read_text()))

    entries = _build_seed_taxonomy_entries()
    categories = sorted({entry.category for entry in entries})
    taxonomy = SkillTaxonomy(version="1.0.0-seed", categories=categories, skills=entries)
    taxonomy_path.parent.mkdir(parents=True, exist_ok=True)
    taxonomy_path.write_text(taxonomy.model_dump_json(indent=2), encoding="utf-8")
    return taxonomy
