"""Dataset quality and lineage gates required before a training run."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from ..data_prep.io import file_sha256
from ..errors import DataValidationError
from ..rights import RightsManifest, assert_use_allowed


def _read_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise DataValidationError(f"{label} does not exist: {path}")
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except json.JSONDecodeError as exc:
        raise DataValidationError(f"invalid {label} JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise DataValidationError(f"{label} root must be an object")
    return value


def validate_training_gates(
    *,
    dataset_dir: str | Path,
    rights_manifest_path: str | Path,
    quality_approval_path: str | Path,
    scope: str,
) -> tuple[dict[str, Any], RightsManifest, dict[str, Any]]:
    """Validate rights, dataset lineage, manual QA, and required SFT splits."""

    rights = assert_use_allowed(rights_manifest_path, "ml_training", scope)
    dataset_path = Path(dataset_dir)
    dataset_manifest = _read_object(dataset_path / "manifest.json", "dataset manifest")
    approval = _read_object(Path(quality_approval_path), "quality approval")

    failures: list[str] = []
    dataset_id = str(dataset_manifest.get("dataset_id", ""))
    if not dataset_id:
        failures.append("dataset manifest has no dataset_id")
    if dataset_manifest.get("rights_manifest_version") != rights.manifest_version:
        failures.append("dataset rights_manifest_version does not match the current manifest")
    if dataset_manifest.get("rights_manifest_sha256") != file_sha256(rights_manifest_path):
        failures.append("dataset rights_manifest_sha256 does not match the current manifest")
    if approval.get("dataset_id") != dataset_id:
        failures.append("quality approval dataset_id does not match the dataset manifest")
    if str(approval.get("status", "")).lower() != "approved":
        failures.append("quality approval status is not approved")
    if approval.get("approved_for_training") is not True:
        failures.append("approved_for_training must be true")
    if not str(approval.get("reviewed_by", "")).strip():
        failures.append("quality approval reviewed_by is required")
    if not str(approval.get("reviewed_at", "")).strip():
        failures.append("quality approval reviewed_at is required")
    error_rate = approval.get("label_error_rate")
    if not isinstance(error_rate, (int, float)) or not 0 <= float(error_rate) <= 0.05:
        failures.append("label_error_rate must be a number between 0 and 0.05")
    sample_size = approval.get("label_sample_size")
    curated_count = int(dataset_manifest.get("counts", {}).get("curated", 0))
    minimum_sample = min(curated_count, max(500, math.ceil(curated_count * 0.10)))
    if not isinstance(sample_size, int) or sample_size < minimum_sample:
        failures.append(f"label_sample_size must be at least {minimum_sample}")
    for split in ("train", "validation"):
        split_path = dataset_path / "curated" / f"{split}.jsonl"
        if not split_path.is_file() or split_path.stat().st_size == 0:
            failures.append(f"required split is missing or empty: {split_path}")
    if dataset_manifest.get("quality", {}).get("group_leakage") != 0:
        failures.append("dataset manifest reports group leakage")
    if failures:
        raise DataValidationError("training gate denied:\n- " + "\n- ".join(failures))
    return dataset_manifest, rights, approval
