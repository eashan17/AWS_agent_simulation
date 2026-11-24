import pytest
from pydantic import BaseModel, Field

from rulestorm import llm
from rulestorm.llm import FakeModel, decide


class Choice(BaseModel):
    action: str
    hours: int = Field(ge=0, le=10)


def test_valid_reply() -> None:
    model = FakeModel(['{"action": "attend", "hours": 2}'])
    outcome = decide("choose", Choice, model=model)
    assert outcome.value == Choice(action="attend", hours=2)
    assert outcome.attempts == 1 and outcome.error is None


def test_retry_then_valid() -> None:
    model = FakeModel(['{"action": "attend", "hours": 99}', '```json\n{"action": "skip", "hours": 0}\n```'])
    outcome = decide("choose", Choice, model=model)
    assert outcome.value == Choice(action="skip", hours=0)
    assert outcome.attempts == 2
    assert "previous reply was invalid" in model.prompts[1]


def test_invalid_twice_is_no_action() -> None:
    model = FakeModel(["not json", '{"action": "attend"}'])
    outcome = decide("choose", Choice, model=model)
    assert outcome.no_action
    assert outcome.attempts == 2
    assert outcome.error.startswith("invalid reply")


def test_exception_is_no_action() -> None:
    model = FakeModel([TimeoutError("read timed out")])
    outcome = decide("choose", Choice, model=model)
    assert outcome.no_action
    assert outcome.error == "TimeoutError: read timed out"


def test_fake_model_refused_outside_tests(monkeypatch) -> None:
    monkeypatch.setenv("RULESTORM_ENV", "production")
    with pytest.raises(RuntimeError, match="automated tests only"):
        llm.get_model()
