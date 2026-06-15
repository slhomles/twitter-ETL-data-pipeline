"""Airflow DAG for a manual, rights-gated dataset build.

The DAG has no schedule by design. Supply paths through environment variables and use a unique
STYLE_DATASET_OUTPUT_ROOT for every approved dataset family.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from airflow import DAG
from airflow.operators.python import PythonOperator


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"required environment variable is missing: {name}")
    return value


def build_approved_dataset(**context) -> dict:
    from style_finetuning.data_prep.pipeline import build_dataset

    output_root = _required_environment("STYLE_DATASET_OUTPUT_ROOT")
    output_dir = os.path.join(output_root, str(context["ts_nodash"]))
    return build_dataset(
        input_path=_required_environment("STYLE_DATASET_INPUT"),
        output_dir=output_dir,
        config_path=os.environ.get("STYLE_DATA_CONFIG", "configs/data/default.toml"),
        rights_manifest_path=_required_environment("STYLE_RIGHTS_MANIFEST"),
        scope=os.environ.get("STYLE_APPROVED_SCOPE", "internal_research"),
    )


with DAG(
    dag_id="build_approved_style_dataset",
    description="Manual rights-gated raw/normalized/curated dataset build",
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["style-finetuning", "rights-gated"],
) as dag:
    build = PythonOperator(
        task_id="build_dataset",
        python_callable=build_approved_dataset,
    )

    build
