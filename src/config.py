"""
src/config.py  —  TalentMatch v2 central configuration.

Groq is optional and used for coaching after native scoring.
Python handles embeddings, PDF extraction and request orchestration.
All ML computation runs inside the C++ engine.
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
    """Timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def get_groq_api_key() -> str:
    """Get Groq API key for AI suggestions."""
    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        logging.getLogger("config").warning("GROQ_API_KEY environment variable not set.")
    return key


# ---------------------------------------------------------------------------
# Directory layout
# ---------------------------------------------------------------------------

class DirectoryManager:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.paths: Dict[str, Path] = {
            "root":           self.root,
            "raw_resumes":    self.root / "raw_resumes",
            "extracted_text": self.root / "extracted_text",
            "embeddings":     self.root / "embeddings",
            "embedding_cache":self.root / "embeddings" / "cache",
            "models":         self.root / "models",
            "configs":        self.root / "configs",
            "logs":           self.root / "logs",
        }

    def create_all(self) -> None:
        for path in self.paths.values():
            path.mkdir(parents=True, exist_ok=True)

    def get(self, name: str) -> Path:
        if name not in self.paths:
            raise KeyError(f"Unknown directory key '{name}'. Valid: {list(self.paths.keys())}")
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
    """Single source of truth for v2 pipeline settings."""

    project_name: str = "talentmatch-ai-v2"
    project_root: str = str(PROJECT_ROOT)

    device: str = field(default_factory=DeviceManager.get_device)

    # Embedding model (local, no network after first download)
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_batch_size: int = 32
    embedding_max_seq_length: int = 384
    normalize_embeddings: bool = True

    # C++ engine library path (empty = auto-discover)
    cpp_library_path: str = ""

    # XGBoost model path
    xgboost_model_path: str = "models/xgboost_model.json"

    # Skill taxonomy JSON path (passed to C++ engine)
    taxonomy_path: str = str(PROJECT_ROOT / "configs" / "skill_taxonomy.json")

    random_seed: int = 42
    created_at: str = field(default_factory=utc_now_iso)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.__dict__, indent=2, default=str), encoding="utf-8")


CONFIG = ProjectConfig()
CONFIG.save(DIRS.get("configs") / "project_config.json")


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def get_logger(name: str, log_dir: Path | None = None) -> logging.Logger:
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
