"""Leakage-resistant grouping and temporal dataset splitting."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


class _UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, value: int) -> int:
        if self.parent[value] != value:
            self.parent[value] = self.find(self.parent[value])
        return self.parent[value]

    def union(self, left: int, right: int) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            self.parent[max(left_root, right_root)] = min(left_root, right_root)


def _group_records(records: list[dict[str, Any]]) -> list[list[int]]:
    union_find = _UnionFind(len(records))
    seen_conversation: dict[str, int] = {}
    seen_cluster: dict[str, int] = {}
    for index, record in enumerate(records):
        conversation = str(record.get("conversation_id", ""))
        cluster = str(record.get("near_dup_cluster_id", ""))
        if conversation:
            if conversation in seen_conversation:
                union_find.union(index, seen_conversation[conversation])
            else:
                seen_conversation[conversation] = index
        if cluster:
            if cluster in seen_cluster:
                union_find.union(index, seen_cluster[cluster])
            else:
                seen_cluster[cluster] = index
    grouped: dict[int, list[int]] = defaultdict(list)
    for index in range(len(records)):
        grouped[union_find.find(index)].append(index)
    return sorted(
        grouped.values(),
        key=lambda indexes: min(records[index]["created_at_utc"] for index in indexes),
    )


def assign_grouped_temporal_splits(
    records: list[dict[str, Any]],
    *,
    train_ratio: float,
    validation_ratio: float,
    test_ratio: float,
) -> list[dict[str, Any]]:
    if not records:
        return []
    if abs(train_ratio + validation_ratio + test_ratio - 1.0) > 1e-9:
        raise ValueError("split ratios must sum to 1.0")
    if min(train_ratio, validation_ratio, test_ratio) < 0:
        raise ValueError("split ratios cannot be negative")

    groups = _group_records(records)
    assignments: list[str] = []
    cumulative = 0
    total = len(records)
    for indexes in groups:
        midpoint = (cumulative + len(indexes) / 2) / total
        if midpoint < train_ratio:
            split = "train"
        elif midpoint < train_ratio + validation_ratio:
            split = "validation"
        else:
            split = "test"
        assignments.append(split)
        cumulative += len(indexes)

    if len(groups) >= 3:
        assignments[0] = "train"
        assignments[-1] = "test"
        if "validation" not in assignments:
            candidate = min(
                range(1, len(groups) - 1),
                key=lambda index: abs(index / (len(groups) - 1) - train_ratio),
            )
            assignments[candidate] = "validation"

    result = [dict(record) for record in records]
    for indexes, split in zip(groups, assignments, strict=True):
        for index in indexes:
            result[index]["split"] = split
    return result


def assert_no_group_leakage(records: list[dict[str, Any]]) -> None:
    for field in ("conversation_id", "near_dup_cluster_id"):
        observed: dict[str, str] = {}
        for record in records:
            key = str(record.get(field, ""))
            split = str(record.get("split", ""))
            if not key:
                continue
            if key in observed and observed[key] != split:
                raise ValueError(
                    f"data leakage: {field}={key!r} is in {observed[key]!r} and {split!r}"
                )
            observed[key] = split
