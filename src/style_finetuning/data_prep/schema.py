"""Canonical post schema and lossless normalization helpers."""

from __future__ import annotations

import html
import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

from ..errors import DataValidationError

URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
MENTION_RE = re.compile(r"(?<!\w)@[A-Za-z0-9_]+")
WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")
LINK_ONLY_RE = re.compile(r"^(?:https?://\S+\s*)+$", re.IGNORECASE)

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "post_id": ("post_id", "tweet_id", "id_str", "id"),
    "author_id": ("author_id", "user_id", "username", "user", "screen_name"),
    "created_at": ("created_at_utc", "created_at", "timestamp", "date"),
    "text": ("text_raw", "full_text", "text", "content"),
    "lang": ("lang", "language"),
    "conversation_id": ("conversation_id", "thread_id"),
    "in_reply_to_post_id": ("in_reply_to_post_id", "in_reply_to_status_id_str"),
    "quoted_post_id": ("quoted_post_id", "quoted_status_id_str"),
}


def _first(mapping: dict[str, Any], aliases: tuple[str, ...], default: Any = None) -> Any:
    for alias in aliases:
        value = mapping.get(alias)
        if value is not None and value != "":
            return value
    return default


def parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value or "").strip()
        if not raw:
            raise DataValidationError("created_at is required")
        parsed = None
        candidate = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            for pattern in (
                "%a %b %d %H:%M:%S %z %Y",
                "%Y-%m-%d %H:%M:%S%z",
                "%Y-%m-%d %H:%M:%S",
            ):
                try:
                    parsed = datetime.strptime(raw, pattern)
                    break
                except ValueError:
                    continue
        if parsed is None:
            raise DataValidationError(f"unsupported created_at value: {raw!r}")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_text(text: str, *, replace_urls: bool, replace_mentions: bool) -> str:
    value = unicodedata.normalize("NFC", html.unescape(text))
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = "\n".join(WHITESPACE_RE.sub(" ", line).strip() for line in value.split("\n"))
    value = re.sub(r"\n{3,}", "\n\n", value).strip()
    if replace_urls:
        value = URL_RE.sub("<URL>", value)
    if replace_mentions:
        value = MENTION_RE.sub("<USER>", value)
    return value


def _reference_types(mapping: dict[str, Any], text: str) -> list[str]:
    raw = mapping.get("reference_types", mapping.get("referenced_tweets", []))
    values: list[str] = []
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
            raw = decoded if isinstance(decoded, list) else [raw]
        except json.JSONDecodeError:
            raw = [item.strip() for item in raw.split(",")]
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                item = item.get("type", "")
            label = str(item).strip().lower()
            if label:
                values.append(label)
    if text.lstrip().startswith("RT @") and "retweeted" not in values:
        values.append("retweeted")
    if _first(mapping, FIELD_ALIASES["in_reply_to_post_id"]) and "replied_to" not in values:
        values.append("replied_to")
    if _first(mapping, FIELD_ALIASES["quoted_post_id"]) and "quoted" not in values:
        values.append("quoted")
    return sorted(set(values))


def normalize_post(
    mapping: dict[str, Any],
    *,
    source_ref: str,
    rights_manifest_version: str,
    replace_urls: bool,
    replace_mentions: bool,
) -> dict[str, Any]:
    post_id = str(_first(mapping, FIELD_ALIASES["post_id"], "")).strip()
    author_id = str(_first(mapping, FIELD_ALIASES["author_id"], "")).strip()
    text_raw = str(_first(mapping, FIELD_ALIASES["text"], ""))
    if not post_id:
        raise DataValidationError("post_id is required")
    if not author_id:
        raise DataValidationError(f"post {post_id}: author_id is required")
    if not text_raw.strip():
        raise DataValidationError(f"post {post_id}: text is required")
    created_at = parse_timestamp(_first(mapping, FIELD_ALIASES["created_at"]))
    conversation_id = str(
        _first(mapping, FIELD_ALIASES["conversation_id"], post_id)
    ).strip()
    text_train = normalize_text(
        text_raw, replace_urls=replace_urls, replace_mentions=replace_mentions
    )
    entities = mapping.get("entities", mapping.get("entities_json", {}))
    if isinstance(entities, str):
        try:
            entities = json.loads(entities)
        except json.JSONDecodeError:
            entities = {"unparsed": entities}
    if not isinstance(entities, dict):
        entities = {"value": entities}
    return {
        "post_id": post_id,
        "author_id": author_id,
        "created_at_utc": created_at.isoformat().replace("+00:00", "Z"),
        "text_raw": text_raw,
        "text_train": text_train,
        "lang": str(_first(mapping, FIELD_ALIASES["lang"], "und")).strip().lower(),
        "conversation_id": conversation_id or post_id,
        "in_reply_to_post_id": str(
            _first(mapping, FIELD_ALIASES["in_reply_to_post_id"], "")
        ).strip()
        or None,
        "quoted_post_id": str(
            _first(mapping, FIELD_ALIASES["quoted_post_id"], "")
        ).strip()
        or None,
        "reference_types": _reference_types(mapping, text_raw),
        "entities_json": entities,
        "source_ref": source_ref,
        "rights_manifest_version": rights_manifest_version,
        "quality_flags": [],
    }


def is_link_only(text: str) -> bool:
    return bool(LINK_ONLY_RE.fullmatch(text.strip()))
