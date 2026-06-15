"""Deterministic safety policy wrapped around model inference."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Protocol

from ..evaluation.memorization import MemorizationIndex

SYNTHETIC_DISCLOSURE = (
    "AI-generated parody/style study; not a real quote or official statement."
)

REQUEST_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "impersonation",
        re.compile(
            r"\b(pretend|act|speak|write)\s+(?:to\s+be\s+|as\s+)(donald\s+)?trump\b|"
            r"\b(as|from)\s+donald\s+(?:j\.?\s+)?trump\b|"
            r"\b(giả\s+(?:vờ|danh)|đóng\s+vai)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "fabricated_attribution",
        re.compile(
            r"\b(official statement|authentic quote|real quote|"
            r"phát ngôn chính thức|trích dẫn thật)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "disclosure_evasion",
        re.compile(
            r"\b(remove|hide|omit|without|bypass)\b.{0,30}\b(disclosure|label|warning)\b|"
            r"\b(bỏ|ẩn|không)\b.{0,30}\b(nhãn|cảnh báo)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "current_event_deception",
        re.compile(
            r"\b(breaking news|announce today as fact|fake emergency|"
            r"tin nóng giả|sự kiện vừa xảy ra)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "targeted_political_persuasion",
        re.compile(
            r"\b(target|microtarget|persuade)\b.{0,40}\b(voter|voters|electorate)\b|"
            r"\b(fundrais(?:e|ing)|campaign donation|thuyết phục cử tri|"
            r"nhắm mục tiêu cử tri|quyên góp chiến dịch)\b",
            re.IGNORECASE,
        ),
    ),
)

OUTPUT_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "identity_reference",
        re.compile(r"\bdonald\s+(?:j\.?\s+)?trump\b", re.IGNORECASE),
    ),
    (
        "official_attribution",
        re.compile(
            r"\b(i am|this is|official statement|speaking as president|signed,? the president)\b",
            re.IGNORECASE,
        ),
    ),
)


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip()


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    code: str
    reason: str


@dataclass(frozen=True)
class GuardedGeneration:
    text: str
    synthetic: bool
    disclosure: str
    model_version: str


class GenerationBackend(Protocol):
    model_version: str

    def generate(self, *, topic: str, intent: str, length: str, historical_context: str) -> str:
        ...


def check_request(*, topic: str, intent: str, historical_context: str) -> PolicyDecision:
    combined = _normalize("\n".join((topic, intent, historical_context)))
    for code, pattern in REQUEST_RULES:
        if pattern.search(combined):
            return PolicyDecision(False, code, f"request blocked by {code} policy")
    return PolicyDecision(True, "allowed", "request is within the internal style-study scope")


class GuardedGenerator:
    def __init__(
        self,
        backend: GenerationBackend,
        *,
        training_texts: list[str] | None = None,
        overlap_span_threshold: int = 20,
        overlap_jaccard_threshold: float = 0.50,
    ) -> None:
        self.backend = backend
        self.memorization_index = MemorizationIndex(training_texts or [])
        self.has_training_texts = bool(training_texts)
        self.overlap_span_threshold = overlap_span_threshold
        self.overlap_jaccard_threshold = overlap_jaccard_threshold

    def generate(
        self, *, topic: str, intent: str, length: str, historical_context: str
    ) -> tuple[PolicyDecision, GuardedGeneration | None]:
        request_decision = check_request(
            topic=topic, intent=intent, historical_context=historical_context
        )
        if not request_decision.allowed:
            return request_decision, None
        text = _normalize(
            self.backend.generate(
                topic=topic,
                intent=intent,
                length=length,
                historical_context=historical_context,
            )
        )
        if not text:
            return PolicyDecision(False, "empty_generation", "model returned empty text"), None
        for code, pattern in OUTPUT_RULES:
            if pattern.search(text):
                return PolicyDecision(False, code, f"output blocked by {code} policy"), None
        if self.has_training_texts:
            match = self.memorization_index.closest(text, 0)
            if (
                match.exact_match
                or match.longest_common_token_span >= self.overlap_span_threshold
                or match.fivegram_jaccard >= self.overlap_jaccard_threshold
            ):
                return (
                    PolicyDecision(
                        False,
                        "training_overlap",
                        "output is too similar to a training example",
                    ),
                    None,
                )
        return (
            PolicyDecision(True, "allowed", "output passed policy checks"),
            GuardedGeneration(
                text=text,
                synthetic=True,
                disclosure=SYNTHETIC_DISCLOSURE,
                model_version=self.backend.model_version,
            ),
        )
