from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from style_finetuning.errors import RightsGateError
from style_finetuning.rights import assert_use_allowed


ROOT = Path(__file__).resolve().parents[1]


class RightsGateTests(unittest.TestCase):
    def test_approved_synthetic_fixture_is_allowed(self) -> None:
        manifest = assert_use_allowed(
            ROOT / "tests/fixtures/synthetic_rights_manifest.json",
            "dataset_build",
            "test",
        )
        self.assertEqual(manifest.manifest_version, "fixture-1")

    def test_draft_manifest_is_denied(self) -> None:
        with self.assertRaises(RightsGateError):
            assert_use_allowed(
                ROOT / "configs/rights_manifest.example.json",
                "dataset_build",
                "internal_research",
            )

    def test_x_content_without_platform_approval_is_denied(self) -> None:
        payload = {
            "manifest_version": "test-x",
            "status": "approved",
            "approved_uses": ["ml_training"],
            "allowed_scopes": ["test"],
            "reviewed_by": "test",
            "reviewed_at": "2026-09-04T00:00:00Z",
            "sources": [
                {
                    "source_id": "x-source",
                    "source_type": "x_api",
                    "contains_x_content": True,
                    "ml_training_allowed": True,
                    "redistribution_allowed": False,
                    "evidence_ref": "internal assertion only",
                    "platform_approval_ref": "",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rights.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(RightsGateError, "platform_approval_ref"):
                assert_use_allowed(path, "ml_training", "test")


if __name__ == "__main__":
    unittest.main()
