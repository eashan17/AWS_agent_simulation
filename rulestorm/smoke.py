"""Day-0 smoke test: can we reach Bedrock, how fast is it, and what are our limits?"""

import os
import time

from pydantic import BaseModel, Field

from rulestorm import config
from rulestorm.llm import BedrockModel, decide


class Ping(BaseModel):
    ok: bool


class _Disruption(BaseModel):
    week: int = Field(ge=1, le=10)
    type: str
    affected: list[str]


class _Student(BaseModel):
    archetype: str
    constraints: list[str]


class SmokeBlueprint(BaseModel):
    """Roughly the size of a real blueprint reply, to time a realistic call."""

    threshold_pct: int = Field(ge=50, le=100)
    admin_capacity_per_week: int = Field(ge=0)
    checkpoint_week: int = Field(ge=1, le=10)
    students: list[_Student]
    disruptions: list[_Disruption]
    facts: list[str]
    assumptions: list[str]


BLUEPRINT_PROMPT = (
    "Policy: students need at least 80% attendance in each course to sit exams; "
    "exceptions need formal approval. Environment: one course, 10 weeks, a commuter, "
    "a resident, a working student and a student with family duties; transport "
    "disruptions happen; the attendance office processes only a few exception "
    "requests a week. Propose the simulation parameters: 4 students with 3 constraints "
    "each, 3 disruptions, 5 facts taken from the text and 5 assumptions you are adding."
)


def auth_method(session) -> str:
    profile = os.environ.get("AWS_PROFILE")
    if profile:
        return f"profile={profile}"
    credentials = session.get_credentials()
    if credentials is None:
        return "none"
    return "instance-role" if credentials.method == "iam-role" else credentials.method


def quotas(session, model_name: str) -> list[tuple[str, float]]:
    client = session.client("service-quotas", region_name=config.region())
    found = []
    for page in client.get_paginator("list_service_quotas").paginate(ServiceCode="bedrock"):
        for quota in page["Quotas"]:
            name = quota["QuotaName"]
            if model_name.lower() in name.lower() and "per minute" in name.lower():
                found.append((name, quota["Value"]))
    return sorted(found)


def model_name(session, model_id: str) -> str:
    """The display name Service Quotas uses, e.g. 'Mistral Large 3'."""
    bedrock = session.client("bedrock", region_name=config.region())
    return bedrock.get_foundation_model(modelIdentifier=model_id)["modelDetails"]["modelName"]


def run(model_id: str | None = None) -> list[str]:
    """Returns the lines to print, so the CLI and (later) the API show the same thing."""
    model = BedrockModel(model_id=model_id, max_attempts=1)
    lines = [
        f"model: {model.model_id}",
        f"region: {config.region()}",
        f"auth: {auth_method(model.session)}",
    ]

    started = time.monotonic()
    ping = decide("Reply with ok set to true.", Ping, model=model, max_tokens=50)
    latency_ms = round((time.monotonic() - started) * 1000)
    lines.append(f"ok: {str(bool(ping.value and ping.value.ok)).lower()}")
    lines.append(f"latency_ms: {latency_ms}")
    if ping.error:
        lines.append(f"error: {ping.error}")
        return lines

    blueprint = decide(BLUEPRINT_PROMPT, SmokeBlueprint, model=model, max_tokens=2000)
    lines.append(f"blueprint_valid: {str(not blueprint.no_action).lower()}")
    lines.append(f"blueprint_attempts: {blueprint.attempts}")
    lines.append(f"blueprint_input_tokens: {blueprint.input_tokens}")
    lines.append(f"output_tokens: {blueprint.output_tokens}")
    lines.append(f"seconds: {blueprint.seconds}")
    if blueprint.error:
        lines.append(f"blueprint_error: {blueprint.error}")

    try:
        name = model_name(model.session, model.model_id)
        found = quotas(model.session, name)
        if not found:
            lines.append(f"quotas: none found matching '{name}' and 'per minute'")
        for name, value in found:
            lines.append(f"quota: {name} = {value:g}")
    except Exception as exc:
        lines.append(f"quotas_error: {type(exc).__name__}: {exc}")
    return lines
