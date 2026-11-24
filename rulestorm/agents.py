"""The LLM people of a template that decide through the model adapter.

Which roles are LLM people, their allowed actions and their prompt all come from the template
(rulestorm/prompts.py); their profiles come from the approved blueprint's values. Rule roles
(recorder, queue processor, checker) run in the engine and are never asked.

A person decides only when the term loop (rulestorm/core/term.py) triggers them. Their prompt is
built from the template, their blueprint profile and the phase's shared snapshot, plus a compact
memory of their own last decisions. No goals or personalities are written here.

Spend and time guards (docs/ARCHITECTURE.md, Model adapter contract):
- a per-run cap on model calls, taken atomically per call (a validation retry is a call too);
- one decision phase has a deadline; a call still unfinished then is a timeout "no action";
- any model error is a recorded "no action", never a crash;
- a run ends `degraded` when more than 10% of its decisions were error no-actions or the cap
  stopped it.
"""

import json
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import wait as wait_futures
from typing import Any, Literal

from pydantic import BaseModel, Field

from rulestorm import config, llm
from rulestorm.core.engine import Engine
from rulestorm.core.model import Template
from rulestorm.core.term import DecisionContext, PhaseDecision, Proposal, Term
from rulestorm.prompts import render_prompt

PHASE_DEADLINE_S = 40.0
MAX_PARALLEL = 4
AGENT_MAX_TOKENS = 400
DEGRADED_ERROR_SHARE = 0.10
MEMORY_SIZE = 3


class AgentDecision(BaseModel):
    """What one LLM person returns for one phase. An empty `actions` list means "no action"."""

    actions: list[Proposal] = Field(default_factory=list, max_length=3)
    reason: str = Field(min_length=1, max_length=300, description="why, in your own words")
    strategy: str = Field("", max_length=200, description="your current strategy, one short sentence")


class CallCapReached(Exception):
    """The run's call cap is used up; the call is refused before it reaches the model."""


class NotPortedYet(RuntimeError):
    """This feature still needs its port to the template format (stress variants: slice L8)."""


class CallBudget:
    """Per-run model-call cap, taken atomically so parallel people can never exceed it."""

    def __init__(self, cap: int) -> None:
        self.cap = cap
        self.used = 0
        self.refused = 0
        self._lock = threading.Lock()

    def take(self) -> bool:
        with self._lock:
            if self.used >= self.cap:
                self.refused += 1
                return False
            self.used += 1
            return True

    @property
    def cap_hits(self) -> int:
        """How many times the cap stopped this run: 0 or 1 (it never resets within a run)."""
        return 1 if self.refused else 0


class CappedModel:
    """Wraps a model so every call (first try and retry) first takes a slot from the budget."""

    def __init__(self, model: llm.Model, budget: CallBudget) -> None:
        self.model = model
        self.budget = budget
        self.model_id = model.model_id

    def complete(self, prompt: str, max_tokens: int, timeout_s: float | None = None) -> llm.Reply:
        if not self.budget.take():
            raise CallCapReached(f"run call cap of {self.budget.cap} reached")
        return self.model.complete(prompt, max_tokens, timeout_s)


def is_cap_error(error: str | None) -> bool:
    return bool(error) and error.startswith(CallCapReached.__name__)


class Agents:
    """The decider for the term loop: `Agents(...).decide_phase` matches core.term.Decider."""

    def __init__(
        self,
        template: Template,
        values: dict[str, Any],
        model: llm.Model | None = None,
        cap: int | None = None,
        phase_deadline_s: float = PHASE_DEADLINE_S,
        max_parallel: int = MAX_PARALLEL,
    ) -> None:
        self.template = template
        self.values = values
        self.llm_roles = {r.id for r in template.roles if r.llm}
        self.budget = CallBudget(config.max_llm_calls_per_run() if cap is None else cap)
        self.model = CappedModel(model or llm.get_model(), self.budget)
        self.phase_deadline_s = phase_deadline_s
        self.max_parallel = max_parallel
        self.memory: dict[str, list[str]] = {}
        self.prompts: dict[str, list[str]] = {}  # person -> prompts sent, for checks and the decision log
        self.timeouts = 0
        self._tokens_lock = threading.Lock()
        self.input_tokens = 0
        self.output_tokens = 0

    def prompt(self, c: DecisionContext) -> str:
        return render_prompt(self.template, self.values, c, self.memory.get(c.person, ()))

    # --- one phase -------------------------------------------------------------------------

    def decide_one(self, context: DecisionContext, prompt: str) -> PhaseDecision:
        outcome = llm.decide(prompt, AgentDecision, model=self.model, max_tokens=AGENT_MAX_TOKENS)
        with self._tokens_lock:
            self.input_tokens += outcome.input_tokens
            self.output_tokens += outcome.output_tokens
        if outcome.no_action:
            return PhaseDecision(person=context.person, error=outcome.error or "no reply")
        return PhaseDecision(person=context.person, proposals=outcome.value.actions, reason=outcome.value.reason,
                             strategy=outcome.value.strategy)

    def decide_phase(self, contexts: list[DecisionContext]) -> list[PhaseDecision]:
        """Triggered LLM people decide in parallel on the same snapshot; results come back
        sorted by person ID, so the engine validates them in an order independent of timing."""
        decisions: dict[str, PhaseDecision] = {}
        calls = []
        for c in contexts:
            if c.role not in self.llm_roles:  # rule roles act in the engine, never through the model
                decisions[c.person] = PhaseDecision(person=c.person, reason="rule role")
                continue
            prompt = self.prompt(c)
            self.prompts.setdefault(c.person, []).append(prompt)
            calls.append((c, prompt))

        if calls:
            pool = ThreadPoolExecutor(max_workers=min(self.max_parallel, len(calls)))
            futures = {pool.submit(self.decide_one, c, p): c for c, p in calls}
            done, _ = wait_futures(futures, timeout=self.phase_deadline_s)
            pool.shutdown(wait=False, cancel_futures=True)  # a late call's reply is discarded
            for future, c in futures.items():
                if future in done:
                    decisions[c.person] = future.result()
                else:
                    self.timeouts += 1
                    decisions[c.person] = PhaseDecision(
                        person=c.person, error=f"timeout: no reply within the {self.phase_deadline_s:g} s phase deadline")

        period_label = self.template.calendar.period_label
        for d in decisions.values():
            if d.error is None and d.reason != "rule role":
                actions = ", ".join(p.action for p in d.proposals) or "nothing"
                note = f"{period_label} {contexts[0].period}: {actions} because {d.reason[:120]}"
                if d.strategy:
                    note += f" (strategy: {d.strategy[:80]})"
                self.memory[d.person] = [*self.memory.get(d.person, []), note][-MEMORY_SIZE:]
        return [decisions[p] for p in sorted(decisions)]


# --- a whole run -----------------------------------------------------------------------------


class Rejection(BaseModel):
    event_id: str
    agent: str
    action: str
    reason: str


class RunSummary(BaseModel):
    status: Literal["completed", "degraded"]
    model_id: str
    llm_cap: int
    llm_calls: int
    llm_errors: int
    cap_hits: int
    timeouts: int
    decisions: int
    decisions_by_agent: dict[str, int]
    no_actions: int
    rejected: list[Rejection]
    input_tokens: int
    output_tokens: int


def summarise(engine: Engine, agents: Agents) -> RunSummary:
    decisions = [e for e in engine.events if e.type == "decision"]
    errors = [d for d in decisions if d.payload.get("error") and not is_cap_error(d.payload["error"])]
    llm_actors = {d.actor for d in decisions}
    rejected = [
        Rejection(event_id=e.event_id, agent=e.actor, action=e.payload["action"], reason=e.payload["reason"])
        for e in engine.events if e.type == "action_rejected" and e.actor in llm_actors
    ]
    error_share = len(errors) / len(decisions) if decisions else 0.0
    degraded = error_share > DEGRADED_ERROR_SHARE or agents.budget.cap_hits > 0
    return RunSummary(
        status="degraded" if degraded else "completed",
        model_id=agents.model.model_id,
        llm_cap=agents.budget.cap,
        llm_calls=agents.budget.used,
        llm_errors=len(errors),
        cap_hits=agents.budget.cap_hits,
        timeouts=agents.timeouts,
        decisions=len(decisions),
        decisions_by_agent=dict(sorted(Counter(d.actor for d in decisions).items())),
        no_actions=sum(1 for d in decisions if d.payload["no_action"]),
        rejected=rejected,
        input_tokens=agents.input_tokens,
        output_tokens=agents.output_tokens,
    )


def run_term(template: Template, values: dict[str, Any], agents: Agents | None = None,
             on_period=None) -> tuple[Engine, RunSummary]:
    """One simulated term with the LLM people. Returns the engine (event log) and the summary."""
    agents = agents or Agents(template, values)
    engine = Term(template, values, agents.decide_phase).run(on_period)
    return engine, summarise(engine, agents)


def run_local(store, blueprint_id: str, out_dir: str = "runs", on_period=None) -> tuple[str, RunSummary, float, str]:
    """A real term on the approved blueprint, in this process (the background runner is slice 7a).
    Writes the event log, the blueprint and the summary to <out_dir>/<run_id>.json (UTF-8) so a
    run can be read by hand. Returns (run_id, summary, seconds, path)."""
    import time
    import uuid
    from pathlib import Path

    from rulestorm.core.model import load_template
    from rulestorm.policy import require_approved

    record = require_approved(store, blueprint_id)
    bp = record.blueprint
    template = load_template(bp.template_id)
    if template.version != bp.template_version:
        raise ValueError(f"blueprint {blueprint_id} was made with {bp.template_id}@{bp.template_version}, "
                         f"but the template is now {template.ref}")
    run_id = f"L-{uuid.uuid4().hex[:8]}"
    started = time.monotonic()
    engine, summary = run_term(template, bp.values, on_period=on_period)
    seconds = round(time.monotonic() - started, 1)
    path = Path(out_dir) / f"{run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "run_id": run_id,
        "blueprint_id": blueprint_id,
        "template": template.ref,
        "seconds": seconds,
        "summary": summary.model_dump(),
        "blueprint": bp.model_dump(),
        "events": [e.model_dump() for e in engine.events],
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return run_id, summary, seconds, str(path)
