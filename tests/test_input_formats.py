from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from style_finetuning.data_prep.io import iter_source_records
from style_finetuning.data_prep.schema import normalize_post


class InputFormatTests(unittest.TestCase):
    def test_csv_and_wrapped_json_are_supported(self) -> None:
        record = {
            "id": "one",
            "user": "fictional",
            "created_at": "2025-01-01T00:00:00Z",
            "full_text": "HELLO! A fictional update.",
            "lang": "en",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "posts.csv"
            csv_path.write_text(
                "id,user,created_at,full_text,lang\n"
                "one,fictional,2025-01-01T00:00:00Z,HELLO! A fictional update.,en\n",
                encoding="utf-8",
            )
            json_path = root / "posts.json"
            json_path.write_text(json.dumps({"posts": [record]}), encoding="utf-8")
            self.assertEqual(next(iter_source_records(csv_path)).payload["id"], "one")
            self.assertEqual(next(iter_source_records(json_path)).payload, record)

    def test_normalization_preserves_raw_style_and_derives_placeholders(self) -> None:
        source = {
            "tweet_id": "two",
            "username": "fictional",
            "created_at": "Wed Oct 10 20:19:24 +0000 2018",
            "text": "BIG NEWS!!  Visit https://example.invalid and ask @helper",
            "lang": "en",
        }
        result = normalize_post(
            source,
            source_ref="fixture#2",
            rights_manifest_version="fixture-1",
            replace_urls=True,
            replace_mentions=True,
        )
        self.assertEqual(result["text_raw"], source["text"])
        self.assertIn("BIG NEWS!!", result["text_train"])
        self.assertIn("<URL>", result["text_train"])
        self.assertIn("<USER>", result["text_train"])
        self.assertEqual(result["created_at_utc"], "2018-10-10T20:19:24Z")


if __name__ == "__main__":
    unittest.main()
