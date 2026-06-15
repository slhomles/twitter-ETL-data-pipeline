"""CLI for automatic candidate evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ..config import load_toml
from ..data_prep.io import iter_source_records, write_json
from ..errors import DataValidationError, StylePipelineError
from .metrics import evaluate_corpora


def _extract_text(record: dict[str, Any]) -> str:
    for key in ("generated_text", "text", "text_train", "content"):
        if isinstance(record.get(key), str) and record[key].strip():
            return str(record[key])
    completion = record.get("completion")
    if isinstance(completion, list) and completion:
        last = completion[-1]
        if isinstance(last, dict) and isinstance(last.get("content"), str):
            return str(last["content"])
    messages = record.get("messages")
    if isinstance(messages, list):
        for message in reversed(messages):
            if isinstance(message, dict) and message.get("role") == "assistant":
                return str(message.get("content", ""))
    raise DataValidationError("record contains no supported text field")


def _load_texts(path: str | Path) -> list[str]:
    return [_extract_text(record.payload) for record in iter_source_records(path)]


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="style-evaluate")
    parser.add_argument("--generated", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--training", required=True)
    parser.add_argument("--config", default="configs/evaluation/default.toml")
    parser.add_argument("--output", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    try:
        report = evaluate_corpora(
            generated_texts=_load_texts(args.generated),
            reference_texts=_load_texts(args.reference),
            training_texts=_load_texts(args.training),
            config=load_toml(args.config),
        )
        write_json(args.output, report)
    except (StylePipelineError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
