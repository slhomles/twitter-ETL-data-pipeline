"""Composite automatic evaluation and release-gate report."""

from __future__ import annotations

from typing import Any

from .diversity import diversity_profile
from .memorization import evaluate_memorization
from .stylometry import corpus_profile, profile_distance


def evaluate_corpora(
    *,
    generated_texts: list[str],
    reference_texts: list[str],
    training_texts: list[str],
    config: dict[str, Any],
) -> dict[str, Any]:
    if not generated_texts:
        raise ValueError("generated corpus is empty")
    if not reference_texts:
        raise ValueError("reference corpus is empty")
    style_candidate = corpus_profile(generated_texts)
    style_reference = corpus_profile(reference_texts)
    style_distance = profile_distance(style_candidate, style_reference)
    diversity = diversity_profile(generated_texts)
    memorization = evaluate_memorization(
        generated_texts,
        training_texts,
        span_threshold=int(config["memorization"]["longest_common_token_span"]),
        jaccard_threshold=float(config["memorization"]["fivegram_jaccard"]),
    )
    checks = {
        "style_distance": style_distance
        <= float(config["style"]["max_distance_from_reference"]),
        "distinct_2": diversity["distinct_2"]
        >= float(config["diversity"]["min_distinct_2"]),
        "memorization_flagged_rate": memorization["flagged_rate"]
        <= float(config["memorization"]["max_flagged_rate"]),
        "memorization_exact_matches": memorization["exact_match_count"] == 0,
    }
    return {
        "counts": {
            "generated": len(generated_texts),
            "reference": len(reference_texts),
            "training": len(training_texts),
        },
        "style": {
            "candidate_profile": style_candidate,
            "reference_profile": style_reference,
            "distance": style_distance,
        },
        "diversity": diversity,
        "memorization": memorization,
        "automatic_gate": {"passed": all(checks.values()), "checks": checks},
        "manual_evaluation_required": bool(config["release"]["manual_evaluation_required"]),
    }
