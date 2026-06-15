# Model card: `<model-version>`

## Model details

- Base model and immutable revision:
- Adapter type:
- Dataset ID:
- Training config SHA-256:
- Code/container revision:
- Owner:

## Intended use

Internal generation of clearly labeled synthetic short-form writing for style research. The model
must not claim to be a real person or be represented as an official source.

## Prohibited use

- Impersonation or fabricated official quotations.
- Current-event deception, targeted political persuasion, fundraising, threats, or harassment.
- Automated posting or interaction on social networks.
- Removing the visible synthetic-content disclosure.

## Training

Record QLoRA parameters, hardware, seed, runtime, peak VRAM, package versions, and the full artifact
lineage from `run_manifest.json`.

## Evaluation

Attach the versioned automatic scorecard, human blind-review report, safety/red-team results,
memorization report, and load-test results. Record every release-gate threshold and outcome.

## Guardrails

Document input policy, output identity/overlap checks, disclosure contract, rate limiting, audit
logging, kill switch, canary rollout, and rollback owner.

## Limitations

The adapter can reproduce historical biases, factual errors, hostile rhetoric, and dataset-specific
phrases. A low training loss is not evidence of factual accuracy, safety, or authorship.

## Release decision

- Decision: draft / internal-candidate / approved / rejected / retired
- Approvers:
- Date:
- Conditions:
