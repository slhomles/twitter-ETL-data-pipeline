from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from style_finetuning.data_prep.io import iter_source_records
from style_finetuning.data_prep.pipeline import build_dataset
from style_finetuning.data_prep.split import assert_no_group_leakage
from style_finetuning.errors import DataValidationError


ROOT = Path(__file__).resolve().parents[1]


class DatasetPipelineTests(unittest.TestCase):
    def _build(self, directory: str) -> tuple[Path, dict]:
        output = Path(directory) / "dataset"
        manifest = build_dataset(
            input_path=ROOT / "tests/fixtures/synthetic_posts.jsonl",
            output_dir=output,
            config_path=ROOT / "configs/data/default.toml",
            rights_manifest_path=ROOT / "tests/fixtures/synthetic_rights_manifest.json",
            scope="test",
        )
        return output, manifest

    def test_end_to_end_counts_lineage_and_splits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output, manifest = self._build(directory)
            self.assertEqual(manifest["counts"]["source"], 16)
            self.assertEqual(manifest["counts"]["normalized"], 16)
            self.assertEqual(manifest["counts"]["curated"], 13)
            self.assertEqual(manifest["counts"]["rejected"], 3)
            self.assertEqual(
                manifest["counts"]["splits"], {"test": 2, "train": 10, "validation": 1}
            )
            curated = [
                record.payload
                for record in iter_source_records(output / "curated/posts.jsonl")
            ]
            assert_no_group_leakage(curated)
            thread_splits = {
                record["split"]
                for record in curated
                if record["conversation_id"] == "thread-015"
            }
            self.assertEqual(thread_splits, {"test"})
            sft_train = next(iter_source_records(output / "curated/train.jsonl")).payload
            self.assertEqual(sft_train["prompt"][0]["role"], "system")
            self.assertEqual(sft_train["completion"][0]["role"], "assistant")

    def test_raw_envelope_preserves_source_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output, _ = self._build(directory)
            original = next(
                iter_source_records(ROOT / "tests/fixtures/synthetic_posts.jsonl")
            ).payload
            raw = next(iter_source_records(output / "raw/source.jsonl")).payload
            self.assertEqual(raw["payload"], original)

    def test_build_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first, first_manifest = self._build(str(Path(directory) / "one"))
            second, second_manifest = self._build(str(Path(directory) / "two"))
            self.assertEqual(first_manifest["dataset_id"], second_manifest["dataset_id"])
            self.assertEqual(first_manifest["artifacts"], second_manifest["artifacts"])
            self.assertTrue((first / "manifest.json").is_file())
            self.assertTrue((second / "manifest.json").is_file())

    def test_refuses_to_overwrite_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "dataset"
            output.mkdir()
            with self.assertRaisesRegex(DataValidationError, "must not already exist"):
                build_dataset(
                    input_path=ROOT / "tests/fixtures/synthetic_posts.jsonl",
                    output_dir=output,
                    config_path=ROOT / "configs/data/default.toml",
                    rights_manifest_path=ROOT
                    / "tests/fixtures/synthetic_rights_manifest.json",
                    scope="test",
                )


if __name__ == "__main__":
    unittest.main()
