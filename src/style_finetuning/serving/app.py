"""FastAPI application with authentication, disclosure, and policy enforcement."""

import hashlib
import hmac
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Literal

from ..errors import OptionalDependencyError, StylePipelineError
from .backend import StubBackend, VLLMBackend
from .policy import GuardedGenerator, SYNTHETIC_DISCLOSURE

LOGGER = logging.getLogger("style_finetuning.serving")


def _serve_imports():
    try:
        from fastapi import FastAPI, Header, HTTPException
        from pydantic import BaseModel, Field
    except ImportError as exc:
        raise OptionalDependencyError(
            "serving dependencies are missing; install the serve extra"
        ) from exc
    return FastAPI, Header, HTTPException, BaseModel, Field


def _load_training_texts(path: str | None) -> list[str]:
    if not path:
        return []
    source = Path(path)
    if not source.is_file():
        raise StylePipelineError(f"training overlap corpus does not exist: {source}")
    texts: list[str] = []
    with source.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                texts.append(str(record["completion"][-1]["content"]))
            except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
                raise StylePipelineError(
                    f"invalid SFT overlap record on line {line_number}"
                ) from exc
    return texts


def _default_backend():
    if os.getenv("STYLE_ALLOW_STUB") == "1":
        return StubBackend()
    base_url = os.getenv("STYLE_VLLM_URL", "").strip()
    model = os.getenv("STYLE_MODEL_VERSION", "").strip()
    if not base_url or not model:
        raise StylePipelineError(
            "STYLE_VLLM_URL and STYLE_MODEL_VERSION are required; "
            "set STYLE_ALLOW_STUB=1 only for local tests"
        )
    return VLLMBackend(
        base_url=base_url,
        model=model,
        api_key=os.getenv("STYLE_VLLM_API_KEY", ""),
    )


def create_app(*, backend=None, api_key: str | None = None, training_texts=None):
    FastAPI, Header, HTTPException, BaseModel, Field = _serve_imports()

    class GenerateRequest(BaseModel):
        topic: str = Field(min_length=2, max_length=200)
        intent: Literal[
            "announce_or_update",
            "praise",
            "criticize_or_rebut",
            "thank_or_congratulate",
            "question_or_challenge",
            "comment",
        ] = "comment"
        length: Literal["very_short", "short", "medium"] = "short"
        historical_context: str = Field(default="historical/general", max_length=300)

    class GenerateResponse(BaseModel):
        text: str
        synthetic: bool
        disclosure: str
        model_version: str
        request_id: str

    selected_backend = backend or _default_backend()
    selected_api_key = api_key if api_key is not None else os.getenv("STYLE_API_KEY", "")
    if not selected_api_key:
        raise StylePipelineError("STYLE_API_KEY is required for the serving endpoint")
    overlap_texts = (
        list(training_texts)
        if training_texts is not None
        else _load_training_texts(os.getenv("STYLE_TRAINING_JSONL"))
    )
    generator = GuardedGenerator(selected_backend, training_texts=overlap_texts)
    app = FastAPI(
        title="Guarded Synthetic Style API",
        version="0.1.0",
        description=SYNTHETIC_DISCLOSURE,
    )

    def authorize(x_api_key: str | None) -> None:
        if not x_api_key or not hmac.compare_digest(
            hashlib.sha256(x_api_key.encode()).digest(),
            hashlib.sha256(selected_api_key.encode()).digest(),
        ):
            raise HTTPException(status_code=401, detail={"code": "unauthorized"})

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "model_version": selected_backend.model_version,
            "disclosure_enforced": True,
            "training_overlap_filter": bool(overlap_texts),
        }

    @app.post("/v1/generate", response_model=GenerateResponse)
    def generate(request: GenerateRequest, x_api_key: str | None = Header(default=None)):
        authorize(x_api_key)
        request_id = str(uuid.uuid4())
        decision, result = generator.generate(
            topic=request.topic,
            intent=request.intent,
            length=request.length,
            historical_context=request.historical_context,
        )
        LOGGER.info(
            "request_id=%s decision=%s topic_length=%s intent=%s model=%s",
            request_id,
            decision.code,
            len(request.topic),
            request.intent,
            selected_backend.model_version,
        )
        if not decision.allowed or result is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": decision.code,
                    "message": decision.reason,
                    "request_id": request_id,
                },
            )
        return GenerateResponse(
            text=result.text,
            synthetic=result.synthetic,
            disclosure=result.disclosure,
            model_version=result.model_version,
            request_id=request_id,
        )

    return app


def main() -> int:
    try:
        import uvicorn

        app = create_app()
    except (ImportError, StylePipelineError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    uvicorn.run(
        app,
        host=os.getenv("STYLE_HOST", "127.0.0.1"),
        port=int(os.getenv("STYLE_PORT", "8000")),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
