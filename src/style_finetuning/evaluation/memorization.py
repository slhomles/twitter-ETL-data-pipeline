"""Nearest-neighbor overlap checks without emitting private training text."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

TOKEN_RE = re.compile(r"[\w']+|[!?]+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text.casefold())


def _ngrams(tokens: list[str], size: int) -> frozenset[tuple[str, ...]]:
    if len(tokens) < size:
        return frozenset({tuple(tokens)}) if tokens else frozenset()
    return frozenset(
        tuple(tokens[index : index + size])
        for index in range(len(tokens) - size + 1)
    )


def _longest_common_span(left: list[str], right: list[str]) -> int:
    previous = [0] * (len(right) + 1)
    best = 0
    for left_token in left:
        current = [0] * (len(right) + 1)
        for index, right_token in enumerate(right, start=1):
            if left_token == right_token:
                current[index] = previous[index - 1] + 1
                best = max(best, current[index])
        previous = current
    return best


@dataclass(frozen=True)
class MemorizationMatch:
    generated_index: int
    training_index: int
    exact_match: bool
    longest_common_token_span: int
    fivegram_jaccard: float


class MemorizationIndex:
    def __init__(self, training_texts: list[str]) -> None:
        self.training_tokens = [_tokens(text) for text in training_texts]
        self.training_ngrams = [_ngrams(tokens, 5) for tokens in self.training_tokens]
        self.fingerprints: dict[tuple[str, ...], list[int]] = defaultdict(list)
        self.inverted: dict[tuple[str, ...], set[int]] = defaultdict(set)
        for index, tokens in enumerate(self.training_tokens):
            self.fingerprints[tuple(tokens)].append(index)
            for ngram in self.training_ngrams[index]:
                self.inverted[ngram].add(index)

    def closest(self, text: str, generated_index: int) -> MemorizationMatch:
        tokens = _tokens(text)
        ngrams = _ngrams(tokens, 5)
        exact_indexes = self.fingerprints.get(tuple(tokens), [])
        candidates = set(exact_indexes)
        for ngram in ngrams:
            candidates.update(self.inverted.get(ngram, set()))
        if not candidates:
            return MemorizationMatch(generated_index, -1, False, 0, 0.0)
        best: MemorizationMatch | None = None
        for training_index in sorted(candidates):
            training_ngrams = self.training_ngrams[training_index]
            union = ngrams | training_ngrams
            jaccard = len(ngrams & training_ngrams) / len(union) if union else 1.0
            match = MemorizationMatch(
                generated_index=generated_index,
                training_index=training_index,
                exact_match=tuple(tokens) == tuple(self.training_tokens[training_index]),
                longest_common_token_span=_longest_common_span(
                    tokens, self.training_tokens[training_index]
                ),
                fivegram_jaccard=jaccard,
            )
            if best is None or (
                match.exact_match,
                match.longest_common_token_span,
                match.fivegram_jaccard,
            ) > (
                best.exact_match,
                best.longest_common_token_span,
                best.fivegram_jaccard,
            ):
                best = match
        assert best is not None
        return best


def evaluate_memorization(
    generated_texts: list[str],
    training_texts: list[str],
    *,
    span_threshold: int,
    jaccard_threshold: float,
) -> dict[str, object]:
    index = MemorizationIndex(training_texts)
    matches = [index.closest(text, item) for item, text in enumerate(generated_texts)]
    flagged = [
        match
        for match in matches
        if match.exact_match
        or match.longest_common_token_span >= span_threshold
        or match.fivegram_jaccard >= jaccard_threshold
    ]
    return {
        "generated_count": len(generated_texts),
        "training_count": len(training_texts),
        "exact_match_count": sum(match.exact_match for match in matches),
        "flagged_count": len(flagged),
        "flagged_rate": len(flagged) / len(generated_texts) if generated_texts else 0.0,
        "max_longest_common_token_span": max(
            (match.longest_common_token_span for match in matches), default=0
        ),
        "max_fivegram_jaccard": max((match.fivegram_jaccard for match in matches), default=0.0),
        "flagged_examples": [
            {
                "generated_index": match.generated_index,
                "training_index": match.training_index,
                "exact_match": match.exact_match,
                "longest_common_token_span": match.longest_common_token_span,
                "fivegram_jaccard": round(match.fivegram_jaccard, 6),
            }
            for match in flagged
        ],
    }
