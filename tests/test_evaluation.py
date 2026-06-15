from __future__ import annotations

import unittest
from pathlib import Path

from style_finetuning.config import load_toml
from style_finetuning.evaluation.memorization import evaluate_memorization
from style_finetuning.evaluation.metrics import evaluate_corpora


ROOT = Path(__file__).resolve().parents[1]


class EvaluationTests(unittest.TestCase):
    def test_exact_training_copy_is_flagged_without_echoing_text(self) -> None:
        text = "A deliberately copied training target with enough words to test the overlap filter."
        report = evaluate_memorization(
            [text], [text], span_threshold=5, jaccard_threshold=0.5
        )
        self.assertEqual(report["exact_match_count"], 1)
        self.assertEqual(report["flagged_count"], 1)
        self.assertNotIn(text, str(report))

    def test_identical_reference_profile_passes_automatic_gate(self) -> None:
        generated = [
            "A clear plan, strong execution, and measurable results!",
            "The team delivered on time. Excellent work!",
        ]
        training = ["A completely separate training sentence about another topic."]
        report = evaluate_corpora(
            generated_texts=generated,
            reference_texts=list(generated),
            training_texts=training,
            config=load_toml(ROOT / "configs/evaluation/default.toml"),
        )
        self.assertTrue(report["automatic_gate"]["passed"])
        self.assertTrue(report["manual_evaluation_required"])


if __name__ == "__main__":
    unittest.main()
