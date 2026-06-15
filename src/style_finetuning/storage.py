"""Private S3 publication for completed dataset build directories."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

from .data_prep.io import file_sha256
from .errors import DataValidationError, OptionalDependencyError
from .rights import assert_use_allowed


def parse_s3_uri(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    bucket = parsed.netloc.strip()
    prefix = parsed.path.strip("/")
    if parsed.scheme != "s3" or not bucket or not prefix:
        raise DataValidationError("destination must be s3://<bucket>/<non-empty-prefix>")
    if any(part in {".", ".."} for part in PurePosixPath(prefix).parts):
        raise DataValidationError("S3 prefix cannot contain . or .. path segments")
    return bucket, prefix


def publish_directory_to_s3(
    *,
    local_directory: str | Path,
    destination: str,
    rights_manifest_path: str | Path,
    scope: str,
    client: Any | None = None,
) -> dict[str, Any]:
    """Upload a completed build to an empty private prefix, publishing manifest last."""

    rights = assert_use_allowed(rights_manifest_path, "dataset_build", scope)
    local_path = Path(local_directory)
    manifest_path = local_path / "manifest.json"
    if not local_path.is_dir() or not manifest_path.is_file():
        raise DataValidationError("local directory must contain a completed manifest.json")
    with manifest_path.open("r", encoding="utf-8") as handle:
        dataset_manifest = json.load(handle)
    if dataset_manifest.get("rights_manifest_version") != rights.manifest_version:
        raise DataValidationError("dataset rights version does not match the current manifest")
    if dataset_manifest.get("rights_manifest_sha256") != file_sha256(rights_manifest_path):
        raise DataValidationError("dataset rights hash does not match the current manifest")
    bucket, prefix = parse_s3_uri(destination)
    if client is None:
        if importlib.util.find_spec("boto3") is None:
            raise OptionalDependencyError("boto3 is required; install the data extra")
        import boto3

        client = boto3.client("s3")
    existing = client.list_objects_v2(Bucket=bucket, Prefix=prefix.rstrip("/") + "/", MaxKeys=1)
    if existing.get("KeyCount", 0) or existing.get("Contents"):
        raise DataValidationError(f"refusing to overwrite non-empty S3 prefix: {destination}")

    files = sorted(path for path in local_path.rglob("*") if path.is_file())
    ordered = [path for path in files if path.name != "manifest.json"] + [manifest_path]
    uploaded: list[str] = []
    for path in ordered:
        relative = path.relative_to(local_path).as_posix()
        key = f"{prefix.rstrip('/')}/{relative}"
        client.upload_file(
            str(path),
            bucket,
            key,
            ExtraArgs={"ServerSideEncryption": "AES256"},
        )
        uploaded.append(key)
    return {
        "destination": f"s3://{bucket}/{prefix}",
        "uploaded_files": len(uploaded),
        "manifest_key": uploaded[-1],
        "manifest_sha256": file_sha256(manifest_path),
    }
