# Implementation runbook

## 1. Local core setup

The core rights/data/evaluation code uses Python 3.11 standard-library modules. From the repository
root:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

For editable installation, use `python -m pip install -e .`. Optional groups are `data`, `train`,
`serve`, and `dev`.

## 2. Rights preflight

Copy `configs/rights_manifest.example.json` to the untracked file `data_rights_manifest.json`.
Complete and review it, then run:

```powershell
$env:PYTHONPATH = "src"
python -m style_finetuning.cli rights `
  --manifest data_rights_manifest.json `
  --use dataset_build `
  --scope internal_research
```

Exit code 2 means the requested use is denied. Do not bypass this check.

## 3. Build a versioned dataset

Input may be UTF-8 CSV, JSON, JSONL, or NDJSON. Required logical fields are post ID, author ID,
timestamp, and full text; common tweet/archive aliases are accepted.

```powershell
$env:PYTHONPATH = "src"
python -m style_finetuning.cli build `
  --input D:\approved-data\posts.jsonl `
  --output D:\approved-data\builds\dataset-v001 `
  --config configs/data/default.toml `
  --rights-manifest data_rights_manifest.json `
  --scope internal_research
```

The output path must not exist. The builder writes into a staging directory and publishes the final
directory only after all files and checksums are complete.

Review:

- `raw/source.jsonl`: lossless source envelope.
- `normalized/posts.jsonl`: canonical records preserving `text_raw`.
- `rejected/posts.jsonl`: stage and reason for every rejected record.
- `curated/{train,validation,test}.jsonl`: TRL prompt/completion data.
- `manifest.json`: dataset ID, rights/config/input lineage, counts, and artifact hashes.

To publish a completed build to a new private S3 prefix, install the `data` extra and run:

```powershell
python -m style_finetuning.cli publish-s3 `
  --local-directory D:\approved-data\builds\dataset-v001 `
  --destination s3://private-bucket/style-datasets/dataset-v001 `
  --rights-manifest data_rights_manifest.json `
  --scope internal_research
```

The publisher refuses a non-empty prefix, requests server-side encryption, and uploads
`manifest.json` last so consumers do not see a build as complete prematurely. Bucket versioning,
block-public-access, lifecycle, KMS policy, and least-privilege IAM remain infrastructure controls.

## 4. Human label QA

Sample by topic, intent, time bucket, length, and rejection reason. Complete a quality approval from
`configs/quality_approval.example.json`; its `dataset_id` must exactly match the manifest.

## 5. GPU smoke training

Use a CUDA-capable Linux host with a target of at least 24 GB GPU memory for the initial 7–8B QLoRA
configuration. Install the training extra in that isolated environment:

```bash
python -m pip install -e '.[train]'
```

Run a small approved dataset build first, then:

```bash
style-train \
  --dataset-dir /approved-data/builds/dataset-v001 \
  --rights-manifest /secure/data_rights_manifest.json \
  --quality-approval /secure/quality_approval.json \
  --config configs/training/qwen2_5_7b_qlora.toml \
  --output /approved-data/checkpoints/qwen-pilot-001 \
  --scope internal_research
```

For a production candidate, replace model revision `main` with an immutable Hugging Face commit and
set `allow_mutable_revision_for_pilot=false`.

## 6. Automatic evaluation

Generation output may use `generated_text`, `text`, `text_train`, `content`, or TRL `completion`.

```powershell
$env:PYTHONPATH = "src"
python -m style_finetuning.evaluation.cli `
  --generated D:\approved-data\generations\candidate.jsonl `
  --reference D:\approved-data\builds\dataset-v001\curated\test.jsonl `
  --training D:\approved-data\builds\dataset-v001\curated\train.jsonl `
  --config configs/evaluation/default.toml `
  --output D:\approved-data\evaluations\candidate-report.json
```

Automatic passing never removes the requirement for blinded human review and red-team approval.

## 7. Guarded serving

Serve the approved adapter with a private OpenAI-compatible vLLM endpoint, then configure:

```powershell
$env:STYLE_VLLM_URL = "http://127.0.0.1:8001"
$env:STYLE_MODEL_VERSION = "style-microblog-qwen-0.1.0"
$env:STYLE_VLLM_API_KEY = "<private-vllm-key>"
$env:STYLE_API_KEY = "<client-api-key>"
$env:STYLE_TRAINING_JSONL = "D:\approved-data\builds\dataset-v001\curated\train.jsonl"
$env:PYTHONPATH = "src"
python -m style_finetuning.serving.app
```

The public-facing process defaults to `127.0.0.1`. Put TLS, network policy, rate limiting, and a
secret manager in front of any non-local deployment. `STYLE_ALLOW_STUB=1` is test-only.

## 8. Rollback and incident handling

- Stop the API or remove its route using the deployment kill switch.
- Roll the model alias back to the previous immutable adapter version.
- Preserve request IDs, policy codes, model version, and aggregate metrics; avoid logging raw prompts.
- Quarantine the failing artifact and its generation report.
- Re-run rights, quality, memorization, safety, and load gates before promotion.
