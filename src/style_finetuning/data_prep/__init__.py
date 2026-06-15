"""Dataset ingestion, normalization, deduplication, and split building."""

from .pipeline import build_dataset

__all__ = ["build_dataset"]
