"""Exact deduplication and deterministic near-duplicate clustering."""

from __future__ import annotations

import hashlib
import itertools
import re
from collections import defaultdict
from typing import Any

TOKEN_RE = re.compile(r"[\w']+|[!?]+", re.UNICODE)


class _UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, value: int) -> int:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[max(left_root, right_root)] = min(left_root, right_root)


def normalized_fingerprint(text: str) -> str:
    return " ".join(TOKEN_RE.findall(text.casefold()))


def remove_exact_duplicates(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: dict[str, str] = {}
    for record in records:
        fingerprint = normalized_fingerprint(str(record["text_train"]))
        if fingerprint in seen:
            duplicate = dict(record)
            duplicate["quality_flags"] = [
                *duplicate.get("quality_flags", []),
                f"exact_duplicate_of:{seen[fingerprint]}",
            ]
            rejected.append(duplicate)
            continue
        seen[fingerprint] = str(record["post_id"])
        kept.append(dict(record))
    return kept, rejected


def _shingles(text: str, ngram_size: int) -> frozenset[str]:
    tokens = TOKEN_RE.findall(text.casefold())
    if not tokens:
        return frozenset({"<EMPTY>"})
    if len(tokens) < ngram_size:
        return frozenset({" ".join(tokens)})
    return frozenset(
        " ".join(tokens[index : index + ngram_size])
        for index in range(len(tokens) - ngram_size + 1)
    )


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 1.0


def _minhash_signature(shingles: frozenset[str], permutations: int) -> tuple[int, ...]:
    signature: list[int] = []
    for permutation in range(permutations):
        minimum = min(
            int.from_bytes(
                hashlib.blake2b(
                    f"{permutation}\0{shingle}".encode("utf-8"), digest_size=8
                ).digest(),
                "big",
            )
            for shingle in shingles
        )
        signature.append(minimum)
    return tuple(signature)


def _candidate_pairs(
    shingle_sets: list[frozenset[str]],
    *,
    permutations: int,
    bands: int,
    exhaustive_limit: int,
) -> set[tuple[int, int]]:
    if len(shingle_sets) <= exhaustive_limit:
        return set(itertools.combinations(range(len(shingle_sets)), 2))
    if permutations <= 0 or bands <= 0 or permutations % bands:
        raise ValueError("minhash_permutations must be positive and divisible by minhash_bands")
    rows_per_band = permutations // bands
    buckets: dict[tuple[int, tuple[int, ...]], list[int]] = defaultdict(list)
    for index, shingles in enumerate(shingle_sets):
        signature = _minhash_signature(shingles, permutations)
        for band in range(bands):
            start = band * rows_per_band
            key = (band, signature[start : start + rows_per_band])
            buckets[key].append(index)
    candidates: set[tuple[int, int]] = set()
    for indexes in buckets.values():
        if len(indexes) > 1:
            candidates.update(itertools.combinations(sorted(indexes), 2))
    return candidates


def _evenly_spaced_indexes(size: int, limit: int) -> set[int]:
    if size <= limit:
        return set(range(size))
    if limit <= 1:
        return {0}
    return {round(index * (size - 1) / (limit - 1)) for index in range(limit)}


def cluster_near_duplicates(
    records: list[dict[str, Any]],
    *,
    ngram_size: int,
    similarity_threshold: float,
    permutations: int,
    bands: int,
    exhaustive_limit: int,
    max_per_cluster: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not 0 <= similarity_threshold <= 1:
        raise ValueError("similarity_threshold must be in [0, 1]")
    if max_per_cluster < 1:
        raise ValueError("max_per_cluster must be at least 1")
    shingle_sets = [
        _shingles(str(record["text_train"]), ngram_size) for record in records
    ]
    union_find = _UnionFind(len(records))
    for left, right in _candidate_pairs(
        shingle_sets,
        permutations=permutations,
        bands=bands,
        exhaustive_limit=exhaustive_limit,
    ):
        if _jaccard(shingle_sets[left], shingle_sets[right]) >= similarity_threshold:
            union_find.union(left, right)

    grouped: dict[int, list[int]] = defaultdict(list)
    for index in range(len(records)):
        grouped[union_find.find(index)].append(index)

    kept: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for indexes in grouped.values():
        ordered = sorted(indexes, key=lambda item: (records[item]["created_at_utc"], item))
        cluster_material = "\0".join(
            sorted(str(records[index]["post_id"]) for index in indexes)
        )
        cluster_id = hashlib.sha256(cluster_material.encode("utf-8")).hexdigest()[:16]
        selected_positions = _evenly_spaced_indexes(len(ordered), max_per_cluster)
        for position, index in enumerate(ordered):
            record = dict(records[index])
            record["near_dup_cluster_id"] = cluster_id
            if position in selected_positions:
                kept.append(record)
            else:
                record["quality_flags"] = [
                    *record.get("quality_flags", []),
                    f"near_duplicate_cluster_cap:{cluster_id}",
                ]
                rejected.append(record)
    kept.sort(key=lambda item: (item["created_at_utc"], item["post_id"]))
    return kept, rejected
