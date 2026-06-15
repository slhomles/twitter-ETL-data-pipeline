"""Fail-closed validation for data and model usage rights."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import RightsGateError

APPROVED_STATUSES = {"approved", "conditional"}
KNOWN_USES = {"dataset_build", "ml_training", "internal_serving", "distribution"}


@dataclass(frozen=True)
class SourceRights:
    source_id: str
    source_type: str
    contains_x_content: bool
    ml_training_allowed: bool
    redistribution_allowed: bool
    evidence_ref: str
    platform_approval_ref: str = ""

    @classmethod
    def from_mapping(cls, value: dict[str, Any], index: int) -> "SourceRights":
        required = {
            "source_id",
            "source_type",
            "contains_x_content",
            "ml_training_allowed",
            "redistribution_allowed",
            "evidence_ref",
        }
        missing = sorted(required - value.keys())
        if missing:
            raise RightsGateError(f"rights source #{index} is missing: {', '.join(missing)}")
        for field in ("contains_x_content", "ml_training_allowed", "redistribution_allowed"):
            if not isinstance(value[field], bool):
                raise RightsGateError(f"rights source #{index}.{field} must be boolean")
        return cls(
            source_id=str(value["source_id"]).strip(),
            source_type=str(value["source_type"]).strip().lower(),
            contains_x_content=value["contains_x_content"],
            ml_training_allowed=value["ml_training_allowed"],
            redistribution_allowed=value["redistribution_allowed"],
            evidence_ref=str(value["evidence_ref"]).strip(),
            platform_approval_ref=str(value.get("platform_approval_ref", "")).strip(),
        )


@dataclass(frozen=True)
class RightsManifest:
    manifest_version: str
    status: str
    approved_uses: frozenset[str]
    allowed_scopes: frozenset[str]
    reviewed_by: str
    reviewed_at: str
    sources: tuple[SourceRights, ...]
    notes: str = ""

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "RightsManifest":
        required = {
            "manifest_version",
            "status",
            "approved_uses",
            "allowed_scopes",
            "reviewed_by",
            "reviewed_at",
            "sources",
        }
        missing = sorted(required - value.keys())
        if missing:
            raise RightsGateError(f"rights manifest is missing: {', '.join(missing)}")
        if not isinstance(value["approved_uses"], list):
            raise RightsGateError("approved_uses must be a list")
        if not isinstance(value["allowed_scopes"], list):
            raise RightsGateError("allowed_scopes must be a list")
        if not isinstance(value["sources"], list) or not value["sources"]:
            raise RightsGateError("sources must be a non-empty list")
        uses = frozenset(str(item).strip() for item in value["approved_uses"])
        unknown_uses = sorted(uses - KNOWN_USES)
        if unknown_uses:
            raise RightsGateError(f"unknown approved uses: {', '.join(unknown_uses)}")
        return cls(
            manifest_version=str(value["manifest_version"]).strip(),
            status=str(value["status"]).strip().lower(),
            approved_uses=uses,
            allowed_scopes=frozenset(str(item).strip() for item in value["allowed_scopes"]),
            reviewed_by=str(value["reviewed_by"]).strip(),
            reviewed_at=str(value["reviewed_at"]).strip(),
            sources=tuple(
                SourceRights.from_mapping(source, index)
                for index, source in enumerate(value["sources"])
            ),
            notes=str(value.get("notes", "")).strip(),
        )


def load_rights_manifest(path: str | Path) -> RightsManifest:
    """Read and validate the shape of a JSON rights manifest."""

    manifest_path = Path(path)
    if not manifest_path.is_file():
        raise RightsGateError(f"rights manifest does not exist: {manifest_path}")
    try:
        with manifest_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise RightsGateError(f"invalid rights manifest JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RightsGateError("rights manifest root must be an object")
    return RightsManifest.from_mapping(payload)


def assert_use_allowed(
    manifest_path: str | Path,
    requested_use: str,
    scope: str = "internal_research",
) -> RightsManifest:
    """Return the manifest only when every relevant source permits the use."""

    if requested_use not in KNOWN_USES:
        raise RightsGateError(f"unknown requested use: {requested_use}")
    manifest = load_rights_manifest(manifest_path)
    failures: list[str] = []
    if manifest.status not in APPROVED_STATUSES:
        failures.append(f"manifest status is {manifest.status!r}, not approved")
    if requested_use not in manifest.approved_uses:
        failures.append(f"use {requested_use!r} is not listed in approved_uses")
    if scope not in manifest.allowed_scopes:
        failures.append(f"scope {scope!r} is not listed in allowed_scopes")
    if not manifest.reviewed_by or not manifest.reviewed_at:
        failures.append("reviewed_by and reviewed_at are required")

    for source in manifest.sources:
        label = source.source_id or "<unnamed>"
        if not source.source_id or not source.evidence_ref:
            failures.append(f"source {label!r} lacks source_id or evidence_ref")
        if requested_use in {"dataset_build", "ml_training"} and not source.ml_training_allowed:
            failures.append(f"source {label!r} does not permit ML training")
        if requested_use == "distribution" and not source.redistribution_allowed:
            failures.append(f"source {label!r} does not permit redistribution")
        if (
            source.contains_x_content
            and source.source_type in {"x_api", "x_scrape", "x_export"}
            and requested_use in {"dataset_build", "ml_training"}
            and not source.platform_approval_ref
        ):
            failures.append(
                f"source {label!r} contains X content but has no platform_approval_ref"
            )

    if failures:
        raise RightsGateError("rights gate denied:\n- " + "\n- ".join(failures))
    return manifest
