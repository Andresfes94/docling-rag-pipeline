from __future__ import annotations

import functools
import logging

import numpy as np
from sentence_transformers import SentenceTransformer

_log = logging.getLogger(__name__)


@functools.lru_cache(maxsize=4)
def _get_model(model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> SentenceTransformer:
    _log.info("Loading embedding model: %s...", model_name)
    return SentenceTransformer(model_name, device="cpu")


def embed_text(
    text: str,
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
) -> np.ndarray:
    model = _get_model(model_name)
    return model.encode(text)


def embed_batch(
    texts: list[str],
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    batch_size: int = 32,
    show_progress: bool = False,
) -> np.ndarray:
    model = _get_model(model_name)
    return model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=show_progress,
    )


def embedding_dimension(model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> int:
    model = _get_model(model_name)
    return model.get_sentence_embedding_dimension()
