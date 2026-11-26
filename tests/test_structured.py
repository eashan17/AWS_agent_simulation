"""Slice M7d: Bedrock structured output for the pick, fill, variants and search calls (no Bedrock)."""

import json

import pytest
from pydantic import BaseModel, Field

from rulestorm import llm, structured
from rulestorm.blueprint import fill_schema
from rulestorm.core.model import load_template
from rulestorm.llm import BedrockModel, FakeModel, decide, schema_counts, strict_schema


class Item(BaseModel):
    title: str = Field(min_length=1, max_length=20)  # a field named like a keyword stays
    score: int = Field(ge=0, le=10)


class Reply(BaseModel):
    items: list[Item] = Field(min_length=2, max_length=5)
    note: str | None = None


def objects(node):
    if isinstance(node, dict):
        if node.get("type") == "object" or "properties" in node:
            yield node
        for v in node.values():
            yield from objects(v)
    elif isinstance(node, list):
        for v in node:
            yield from objects(v)


def test_the_strict_schema_keeps_what_bedrock_enforces_and_closes_every_object() -> None:
    schema = strict_schema(Reply)
    text = json.dumps(schema)
    for keyword in ('"minimum"', '"maximum"', '"minLength"', '"maxLength"', '"maxItems"'):
        assert keyword not in text, keyword
    assert schema["properties"]["items"]["minItems"] == 1  # 2 isn't enforceable; Pydantic still checks it
    assert all(o["additionalProperties"] is False for o in objects(schema))
    assert "title" in schema["$defs"]["Item"]["properties"]  # a property name is not the `title` keyword
    assert schema_counts(schema) == (1, 1)  # `note` is optional and a union


def test_every_fixed_schema_is_within_bedrocks_limits() -> None:
    for name, model in structured.fixed_schemas().items():
        optional, unions = schema_counts(strict_schema(model))
        assert optional <= llm.MAX_OPTIONAL and unions <= llm.MAX_UNIONS, name
    assert set(structured.fixed_schemas()) == {"pick", "fill attendance", "fill hostel_curfew",
                                               "variants attendance", "variants hostel_curfew"}
    assert all(line.endswith("-> ok") for line in structured.schema_lines())


def test_a_label_can_only_name_a_value_the_fill_sets_or_a_section() -> None:
    schema = strict_schema(fill_schema(load_template("attendance")))
    label = next(d for name, d in schema["$defs"].items() if name.startswith("FillLabel"))
    allowed = label["properties"]["field"]["enum"]
    assert "people" in allowed and "threshold_pct" in allowed
    assert "excused_counting" not in allowed and "purpose" not in allowed  # a reading isn't in the fill


def test_decide_sends_the_strict_schema_only_when_asked_and_still_validates() -> None:
    good = json.dumps({"items": [{"title": "a", "score": 1}, {"title": "b", "score": 2}]})
    asked = FakeModel([good])
    assert decide("p", Reply, model=asked, structured=True).value is not None
    assert asked.schemas == [strict_schema(Reply)]
    plain = FakeModel([good])
    decide("p", Reply, model=plain)
    assert plain.schemas == [None]
    too_few = json.dumps({"items": [{"title": "a", "score": 1}]})  # well-formed, but Pydantic refuses it
    retried = FakeModel([too_few, good])
    outcome = decide("p", Reply, model=retried, structured=True)
    assert outcome.value is not None and outcome.attempts == 2


def test_a_model_that_takes_no_schema_is_called_as_before() -> None:
    class Old:
        model_id = "old"

        def complete(self, prompt, max_tokens, timeout_s=None):  # no schema argument
            return llm.Reply(json.dumps({"items": [{"title": "a", "score": 1}, {"title": "b", "score": 2}]}), 1, 1)

    assert decide("p", Reply, model=Old(), structured=True, deadline_s=5).value is not None


class FakeClient:
    """Bedrock's converse: refuses `outputConfig` once, as for a schema it can't take."""

    def __init__(self) -> None:
        self.requests: list[dict] = []

    def converse(self, **request):
        self.requests.append(request)
        if "outputConfig" in request:
            raise type("ValidationException", (Exception,), {})("Schema is too complex")
        return {"output": {"message": {"content": [{"text": '{"ok": true}'}]}},
                "usage": {"inputTokens": 3, "outputTokens": 2}}


def test_a_schema_bedrock_refuses_falls_back_to_the_plain_call() -> None:
    model = object.__new__(BedrockModel)  # no AWS session: the client is the fake above
    model.model_id, model.client = "deepseek.v3.2", FakeClient()
    reply = model.complete("p", 50, None, schema=strict_schema(Reply))
    assert reply.text == '{"ok": true}'
    first, second = model.client.requests
    sent = first["outputConfig"]["textFormat"]
    assert sent["type"] == "json_schema" and json.loads(sent["structure"]["jsonSchema"]["schema"]) == strict_schema(Reply)
    assert "outputConfig" not in second


def test_the_warm_up_compiles_each_schema_once_and_never_raises(monkeypatch) -> None:
    calls = []

    class Recorder:
        model_id, structured = "rec", True

        def complete(self, prompt, max_tokens, timeout_s=None, schema=None):
            calls.append((max_tokens, timeout_s, schema))
            if len(calls) == 2:
                raise RuntimeError("throttled")
            return llm.Reply("{}", 1, 1)

    lines = structured.warm(Recorder())
    assert len(calls) == 5 and all(c[0] == structured.WARM_TOKENS and c[2] for c in calls)
    assert sum(line.startswith("not warmed") for line in lines) == 1
    assert structured.warm_in_background() is None  # the tests run on the fake model
    monkeypatch.setenv("RULESTORM_MODEL", "deepseek.v3.2")
    monkeypatch.setenv("RULESTORM_WARM_SCHEMAS", "0")
    assert structured.warm_in_background() is None  # turned off


@pytest.mark.parametrize("call", ["pick", "fill"])
def test_the_blueprint_calls_ask_for_structured_output(call, tmp_path) -> None:
    from rulestorm.policy import PolicyInput, interpret
    from rulestorm.store import Store
    from test_blueprint import FILL, PICK

    policy = Store(str(tmp_path / "t.db")).save_policy(PolicyInput(text="80% attendance", purpose="y", environment="z"))
    model = FakeModel([PICK, json.dumps(FILL)])
    interpret(policy, model)
    pick, fill = model.schemas
    assert (pick if call == "pick" else fill) is not None
