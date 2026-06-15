"""Input and artifact I/O for local deterministic dataset builds."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import DataValidationError


@dataclass(frozen=True)
class SourceRecord:
    row_number: int
    payload: dict[str, Any]


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ensure_mapping(value: Any, row_number: int) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise DataValidationError(f"record {row_number} is not an object")
    return dict(value)


def iter_source_records(path: str | Path) -> Iterator[SourceRecord]:
    """Read CSV, JSON, or JSONL without requiring pandas."""

    source_path = Path(path)
    if not source_path.is_file():
        raise DataValidationError(f"input file does not exist: {source_path}")
    suffix = source_path.suffix.lower()

    if suffix in {".jsonl", ".ndjson"}:
        with source_path.open("r", encoding="utf-8-sig") as handle:
            for row_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise DataValidationError(
                        f"invalid JSON on line {row_number}: {exc}"
                    ) from exc
                yield SourceRecord(row_number, _ensure_mapping(value, row_number))
        return

    if suffix == ".csv":
        with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row_number, value in enumerate(csv.DictReader(handle), start=2):
                yield SourceRecord(row_number, dict(value))
        return

    if suffix == ".json":
        try:
            with source_path.open("r", encoding="utf-8-sig") as handle:
                root = json.load(handle)
        except json.JSONDecodeError as exc:
            raise DataValidationError(f"invalid JSON: {exc}") from exc
        if isinstance(root, Mapping):
            for key in ("data", "posts", "tweets", "records"):
                if isinstance(root.get(key), list):
                    root = root[key]
                    break
        if not isinstance(root, list):
            raise DataValidationError(
                "JSON input must be a list or contain a data/posts/tweets/records list"
            )
        for row_number, value in enumerate(root, start=1):
            yield SourceRecord(row_number, _ensure_mapping(value, row_number))
        return

    raise DataValidationError(f"unsupported input extension: {suffix or '<none>'}")


def _atomic_text_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise DataValidationError(f"refusing to overwrite existing artifact: {path}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def write_jsonl(path: str | Path, records: Iterable[Mapping[str, Any]]) -> None:
    lines = [json.dumps(dict(record), ensure_ascii=False, sort_keys=True) for record in records]
    text = "\n".join(lines)
    if lines:
        text += "\n"
    _atomic_text_write(Path(path), text)


def write_json(path: str | Path, value: Any) -> None:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    _atomic_text_write(Path(path), text)
