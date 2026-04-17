"""Text analysis helpers."""

from __future__ import annotations

import re

import numpy as np


def safe_mean(values: list[int | float]) -> float:
    """Return the arithmetic mean, or 0.0 for an empty list."""
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def ratio_matching(texts: list[str], pattern: str, flags: int = 0) -> float:
    """Return the ratio of texts matching a regex."""
    if not texts:
        return 0.0
    matches = sum(1 for text in texts if re.search(pattern, text, flags))
    return round(matches / len(texts), 4)


def ratio_containing(texts: list[str], phrases: list[str]) -> float:
    """Return the ratio of texts containing any phrase."""
    if not texts:
        return 0.0
    lowered = [text.lower() for text in texts]
    matches = sum(1 for text in lowered if any(phrase in text for phrase in phrases))
    return round(matches / len(texts), 4)


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    array1 = np.array(vec1)
    array2 = np.array(vec2)
    magnitude1 = float(np.linalg.norm(array1))
    magnitude2 = float(np.linalg.norm(array2))
    if magnitude1 == 0.0 or magnitude2 == 0.0:
        return 0.0
    similarity = float(np.dot(array1, array2) / (magnitude1 * magnitude2))
    return max(0.0, min(similarity, 1.0))
