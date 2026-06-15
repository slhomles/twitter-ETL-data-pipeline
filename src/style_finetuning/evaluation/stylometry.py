"""Interpretable style-distribution features for short social posts."""

from __future__ import annotations

import math
import re
from statistics import fmean

WORD_RE = re.compile(r"[\w']+", re.UNICODE)
SENTENCE_RE = re.compile(r"[.!?]+")
REPEATED_PUNCTUATION_RE = re.compile(r"([!?])\1+")


def text_features(text: str) -> dict[str, float]:
    words = WORD_RE.findall(text)
    letters = [character for character in text if character.isalpha()]
    uppercase = [character for character in letters if character.isupper()]
    sentences = SENTENCE_RE.findall(text)
    return {
        "characters": float(len(text)),
        "words": float(len(words)),
        "sentences": float(max(1, len(sentences))),
        "uppercase_ratio": len(uppercase) / len(letters) if letters else 0.0,
        "exclamations_per_100_chars": text.count("!") * 100 / max(1, len(text)),
        "questions_per_100_chars": text.count("?") * 100 / max(1, len(text)),
        "hashtags_per_post": float(len(re.findall(r"(?<!\w)#[\w_]+", text))),
        "mentions_per_post": float(len(re.findall(r"(?<!\w)@[\w_]+", text))),
        "repeated_punctuation_per_post": float(len(REPEATED_PUNCTUATION_RE.findall(text))),
    }


def corpus_profile(texts: list[str]) -> dict[str, float]:
    if not texts:
        return {}
    features = [text_features(text) for text in texts]
    return {
        name: fmean(feature[name] for feature in features)
        for name in sorted(features[0])
    }


def profile_distance(candidate: dict[str, float], reference: dict[str, float]) -> float:
    if not candidate or not reference:
        return math.inf
    natural_scales = {
        "characters": 100.0,
        "words": 20.0,
        "sentences": 3.0,
        "uppercase_ratio": 0.2,
        "exclamations_per_100_chars": 3.0,
        "questions_per_100_chars": 2.0,
        "hashtags_per_post": 1.0,
        "mentions_per_post": 1.0,
        "repeated_punctuation_per_post": 1.0,
    }
    differences = [
        min(3.0, abs(candidate[name] - reference[name]) / natural_scales[name])
        for name in natural_scales
    ]
    return fmean(differences)
