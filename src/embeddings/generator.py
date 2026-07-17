from __future__ import annotations

from typing import List

import numpy as np

from src.config import CONFIG, get_logger

logger = get_logger("embeddings")


class _EmbeddingModelProvider:
    """Process-wide singleton so the embedding model loads once, not once
    per request."""

    _instance = None
    _model_name = None

    @classmethod
    def get(cls):
        if cls._instance is None or cls._model_name != CONFIG.embedding_model_name:
            from sentence_transformers import SentenceTransformer

            logger.info(f"Loading embedding model '{CONFIG.embedding_model_name}' on {CONFIG.device}...")
            model = SentenceTransformer(CONFIG.embedding_model_name, device=CONFIG.device)
            model.max_seq_length = CONFIG.embedding_max_seq_length
            cls._instance = model
            cls._model_name = CONFIG.embedding_model_name
        return cls._instance


def embed_batch(texts: List[str]) -> np.ndarray:
    """Encodes a list of texts into an (N, dim) float32 array."""
    model = _EmbeddingModelProvider.get()
    embeddings = model.encode(
        texts,
        batch_size=CONFIG.embedding_batch_size,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=CONFIG.normalize_embeddings,
    )
    return embeddings.astype(np.float32)


def embed(text: str) -> np.ndarray:
    """The Stage 3 pipeline contract: single text in, single embedding vector out."""
    return embed_batch([text])[0]
