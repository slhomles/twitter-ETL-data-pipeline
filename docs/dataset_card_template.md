# Dataset card: `<dataset-id>`

## Status

- Dataset version:
- Dataset manifest SHA-256:
- Rights manifest version:
- Approved scope:
- Owner:
- Last review:

## Intended use

Describe the approved internal/research use. This card does not grant rights beyond the attached
rights manifest.

## Sources and provenance

List source IDs and evidence references from the rights manifest. Do not paste confidential legal
documents or hydrated source text into this public-facing card.

## Schema and transformations

- Raw layer is a lossless envelope and remains immutable.
- Normalized layer preserves `text_raw` and derives `text_train`.
- Curated layer filters, labels, deduplicates, groups, and splits records.

Record the exact data config SHA-256 and any approved deviations here.

## Split strategy

Record counts for train, validation, test, and challenge sets. Confirm that conversation and
near-duplicate clusters do not cross splits.

## Quality review

- Label sample size:
- Label error rate:
- Reviewer:
- Review timestamp:
- Known failure modes:

## Biases and limitations

Document temporal, topical, language, archive-completeness, deletion, and selection biases. The
corpus represents historical writing samples and must not be treated as a current factual source.

## Distribution

State whether raw data, curated examples, adapters, or only aggregate metrics may be distributed.
Default: private and not redistributable until explicitly approved.
