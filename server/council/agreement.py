"""Pairwise agreement between answers.

Unanimity is a weak signal - models share training data and failure modes. A 3-2 split on a
factual question is the interesting case, which is why this is a matrix you look at rather than a
single number.
"""

from __future__ import annotations

import logging

from server.models.council import AgreementCell
from server.providers.embeddings import EmbeddingClient

log = logging.getLogger(__name__)


def cosine(a: list[float], b: list[float]) -> float:
    import numpy as np

    left, right = np.array(a, dtype=float), np.array(b, dtype=float)
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    return float(np.dot(left, right) / denominator) if denominator else 0.0


async def matrix(
    embedder: EmbeddingClient | None, answers: list[tuple[str, str]]
) -> tuple[list[AgreementCell], str]:
    """Returns the cells and a sentence about what was actually computed."""
    usable = [(label, content) for label, content in answers if content.strip()]
    if len(usable) < 2:
        return [], "Fewer than two answers, so there is nothing to compare."
    if embedder is None:
        return [], (
            "No embedding model is configured, so agreement was not computed. Set "
            "knowledge.embeddings_base_url to enable it."
        )

    try:
        vectors = await embedder.embed([content for _, content in usable])
    except Exception as exc:  # noqa: BLE001 - a missing matrix beats an invented one
        log.warning("council: agreement embedding failed: %s", exc)
        return [], f"Agreement could not be computed: {exc}"

    cells: list[AgreementCell] = []
    for i, (label_a, _) in enumerate(usable):
        for j, (label_b, _) in enumerate(usable):
            if j <= i:
                continue
            cells.append(
                AgreementCell(a=label_a, b=label_b, similarity=cosine(vectors[i], vectors[j]))
            )
    spread = max(c.similarity for c in cells) - min(c.similarity for c in cells) if cells else 0.0
    note = (
        "The answers agree closely; treat that as weak evidence, not confirmation."
        if spread < 0.05
        else "The answers diverge - the pairs with low similarity are where to look."
    )
    return cells, note
