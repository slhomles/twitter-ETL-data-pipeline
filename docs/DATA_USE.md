# Data-use status

## Current decision

**Real-corpus status: BLOCKED pending documented approval.**

Only the self-authored fictional records under `tests/fixtures/` are currently approved for the
automated `test` scope. That fixture approval is not transferable to any external archive, X export,
API response, scraped content, commercial deployment, or public model release.

## Required evidence for a real corpus

Create an untracked `data_rights_manifest.json` from `configs/rights_manifest.example.json` and have
an authorized reviewer complete:

- Source inventory and stable source IDs.
- Acquisition method and applicable terms.
- Evidence that ML training is permitted.
- Platform approval reference when the source contains X content obtained from X API/export/scrape.
- Allowed scope: internal research, internal serving, distribution, or commercial use.
- Redistribution decision for raw, curated, adapter, and merged-model artifacts.
- Reviewer identity and review timestamp.

The CLI validates structure and consistency but cannot determine whether a legal assertion is true.
Do not set `status=approved` or `ml_training_allowed=true` without authority and evidence.

## Quality approval

After building a dataset, copy `configs/quality_approval.example.json`, set its exact `dataset_id`,
and record human label QA. Training requires:

- `status=approved` and `approved_for_training=true`.
- A named reviewer and timestamp.
- Label error rate no greater than 5%.
- Sample size at least `min(corpus size, max(500, 10% of corpus size))`.
- Zero conversation or near-duplicate cluster leakage in the dataset manifest.

## Distribution default

All source, normalized, curated, checkpoint, adapter, and evaluation-example artifacts are private
by default. Only aggregate metrics and documentation may be committed unless a separate distribution
approval explicitly permits more.

## Safety boundary

The approved product behavior is labeled synthetic style research. The system must not be used for
impersonation, fabricated official statements, current-event deception, targeted political
persuasion, fundraising, harassment, or automated social-network posting.
