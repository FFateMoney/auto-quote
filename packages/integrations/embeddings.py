from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache

import numpy as np


TOKEN_RE = re.compile(r"[A-Za-z0-9_.+\-/]+|[\u4e00-\u9fff]")
DEFAULT_EMBEDDING_DIM = 256


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(str(text or ""))]


@lru_cache(maxsize=4096)
def _embed_cached(text: str, dim: int) -> tuple[float, ...]:
    vector = np.zeros(dim, dtype=np.float32)
    tokens = _tokenize(text)
    if not tokens:
        return tuple(vector.tolist())

    for token in tokens:
        digest = hashlib.sha1(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        weight = 1.0 + math.log1p(len(token))
        vector[index] += sign * weight

    norm = float(np.linalg.norm(vector))
    if norm > 0:
        vector /= norm
    return tuple(float(value) for value in vector.tolist())


class EmbeddingAdapter:
    def __init__(self, *, dim: int = DEFAULT_EMBEDDING_DIM) -> None:
        self.dim = dim

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        rows = [_embed_cached(str(text or ""), self.dim) for text in texts]
        return np.asarray(rows, dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_texts([text])[0]
