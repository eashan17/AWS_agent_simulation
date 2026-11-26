"""Model adapter: one `decide(prompt, schema)` over Bedrock Converse, plus a scripted fake.

Contract (docs/ARCHITECTURE.md, Model adapter contract):
- asks for JSON in the prompt (no tool use) and validates the reply with Pydantic;
- on an invalid reply, retries once with the validation error included;
- any exception, or a second invalid reply, gives a "no action" outcome with the error text.
It never raises for model or AWS errors, so one bad call cannot crash a run.
"""

import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from rulestorm import config

T = TypeVar("T", bound=BaseModel)
log = logging.getLogger("rulestorm.llm")

MAX_ERROR_CHARS = 500
# With a deadline, a retry starts only if at least this much time is left: a blueprint reply
# takes about 20 s, so a shorter window would only spend credits on a call that times out.
MIN_ATTEMPT_S = 15.0


@dataclass
class Reply:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


class Model(Protocol):
    model_id: str

    def complete(self, prompt: str, max_tokens: int, timeout_s: float | None = None) -> Reply: ...


# --- structured output (slice M7d) ---------------------------------------------------------------
# Bedrock Converse `outputConfig.textFormat` (json_schema) constrains decoding to a schema: the reply
# is always well-formed JSON of that shape. Bedrock enforces types, enums, `required`, `$defs` and
# `minItems` 0 or 1, but not numeric limits, lengths or `maxItems`, and every object must be closed.
# Those keywords are left out of what Bedrock sees; Pydantic still checks every reply.
_NOT_ENFORCED = {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "minLength",
                 "maxLength", "maxItems", "title"}
MAX_OPTIONAL, MAX_UNIONS = 12, 16  # Bedrock's limits per schema


def strict_schema(schema: type[BaseModel]) -> dict:
    """The model's JSON schema in the subset Bedrock enforces."""
    def walk(node):
        if isinstance(node, list):
            return [walk(x) for x in node]
        if not isinstance(node, dict):
            return node
        out = {}
        for k, v in node.items():
            if k in ("properties", "$defs") and isinstance(v, dict):  # names, not keywords: keep them all
                out[k] = {name: walk(sub) for name, sub in v.items()}
            elif k not in _NOT_ENFORCED:
                out[k] = walk(v)
        if out.get("minItems", 0) > 1:
            out["minItems"] = 1
        if out.get("type") == "object" or "properties" in out:
            out["additionalProperties"] = False
            out.setdefault("properties", {})
        return out

    return walk(schema.model_json_schema())


def schema_counts(schema: dict) -> tuple[int, int]:
    """(optional properties, union-typed properties), counted across every object, as Bedrock does."""
    optional = unions = 0

    def walk(node) -> None:
        nonlocal optional, unions
        if isinstance(node, dict):
            if isinstance(node.get("properties"), dict):
                optional += len(set(node["properties"]) - set(node.get("required", [])))
                unions += sum(1 for p in node["properties"].values()
                              if isinstance(p, dict) and ("anyOf" in p or isinstance(p.get("type"), list)))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)
    return optional, unions


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


# What an AWS error may carry that must never reach the API or the timeline: ARNs (which hold
# the account ID and role names), bare 12-digit account IDs and access key IDs.
_SECRETS = (
    (re.compile(r"arn:aws[\w-]*:[^\s'\",)]*"), "<arn>"),
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), "<access key>"),
    (re.compile(r"\b\d{12}\b"), "<account>"),
)


def redact(text: str) -> str:
    """The text with ARNs, account IDs and access key IDs replaced (slice 7b)."""
    for pattern, replacement in _SECRETS:
        text = pattern.sub(replacement, text)
    return text


def _short(text: str) -> str:
    return text if len(text) <= MAX_ERROR_CHARS else text[:MAX_ERROR_CHARS] + "…"


def _extract_json(text: str) -> str:
    """Models often wrap JSON in prose or ``` fences; take the outermost object."""
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start != -1 and end > start else text


# A key whose `":` the model dropped or mistyped before a list: `"constraints["x"]`, `"constraints=["x"]`
# (both seen in real fills, 27 Nov). Only a key right after `{` or `,` is touched.
_KEY_WITHOUT_COLON = re.compile(r'(?<=[{,])"(\w+)"?\s*=?\s*\[')


def _repaired(text: str) -> str:
    """The reply as is if it parses; else with only that one typo repaired. Pydantic still checks
    every value, so a repair can't make a wrong reply valid, only a well-formed one readable."""
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        return _KEY_WITHOUT_COLON.sub(r'"\1":[', text)


def _prompt_with_schema(prompt: str, schema: type[BaseModel]) -> str:
    return (
        f"{prompt}\n\nReply with one JSON object only, no other text, written compactly on a single line "
        "(no indentation or line breaks: whitespace costs time). "
        f"It must match this JSON schema:\n{json.dumps(schema.model_json_schema())}"
    )


class DeadlineExceeded(Exception):
    """No reply before the time budget ran out."""


def _complete_by(model: "Model", prompt: str, max_tokens: int, timeout_s: float | None,
                 schema: dict | None = None) -> Reply:
    """Boto's read timeout only fires when the socket goes quiet, so it is not a wall-clock
    limit (a blueprint once took 75 s against a 55 s budget). With a timeout, the call runs in
    a daemon thread and we stop waiting at the deadline; an abandoned call finishes unseen.
    `schema` (slice M7d) goes only to a model that says it takes one (`structured`)."""
    extra = {"schema": schema} if schema is not None and getattr(model, "structured", False) else {}
    if timeout_s is None:
        return model.complete(prompt, max_tokens, None, **extra)
    box: dict = {}

    def call() -> None:
        try:
            box["reply"] = model.complete(prompt, max_tokens, timeout_s, **extra)
        except Exception as exc:  # handed back to decide, which records it
            box["error"] = exc

    worker = threading.Thread(target=call, daemon=True)
    worker.start()
    worker.join(timeout_s)
    if worker.is_alive():
        raise DeadlineExceeded(f"no reply within {timeout_s:.0f} s")
    if "error" in box:
        raise box["error"]
    return box["reply"]


def decide(
    prompt: str,
    schema: type[T],
    model: Model | None = None,
    max_tokens: int = 800,
    deadline_s: float | None = None,
    structured: bool = False,
) -> Outcome[T]:
    """`deadline_s` is one time budget shared by both attempts: each attempt may wait for
    whatever is left of it, and the retry is skipped if less than MIN_ATTEMPT_S remains.
    `structured` (slice M7d) asks the model to constrain its reply to the schema."""
    model = model or get_model()
    outcome: Outcome[T] = Outcome(value=None)
    started = time.monotonic()
    current = _prompt_with_schema(prompt, schema)
    constraint = strict_schema(schema) if structured else None
    try:
        for attempt in (1, 2):
            timeout_s = None
            if deadline_s is not None:
                timeout_s = deadline_s - (time.monotonic() - started)
                if attempt > 1 and timeout_s < MIN_ATTEMPT_S:
                    outcome.error += f" (no retry: {timeout_s:.0f} s left of the {deadline_s:.0f} s budget)"
                    break
            outcome.attempts = attempt
            reply = _complete_by(model, current, max_tokens, timeout_s, constraint)
            outcome.raw_replies.append(reply.text)
            outcome.input_tokens += reply.input_tokens
            outcome.output_tokens += reply.output_tokens
            try:
                outcome.value = schema.model_validate_json(_repaired(_extract_json(reply.text)))
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
        log.warning("model call failed: %s: %s", type(exc).__name__, exc)  # in full, server log only
        outcome.error = f"{type(exc).__name__}: {_short(redact(str(exc)))}"
    outcome.seconds = round(time.monotonic() - started, 2)
    return outcome


class BedrockModel:
    """Bedrock Converse in-Region. `max_attempts=1` turns boto retries off (blueprint calls)."""

    structured = True  # slice M7d: takes a schema for Bedrock structured output

    def __init__(self, model_id: str | None = None, max_attempts: int = 5) -> None:
        import boto3
        from botocore.config import Config

        self.model_id = model_id or config.model_id()
        self.max_attempts = max_attempts
        self.session = boto3.Session(region_name=config.region())
        # Resolve the credentials once, here, rather than in each first call: on a laptop signed in
        # with `aws login`, several people's first calls resolving them at once in parallel threads
        # timed out the first phases of every run (26 Nov: 25 of 34 timeouts in 5 runs). A boto3
        # session isn't thread-safe, so clients are also made one at a time.
        credentials = self.session.get_credentials()
        if credentials is not None:
            credentials.get_frozen_credentials()
        self._clients: dict[int, object] = {}
        self._lock = threading.Lock()
        self._config = Config
        self.client = self._client(config.read_timeout_s())

    def _client(self, read_timeout_s: float):
        """One client per read timeout, rounded up to 10 s steps so a run makes only a few (boto
        fixes the timeout per client; the wall-clock limit is _complete_by's)."""
        key = max(10, -(-int(read_timeout_s) // 10) * 10)
        with self._lock:
            if key not in self._clients:
                self._clients[key] = self.session.client(
                    "bedrock-runtime",
                    config=self._config(
                        connect_timeout=5,
                        read_timeout=key,
                        retries={"mode": "adaptive", "max_attempts": self.max_attempts},
                    ),
                )
            return self._clients[key]

    def complete(self, prompt: str, max_tokens: int, timeout_s: float | None = None,
                 schema: dict | None = None) -> Reply:
        client = self.client if timeout_s is None else self._client(timeout_s)
        request = {"modelId": self.model_id, "messages": [{"role": "user", "content": [{"text": prompt}]}],
                   "inferenceConfig": {"maxTokens": max_tokens, "temperature": 0.7}}
        if schema is not None:
            constrained = {**request, "outputConfig": {"textFormat": {"type": "json_schema", "structure": {
                "jsonSchema": {"name": str(schema.get("title") or "reply")[:64] or "reply",
                               "schema": json.dumps(schema)}}}}}
            try:
                response = client.converse(**constrained)
            except Exception as exc:  # Bedrock refused the schema ("Schema is too complex", a keyword)
                if "ValidationException" not in type(exc).__name__ + str(getattr(exc, "response", "")):
                    raise
                log.warning("structured output refused, calling without it: %s", _short(str(exc)))
                response = client.converse(**request)
        else:
            response = client.converse(**request)
        text = "".join(
            part.get("text", "") for part in response["output"]["message"]["content"]
        )
        usage = response.get("usage", {})
        return Reply(text, usage.get("inputTokens", 0), usage.get("outputTokens", 0))


class FakeModel:
    """Scripted replies for automated tests. Each item is a reply text or an exception to raise."""

    model_id = "fake"
    structured = True  # records the schema it was given (slice M7d); the script decides the reply

    def __init__(self, script: list[str | Exception] | None = None) -> None:
        self.script = list(script or [])
        self.prompts: list[str] = []
        self.timeouts: list[float | None] = []
        self.schemas: list[dict | None] = []

    def complete(self, prompt: str, max_tokens: int, timeout_s: float | None = None,
                 schema: dict | None = None) -> Reply:
        self.prompts.append(prompt)
        self.timeouts.append(timeout_s)
        self.schemas.append(schema)
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
