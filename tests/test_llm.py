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


class SlowFake(FakeModel):
    """Each call 'takes' a set number of seconds on a fake clock."""

    def __init__(self, script, seconds_per_call, clock) -> None:
        super().__init__(script)
        self.seconds_per_call, self.clock = seconds_per_call, clock

    def complete(self, prompt, max_tokens, timeout_s=None):
        self.clock[0] += self.seconds_per_call
        return super().complete(prompt, max_tokens, timeout_s)


def test_deadline_shared_by_both_attempts(monkeypatch) -> None:
    clock = [0.0]
    monkeypatch.setattr(llm.time, "monotonic", lambda: clock[0])
    # First reply invalid after 20 s: the retry may wait for the remaining 35 s.
    model = SlowFake(["not json", '{"action": "attend", "hours": 2}'], 20, clock)
    outcome = decide("choose", Choice, model=model, deadline_s=55)
    assert outcome.attempts == 2 and outcome.value is not None
    assert model.timeouts == [55, 35]


def test_no_retry_when_budget_nearly_spent(monkeypatch) -> None:
    clock = [0.0]
    monkeypatch.setattr(llm.time, "monotonic", lambda: clock[0])
    # First reply invalid after 45 s: 10 s left is under MIN_ATTEMPT_S, so no second call.
    model = SlowFake(["not json", '{"action": "attend", "hours": 2}'], 45, clock)
    outcome = decide("choose", Choice, model=model, deadline_s=55)
    assert outcome.no_action and outcome.attempts == 1 and len(model.prompts) == 1
    assert "no retry" in outcome.error


def test_no_deadline_keeps_the_configured_timeout() -> None:
    model = FakeModel(['{"action": "attend", "hours": 2}'])
    decide("choose", Choice, model=model)
    assert model.timeouts == [None]
