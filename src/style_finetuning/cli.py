"""Command-line entry point for rights checks and dataset builds."""

from __future__ import annotations

import argparse
import json
import sys

from .errors import StylePipelineError
from .rights import assert_use_allowed


def _rights_command(args: argparse.Namespace) -> int:
    manifest = assert_use_allowed(args.manifest, args.use, args.scope)
    print(
        json.dumps(
            {
                "allowed": True,
                "manifest_version": manifest.manifest_version,
                "requested_use": args.use,
                "scope": args.scope,
            },
            indent=2,
        )
    )
    return 0


def _build_command(args: argparse.Namespace) -> int:
    from .data_prep.pipeline import build_dataset

    result = build_dataset(
        input_path=args.input,
        output_dir=args.output,
        config_path=args.config,
        rights_manifest_path=args.rights_manifest,
        scope=args.scope,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _publish_s3_command(args: argparse.Namespace) -> int:
    from .storage import publish_directory_to_s3

    result = publish_directory_to_s3(
        local_directory=args.local_directory,
        destination=args.destination,
        rights_manifest_path=args.rights_manifest,
        scope=args.scope,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="style-pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    rights_parser = subparsers.add_parser("rights", help="Validate a requested data use")
    rights_parser.add_argument("--manifest", required=True)
    rights_parser.add_argument("--use", required=True)
    rights_parser.add_argument("--scope", default="internal_research")
    rights_parser.set_defaults(handler=_rights_command)

    build_parser = subparsers.add_parser("build", help="Build raw/normalized/curated data")
    build_parser.add_argument("--input", required=True)
    build_parser.add_argument("--output", required=True)
    build_parser.add_argument("--config", default="configs/data/default.toml")
    build_parser.add_argument("--rights-manifest", required=True)
    build_parser.add_argument("--scope", default="internal_research")
    build_parser.set_defaults(handler=_build_command)

    publish_parser = subparsers.add_parser(
        "publish-s3", help="Publish a completed dataset build to an empty private S3 prefix"
    )
    publish_parser.add_argument("--local-directory", required=True)
    publish_parser.add_argument("--destination", required=True)
    publish_parser.add_argument("--rights-manifest", required=True)
    publish_parser.add_argument("--scope", default="internal_research")
    publish_parser.set_defaults(handler=_publish_s3_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = create_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except StylePipelineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
