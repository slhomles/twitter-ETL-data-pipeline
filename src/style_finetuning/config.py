"""Small configuration helpers based on Python's standard library."""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path
from typing import Any


def load_toml(path: str | Path) -> dict[str, Any]:
    """Load a TOML document and return a plain dictionary."""

    with Path(path).open("rb") as handle:
        return tomllib.load(handle)


def canonical_json(value: Any) -> str:
    """Serialize a value deterministically for manifests and hashing."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def object_sha256(value: Any) -> str:
    """Return a stable SHA-256 digest for a JSON-serializable object."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
