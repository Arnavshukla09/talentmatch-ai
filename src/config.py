"""
Central configuration, directory layout, and logging.

Consolidates what the original notebook re-defined in nearly every phase's
bootstrap cell (DeviceManager aside, see devices.py): ProjectConfig,
DirectoryManager/DirsAccessor, SecretsManager, and get_logger each appeared
4-6 times with small drifting variations. This module is the one canonical
version; every phase module imports from here instead of redefining its own.

Colab coupling has been removed entirely:
- No `google.colab.drive.mount(...)` — storage is a plain local/container
  directory controlled by the DATA_DIR environment variable.
- No `google.colab.userdata` — secrets come from real environment
  variables (os.environ), which is what both Docker and Hugging Face
  Spaces secrets ultimately inject as.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from src.devices import DeviceManager


def utc_now_iso() -> str:
    """Timezone-aware UTC timestamp (replaces the deprecated datetime.utcnow())."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Directory layout
# ---------------------------------------------------------------------------

class DirectoryManager:
    """
    Defines and creates the fixed artifact directory structure under
    DATA_DIR. Every phase writes only inside these directories, and reads
    only from directories written by an earlier phase — this is the
    storage "contract" between phases.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.paths: Dict[str, Path] = {
            "root": self.root,
            "raw_resumes": self.root / "raw_resumes",
            "raw_job_descriptions": self.root / "raw_job_descriptions",
            "extracted_text": self.root / "extracted_text",
            "parsed_json": self.root / "parsed_json",
            "validated_json": self.root / "validated_json",
            "skills": self.root / "skills",
            "features": self.root / "features",
            "embeddings": self.root / "embeddings",
            "embedding_cache": self.root / "embeddings" / "cache",
            "models": self.root / "models",
            "explainability": self.root / "explainability",
            "reports": self.root / "reports",
            "configs": self.root / "configs",
            "logs": self.root / "logs",
            "checkpoints": self.root / "checkpoints",
        }

    def create_all(self) -> None:
        for path in self.paths.values():
            path.mkdir(parents=True, exist_ok=True)

    def get(self, name: str) -> Path:
        if name not in self.paths:
            raise KeyError(f"Unknown directory key '{name}'. Valid keys: {list(self.paths.keys())}")
        return self.paths[name]

    def __getitem__(self, name: str) -> Path:
        return self.get(name)


PROJECT_ROOT = Path(os.environ.get("DATA_DIR", "./data"))
DIRS = DirectoryManager(root=PROJECT_ROOT)
DIRS.create_all()


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class ProjectConfig:
    """Single source of truth for pipeline settings."""

    project_name: str = "talentmatch-ai"
    project_root: str = str(PROJECT_ROOT)

    device: str = field(default_factory=DeviceManager.get_device)

    groq_model_name: str = "llama-3.3-70b-versatile"
    groq_max_retries: int = 3
    groq_request_timeout_seconds: int = 60

    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_batch_size: int = 32
    embedding_max_seq_length: int = 384
    normalize_embeddings: bool = True

    ocr_confidence_threshold: float = 0.40
    fuzzy_skill_match_threshold: float = 88.0
    semantic_skill_match_threshold: float = 0.62

    random_seed: int = 42

    created_at: str = field(default_factory=utc_now_iso)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.__dict__, indent=2, default=str), encoding="utf-8")


def get_groq_api_key() -> str:
    """
    Loads the Groq API key from a real environment variable.

    Set it via a local .env file (see .env.example) for `docker compose up`,
    or via Space Settings -> Repository secrets on Hugging Face.
    """
    try:
        return os.environ["GROQ_API_KEY"]
    except KeyError as exc:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Copy .env.example to .env and fill it in "
            "(local/Docker), or add it as a repository secret in your Hugging "
            "Face Space settings."
        ) from exc


CONFIG = ProjectConfig()
CONFIG.save(DIRS.get("configs") / "project_config.json")


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def get_logger(name: str, log_dir: Path | None = None) -> logging.Logger:
    """
    Returns a configured logger that writes to both console and a per-day
    log file. Call this at the top of every module instead of print().
    """
    log_dir = log_dir or DIRS.get("logs")
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
