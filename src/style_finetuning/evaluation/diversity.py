"""Corpus-level n-gram diversity metrics."""

from __future__ import annotations

import re

TOKEN_RE = re.compile(r"[\w']+|[!?]+", re.UNICODE)


def distinct_n(texts: list[str], n: int) -> float:
    observed: list[tuple[str, ...]] = []
    for text in texts:
        tokens = TOKEN_RE.findall(text.casefold())
        observed.extend(
            tuple(tokens[index : index + n])
            for index in range(max(0, len(tokens) - n + 1))
        )
    return len(set(observed)) / len(observed) if observed else 0.0


def diversity_profile(texts: list[str]) -> dict[str, float]:
    return {"distinct_2": distinct_n(texts, 2), "distinct_3": distinct_n(texts, 3)}
