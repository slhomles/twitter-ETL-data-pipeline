"""End-to-end rights-gated dataset builder."""

from __future__ import annotations

import copy
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from ..config import load_toml, object_sha256
from ..errors import DataValidationError
from ..labeling import label_post
from ..rights import assert_use_allowed
from .dedup import cluster_near_duplicates, remove_exact_duplicates
from .io import file_sha256, iter_source_records, write_json, write_jsonl
from .schema import is_link_only, normalize_post
from .split import assign_grouped_temporal_splits, assert_no_group_leakage


def _required_section(config: dict[str, Any], name: str) -> dict[str, Any]:
    value = config.get(name)
    if not isinstance(value, dict):
        raise DataValidationError(f"config section [{name}] is required")
    return value


def _reject_reason(record: dict[str, Any], dataset_config: dict[str, Any]) -> str | None:
    allowed_languages = {str(item).lower() for item in dataset_config["allowed_languages"]}
    if allowed_languages and record["lang"] not in allowed_languages:
        return f"language_not_allowed:{record['lang']}"
    allowed_authors = {str(item) for item in dataset_config.get("allowed_author_ids", [])}
    if allowed_authors and record["author_id"] not in allowed_authors:
        return f"author_not_allowed:{record['author_id']}"
    excluded_references = {
        str(item).lower() for item in dataset_config["exclude_reference_types"]
    }
    matched = excluded_references.intersection(record["reference_types"])
    if matched:
        return f"reference_type_excluded:{sorted(matched)[0]}"
    if len(record["text_train"].strip()) < int(dataset_config["min_text_chars"]):
        return "text_too_short"
    if is_link_only(record["text_raw"]):
        return "link_only"
    return None


def _sft_record(record: dict[str, Any], prompt_config: dict[str, Any]) -> dict[str, Any]:
    user_prompt = "\n".join(
        (
            f"Topic: {record['topic']}",
            f"Intent: {record['intent']}",
            f"Length: {record['length_bucket']}",
            f"Time context: {prompt_config['time_context']}",
        )
    )
    return {
        "prompt": [
            {"role": "system", "content": prompt_config["system"]},
            {"role": "user", "content": user_prompt},
        ],
        "completion": [{"role": "assistant", "content": record["text_train"]}],
        "metadata": {
            "post_id": record["post_id"],
            "created_at_utc": record["created_at_utc"],
            "topic": record["topic"],
            "intent": record["intent"],
            "tone_tags": record["tone_tags"],
            "near_dup_cluster_id": record["near_dup_cluster_id"],
            "conversation_id": record["conversation_id"],
            "rights_manifest_version": record["rights_manifest_version"],
        },
    }


def _artifact_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    }


def build_dataset(
    *,
    input_path: str | Path,
    output_dir: str | Path,
    config_path: str | Path,
    rights_manifest_path: str | Path,
    scope: str = "internal_research",
) -> dict[str, Any]:
    """Build immutable raw, normalized, rejected, and curated artifacts."""

    source_path = Path(input_path)
    target_path = Path(output_dir)
    if target_path.exists():
        raise DataValidationError(f"output path must not already exist: {target_path}")
    rights = assert_use_allowed(rights_manifest_path, "dataset_build", scope)
    config = load_toml(config_path)
    dataset_config = _required_section(config, "dataset")
    dedup_config = _required_section(config, "dedup")
    split_config = _required_section(config, "split")
    prompt_config = _required_section(config, "prompt")

    source_records = list(iter_source_records(source_path))
    if not source_records:
        raise DataValidationError("input contains no records")
    raw_envelopes: list[dict[str, Any]] = []
    normalized: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for source_record in source_records:
        source_ref = f"{source_path.name}#row={source_record.row_number}"
        raw_envelopes.append(
            {
                "source_ref": source_ref,
                "source_row": source_record.row_number,
                "payload": copy.deepcopy(source_record.payload),
            }
        )
        try:
            record = normalize_post(
                source_record.payload,
                source_ref=source_ref,
                rights_manifest_version=rights.manifest_version,
                replace_urls=bool(dataset_config["replace_urls"]),
                replace_mentions=bool(dataset_config["replace_mentions"]),
            )
        except DataValidationError as exc:
            rejected.append(
                {
                    "stage": "normalize",
                    "reason": str(exc),
                    "source_ref": source_ref,
                    "payload": copy.deepcopy(source_record.payload),
                }
            )
            continue
        normalized.append(record)

    filtered: list[dict[str, Any]] = []
    for record in normalized:
        reason = _reject_reason(record, dataset_config)
        if reason:
            rejected.append({"stage": "filter", "reason": reason, "record": record})
        else:
            filtered.append(record)

    exact_kept, exact_rejected = remove_exact_duplicates(filtered)
    rejected.extend(
        {"stage": "exact_dedup", "reason": "exact_duplicate", "record": record}
        for record in exact_rejected
    )
    clustered, cluster_rejected = cluster_near_duplicates(
        exact_kept,
        ngram_size=int(dedup_config["ngram_size"]),
        similarity_threshold=float(dedup_config["similarity_threshold"]),
        permutations=int(dedup_config["minhash_permutations"]),
        bands=int(dedup_config["minhash_bands"]),
        exhaustive_limit=int(dedup_config["exhaustive_limit"]),
        max_per_cluster=int(dataset_config["max_per_near_duplicate_cluster"]),
    )
    rejected.extend(
        {
            "stage": "near_dedup",
            "reason": "near_duplicate_cluster_cap",
            "record": record,
        }
        for record in cluster_rejected
    )
    labeled = [label_post(record) for record in clustered]
    curated = assign_grouped_temporal_splits(
        labeled,
        train_ratio=float(split_config["train_ratio"]),
        validation_ratio=float(split_config["validation_ratio"]),
        test_ratio=float(split_config["test_ratio"]),
    )
    assert_no_group_leakage(curated)
    split_counts = Counter(record["split"] for record in curated)
    if len(curated) >= 3 and set(split_counts) != {"train", "validation", "test"}:
        raise DataValidationError(f"expected all three splits, got: {dict(split_counts)}")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{target_path.name}.", dir=target_path.parent
    ) as temporary_directory:
        staging = Path(temporary_directory)
        write_jsonl(staging / "raw" / "source.jsonl", raw_envelopes)
        write_jsonl(staging / "normalized" / "posts.jsonl", normalized)
        write_jsonl(staging / "rejected" / "posts.jsonl", rejected)
        write_jsonl(staging / "curated" / "posts.jsonl", curated)
        for split in ("train", "validation", "test"):
            write_jsonl(
                staging / "curated" / f"{split}.jsonl",
                (
                    _sft_record(record, prompt_config)
                    for record in curated
                    if record["split"] == split
                ),
            )
        dataset_identity = {
            "dataset_version": str(dataset_config["version"]),
            "input_name": source_path.name,
            "input_sha256": file_sha256(source_path),
            "config_sha256": object_sha256(config),
            "rights_manifest_version": rights.manifest_version,
            "rights_manifest_sha256": file_sha256(rights_manifest_path),
            "scope": scope,
        }
        manifest = {
            **dataset_identity,
            "dataset_id": object_sha256(dataset_identity)[:20],
            "counts": {
                "source": len(source_records),
                "normalized": len(normalized),
                "curated": len(curated),
                "rejected": len(rejected),
                "splits": dict(sorted(split_counts.items())),
            },
            "quality": {
                "group_leakage": 0,
                "manual_label_review_required": True,
                "raw_is_lossless_envelope": True,
            },
            "artifacts": _artifact_hashes(staging),
        }
        write_json(staging / "manifest.json", manifest)
        staging.replace(target_path)
    return manifest
