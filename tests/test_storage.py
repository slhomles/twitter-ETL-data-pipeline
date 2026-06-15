from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from style_finetuning.data_prep.pipeline import build_dataset
from style_finetuning.errors import DataValidationError
from style_finetuning.storage import parse_s3_uri, publish_directory_to_s3


ROOT = Path(__file__).resolve().parents[1]


class FakeS3Client:
    def __init__(self, *, occupied: bool = False) -> None:
        self.occupied = occupied
        self.uploads: list[tuple[str, str, str, dict]] = []

    def list_objects_v2(self, **_: object) -> dict:
        return {"KeyCount": 1 if self.occupied else 0}

    def upload_file(self, path: str, bucket: str, key: str, ExtraArgs: dict) -> None:
        self.uploads.append((path, bucket, key, ExtraArgs))


class StorageTests(unittest.TestCase):
    def test_parse_s3_uri_requires_bucket_and_prefix(self) -> None:
        self.assertEqual(
            parse_s3_uri("s3://private-bucket/datasets/v1"),
            ("private-bucket", "datasets/v1"),
        )
        with self.assertRaises(DataValidationError):
            parse_s3_uri("s3://private-bucket")

    def test_manifest_is_uploaded_last_with_encryption(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            dataset = Path(directory) / "dataset"
            build_dataset(
                input_path=ROOT / "tests/fixtures/synthetic_posts.jsonl",
                output_dir=dataset,
                config_path=ROOT / "configs/data/default.toml",
                rights_manifest_path=ROOT / "tests/fixtures/synthetic_rights_manifest.json",
                scope="test",
            )
            client = FakeS3Client()
            result = publish_directory_to_s3(
                local_directory=dataset,
                destination="s3://private-bucket/datasets/fixture-v1",
                rights_manifest_path=ROOT / "tests/fixtures/synthetic_rights_manifest.json",
                scope="test",
                client=client,
            )
            self.assertEqual(result["uploaded_files"], len(client.uploads))
            self.assertTrue(client.uploads[-1][2].endswith("/manifest.json"))
            self.assertTrue(
                all(upload[3] == {"ServerSideEncryption": "AES256"} for upload in client.uploads)
            )

    def test_non_empty_prefix_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            dataset = Path(directory) / "dataset"
            build_dataset(
                input_path=ROOT / "tests/fixtures/synthetic_posts.jsonl",
                output_dir=dataset,
                config_path=ROOT / "configs/data/default.toml",
                rights_manifest_path=ROOT / "tests/fixtures/synthetic_rights_manifest.json",
                scope="test",
            )
            with self.assertRaisesRegex(DataValidationError, "non-empty S3 prefix"):
                publish_directory_to_s3(
                    local_directory=dataset,
                    destination="s3://private-bucket/datasets/existing",
                    rights_manifest_path=ROOT
                    / "tests/fixtures/synthetic_rights_manifest.json",
                    scope="test",
                    client=FakeS3Client(occupied=True),
                )


if __name__ == "__main__":
    unittest.main()
