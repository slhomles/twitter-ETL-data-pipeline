"""QLoRA SFT entrypoint with fail-closed data rights and quality gates."""

from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import os
import sys
from pathlib import Path
from typing import Any

from ..config import load_toml, object_sha256
from ..data_prep.io import write_json
from ..errors import DataValidationError, OptionalDependencyError, StylePipelineError
from .gates import validate_training_gates

TRAIN_DEPENDENCIES = ("torch", "transformers", "datasets", "trl", "peft", "bitsandbytes")


def _require_training_dependencies() -> None:
    missing = [name for name in TRAIN_DEPENDENCIES if importlib.util.find_spec(name) is None]
    if missing:
        raise OptionalDependencyError(
            "missing training dependencies: "
            + ", ".join(missing)
            + ". Install the train extra in a CUDA-capable environment."
        )


def _checked_config(path: str | Path) -> dict[str, Any]:
    config = load_toml(path)
    for section in ("model", "quantization", "lora", "training", "tracking"):
        if not isinstance(config.get(section), dict):
            raise DataValidationError(f"training config section [{section}] is required")
    revision = str(config["model"].get("revision", "")).strip()
    if not revision:
        raise DataValidationError("model.revision is required")
    if revision in {"main", "master"} and not config["model"].get(
        "allow_mutable_revision_for_pilot", False
    ):
        raise DataValidationError("production runs must pin model.revision to a commit")
    return config


def _sft_kwargs(sft_config_class: type, training: dict[str, Any], output: Path) -> dict[str, Any]:
    available = inspect.signature(sft_config_class).parameters
    kwargs: dict[str, Any] = {
        "output_dir": str(output),
        "num_train_epochs": float(training["num_train_epochs"]),
        "learning_rate": float(training["learning_rate"]),
        "per_device_train_batch_size": int(training["per_device_train_batch_size"]),
        "per_device_eval_batch_size": int(training["per_device_eval_batch_size"]),
        "gradient_accumulation_steps": int(training["gradient_accumulation_steps"]),
        "warmup_ratio": float(training["warmup_ratio"]),
        "weight_decay": float(training["weight_decay"]),
        "max_grad_norm": float(training["max_grad_norm"]),
        "lr_scheduler_type": str(training["lr_scheduler_type"]),
        "logging_steps": int(training["logging_steps"]),
        "eval_steps": int(training["eval_steps"]),
        "save_steps": int(training["save_steps"]),
        "save_total_limit": int(training["save_total_limit"]),
        "gradient_checkpointing": bool(training["gradient_checkpointing"]),
        "packing": bool(training["packing"]),
        "seed": int(training["seed"]),
        "eval_strategy": "steps",
        "save_strategy": "steps",
        "load_best_model_at_end": True,
        "metric_for_best_model": "eval_loss",
        "greater_is_better": False,
    }
    length_name = "max_length" if "max_length" in available else "max_seq_length"
    kwargs[length_name] = int(training["max_length"])
    if "completion_only_loss" in available:
        kwargs["completion_only_loss"] = True
    return {key: value for key, value in kwargs.items() if key in available}


def run_training(args: argparse.Namespace) -> dict[str, Any]:
    output_path = Path(args.output)
    if output_path.exists():
        raise DataValidationError(f"output path must not already exist: {output_path}")
    dataset_manifest, rights, quality = validate_training_gates(
        dataset_dir=args.dataset_dir,
        rights_manifest_path=args.rights_manifest,
        quality_approval_path=args.quality_approval,
        scope=args.scope,
    )
    config = _checked_config(args.config)
    _require_training_dependencies()

    import torch
    from datasets import load_dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from trl import SFTConfig, SFTTrainer

    model_config = config["model"]
    quantization = config["quantization"]
    lora = config["lora"]
    training = config["training"]
    tracking = config["tracking"]
    dtype_name = str(quantization["compute_dtype"])
    compute_dtype = getattr(torch, dtype_name, None)
    if compute_dtype is None:
        raise DataValidationError(f"unknown torch dtype: {dtype_name}")
    if not torch.cuda.is_available():
        raise DataValidationError("CUDA is required for this QLoRA configuration")
    use_bf16 = dtype_name == "bfloat16" and torch.cuda.is_bf16_supported()
    if dtype_name == "bfloat16" and not use_bf16:
        compute_dtype = torch.float16

    quantization_config = BitsAndBytesConfig(
        load_in_4bit=bool(quantization["load_in_4bit"]),
        bnb_4bit_quant_type=str(quantization["quant_type"]),
        bnb_4bit_use_double_quant=bool(quantization["use_double_quant"]),
        bnb_4bit_compute_dtype=compute_dtype,
    )
    model = AutoModelForCausalLM.from_pretrained(
        model_config["name"],
        revision=model_config["revision"],
        trust_remote_code=bool(model_config["trust_remote_code"]),
        quantization_config=quantization_config,
        device_map="auto",
    )
    model.config.use_cache = False
    tokenizer = AutoTokenizer.from_pretrained(
        model_config["name"],
        revision=model_config["revision"],
        trust_remote_code=bool(model_config["trust_remote_code"]),
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    data_files = {
        "train": str(Path(args.dataset_dir) / "curated" / "train.jsonl"),
        "validation": str(Path(args.dataset_dir) / "curated" / "validation.jsonl"),
    }
    dataset = load_dataset("json", data_files=data_files)
    lora_config = LoraConfig(
        r=int(lora["r"]),
        lora_alpha=int(lora["alpha"]),
        lora_dropout=float(lora["dropout"]),
        bias=str(lora["bias"]),
        target_modules=list(lora["target_modules"]),
        task_type="CAUSAL_LM",
    )
    training_kwargs = _sft_kwargs(SFTConfig, training, output_path)
    training_kwargs["bf16"] = use_bf16
    training_kwargs["fp16"] = not use_bf16
    training_kwargs["report_to"] = ["mlflow"] if tracking["report_to_mlflow"] else []
    sft_config = SFTConfig(**training_kwargs)

    trainer_kwargs: dict[str, Any] = {
        "model": model,
        "args": sft_config,
        "train_dataset": dataset["train"],
        "eval_dataset": dataset["validation"],
        "peft_config": lora_config,
    }
    trainer_parameters = inspect.signature(SFTTrainer).parameters
    if "processing_class" in trainer_parameters:
        trainer_kwargs["processing_class"] = tokenizer
    elif "tokenizer" in trainer_parameters:
        trainer_kwargs["tokenizer"] = tokenizer
    if tracking["report_to_mlflow"]:
        os.environ.setdefault("MLFLOW_EXPERIMENT_NAME", str(tracking["experiment_name"]))
    trainer = SFTTrainer(**trainer_kwargs)
    train_result = trainer.train()
    trainer.save_model(str(output_path / "adapter"))
    tokenizer.save_pretrained(str(output_path / "adapter"))

    run_manifest = {
        "dataset_id": dataset_manifest["dataset_id"],
        "rights_manifest_version": rights.manifest_version,
        "quality_reviewed_by": quality["reviewed_by"],
        "base_model": model_config["name"],
        "base_model_revision": model_config["revision"],
        "training_config_sha256": object_sha256(config),
        "seed": training["seed"],
        "metrics": dict(train_result.metrics),
    }
    write_json(output_path / "run_manifest.json", run_manifest)
    return run_manifest


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="style-train")
    parser.add_argument("--dataset-dir", required=True)
    parser.add_argument("--rights-manifest", required=True)
    parser.add_argument("--quality-approval", required=True)
    parser.add_argument("--config", default="configs/training/qwen2_5_7b_qlora.toml")
    parser.add_argument("--output", required=True)
    parser.add_argument("--scope", default="internal_research")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    try:
        manifest = run_training(args)
    except StylePipelineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
