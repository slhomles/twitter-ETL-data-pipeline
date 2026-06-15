from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from style_finetuning.data_prep.pipeline import build_dataset
from style_finetuning.errors import DataValidationError
from style_finetuning.training.gates import validate_training_gates


ROOT = Path(__file__).resolve().parents[1]


class TrainingGateTests(unittest.TestCase):
    def test_synthetic_dataset_with_matching_approval_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            dataset = Path(directory) / "dataset"
            build_dataset(
                input_path=ROOT / "tests/fixtures/synthetic_posts.jsonl",
                output_dir=dataset,
                config_path=ROOT / "configs/data/default.toml",
                rights_manifest_path=ROOT / "tests/fixtures/synthetic_rights_manifest.json",
                scope="test",
            )
            manifest, rights, approval = validate_training_gates(
                dataset_dir=dataset,
                rights_manifest_path=ROOT / "tests/fixtures/synthetic_rights_manifest.json",
                quality_approval_path=ROOT
                / "tests/fixtures/synthetic_quality_approval.json",
                scope="test",
            )
            self.assertEqual(manifest["dataset_id"], approval["dataset_id"])
            self.assertEqual(rights.manifest_version, "fixture-1")

    def test_draft_quality_approval_is_denied(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            dataset = Path(directory) / "dataset"
            build_dataset(
                input_path=ROOT / "tests/fixtures/synthetic_posts.jsonl",
                output_dir=dataset,
                config_path=ROOT / "configs/data/default.toml",
                rights_manifest_path=ROOT / "tests/fixtures/synthetic_rights_manifest.json",
                scope="test",
            )
            with self.assertRaises(DataValidationError):
                validate_training_gates(
                    dataset_dir=dataset,
                    rights_manifest_path=ROOT
                    / "tests/fixtures/synthetic_rights_manifest.json",
                    quality_approval_path=ROOT / "configs/quality_approval.example.json",
                    scope="test",
                )

    def test_changed_rights_document_breaks_dataset_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / "dataset"
            rights_path = ROOT / "tests/fixtures/synthetic_rights_manifest.json"
            build_dataset(
                input_path=ROOT / "tests/fixtures/synthetic_posts.jsonl",
                output_dir=dataset,
                config_path=ROOT / "configs/data/default.toml",
                rights_manifest_path=rights_path,
                scope="test",
            )
            changed_rights = json.loads(rights_path.read_text(encoding="utf-8"))
            changed_rights["notes"] = "Changed after the dataset build."
            changed_path = root / "changed-rights.json"
            changed_path.write_text(json.dumps(changed_rights), encoding="utf-8")
            with self.assertRaisesRegex(DataValidationError, "rights_manifest_sha256"):
                validate_training_gates(
                    dataset_dir=dataset,
                    rights_manifest_path=changed_path,
                    quality_approval_path=ROOT
                    / "tests/fixtures/synthetic_quality_approval.json",
                    scope="test",
                )


if __name__ == "__main__":
    unittest.main()
