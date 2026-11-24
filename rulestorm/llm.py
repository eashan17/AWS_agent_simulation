"""Model adapter: one `decide(prompt, schema)` over Bedrock Converse, plus a scripted fake.

Contract (docs/ARCHITECTURE.md, Model adapter contract):
- asks for JSON in the prompt (no tool use) and validates the reply with Pydantic;
- on an invalid reply, retries once with the validation error included;
- any exception, or a second invalid reply, gives a "no action" outcome with the error text.
It never raises for model or AWS errors, so one bad call cannot crash a run.
"""

import json
import re
import time
from dataclasses import dataclass, field
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from rulestorm import config

T = TypeVar("T", bound=BaseModel)

MAX_ERROR_CHARS = 500


@dataclass
class Reply:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


class Model(Protocol):
    model_id: str

    def complete(self, prompt: str, max_tokens: int) -> Reply: ...


@dataclass
class Outcome(Generic[T]):
    """What `decide` returns. `value` is None means "no action"; `error` says why."""

    value: T | None
    error: str | None = None
    attempts: int = 0
    raw_replies: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0

    @property
    def no_action(self) -> bool:
        return self.value is None


def _short(text: str) -> str:
    return text if len(text) <= MAX_ERROR_CHARS else text[:MAX_ERROR_CHARS] + "…"


def _extract_json(text: str) -> str:
    """Models often wrap JSON in prose or ``` fences; take the outermost object."""
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start != -1 and end > start else text


def _prompt_with_schema(prompt: str, schema: type[BaseModel]) -> str:
    return (
        f"{prompt}\n\nReply with one JSON object only, no other text. "
        f"It must match this JSON schema:\n{json.dumps(schema.model_json_schema())}"
    )


def decide(
    prompt: str, schema: type[T], model: Model | None = None, max_tokens: int = 800
) -> Outcome[T]:
    model = model or get_model()
    outcome: Outcome[T] = Outcome(value=None)
    started = time.monotonic()
    current = _prompt_with_schema(prompt, schema)
    try:
        for attempt in (1, 2):
            outcome.attempts = attempt
            reply = model.complete(current, max_tokens)
            outcome.raw_replies.append(reply.text)
            outcome.input_tokens += reply.input_tokens
            outcome.output_tokens += reply.output_tokens
            try:
                outcome.value = schema.model_validate_json(_extract_json(reply.text))
                outcome.error = None
                break
            except ValidationError as exc:
                outcome.error = f"invalid reply: {_short(str(exc))}"
                current = (
                    f"{_prompt_with_schema(prompt, schema)}\n\n"
                    f"Your previous reply was invalid:\n{_short(str(exc))}\n"
                    "Reply again with corrected JSON only."
                )
    except Exception as exc:  # throttling, timeout, access error: recorded, never raised
        outcome.value = None
        outcome.error = f"{type(exc).__name__}: {_short(str(exc))}"
    outcome.seconds = round(time.monotonic() - started, 2)
    return outcome


class BedrockModel:
    """Bedrock Converse in-Region. `max_attempts=1` turns boto retries off (blueprint calls)."""

    def __init__(self, model_id: str | None = None, max_attempts: int = 5) -> None:
        import boto3
        from botocore.config import Config

        self.model_id = model_id or config.model_id()
        self.session = boto3.Session(region_name=config.region())
        self.client = self.session.client(
            "bedrock-runtime",
            config=Config(
                connect_timeout=5,
                read_timeout=config.read_timeout_s(),
                retries={"mode": "adaptive", "max_attempts": max_attempts},
            ),
        )

    def complete(self, prompt: str, max_tokens: int) -> Reply:
        response = self.client.converse(
            modelId=self.model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": max_tokens, "temperature": 0.7},
        )
        text = "".join(
            part.get("text", "") for part in response["output"]["message"]["content"]
        )
        usage = response.get("usage", {})
        return Reply(text, usage.get("inputTokens", 0), usage.get("outputTokens", 0))


class FakeModel:
    """Scripted replies for automated tests. Each item is a reply text or an exception to raise."""

    model_id = "fake"

    def __init__(self, script: list[str | Exception] | None = None) -> None:
        self.script = list(script or [])
        self.prompts: list[str] = []

    def complete(self, prompt: str, max_tokens: int) -> Reply:
        self.prompts.append(prompt)
        if not self.script:
            raise RuntimeError("fake model script is empty")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return Reply(item, input_tokens=len(prompt) // 4, output_tokens=len(item) // 4)


def get_model(max_attempts: int = 5) -> Model:
    if config.model_id() == "fake":
        if not config.is_test_env():
            raise RuntimeError("RULESTORM_MODEL=fake is for automated tests only (RULESTORM_ENV=test)")
        return FakeModel()
    return BedrockModel(max_attempts=max_attempts)
