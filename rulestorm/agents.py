"""The 6 LLM agents (4 students, faculty, advisor) that decide through the model adapter.

The attendance admin and examination officer are rule agents in code (rulestorm/simulation.py).

An agent decides only when the term loop triggers it. Its prompt is built from its blueprint
profile (description and goals; students also constraints), its role and the policy
parameters, plus the phase's shared snapshot and a compact memory of its own last decisions.
No goals or personalities are written here: they all come from the approved blueprint.

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
from typing import Literal

from pydantic import BaseModel, Field

from rulestorm import config, llm
from rulestorm.education import ROLE_ACTIONS
from rulestorm.engine import Engine
from rulestorm.policy import Blueprint
from rulestorm.simulation import DecisionContext, PhaseDecision, Proposal, Term

LLM_ROLES = frozenset({"student", "faculty", "advisor"})
PHASE_DEADLINE_S = 40.0
MAX_PARALLEL = 4
AGENT_MAX_TOKENS = 400
DEGRADED_ERROR_SHARE = 0.10
MEMORY_SIZE = 3

# Actions an LLM agent may propose, with their parameters. Recording attendance is the
# faculty's rule in code, so it is not offered. The engine still checks every proposal.
ACTION_PARAMS: dict[str, str] = {
    "attend": '{"session": <current session>}; optional "travel_buffer_min": 0-180 to change your travel slack',
    "skip": '{"session": <current session>}',
    "submit_exception_request": '{"sessions": [<your completed, absent sessions>], "reason": "<short>"}',
    "ask_advisor": '{"message": "<short>"}',
    "edit_attendance": '{"student": "<archetype>", "session": <n>, "present": true|false}',
    "cancel_session": '{"session": <a session that has not taken place>}',
    "advise_student": '{"student": "<archetype>", "advice": "<short>"}',
}
RULE_ACTIONS = frozenset({"record_attendance"})


class AgentDecision(BaseModel):
    """What one LLM agent returns for one phase. An empty `actions` list means "no action"."""

    actions: list[Proposal] = Field(default_factory=list, max_length=3)
    reason: str = Field(min_length=1, max_length=300, description="why, in your own words")
    strategy: str = Field("", max_length=200, description="your current strategy, one short sentence")


class CallCapReached(Exception):
    """The run's call cap is used up; the call is refused before it reaches the model."""


class CallBudget:
    """Per-run model-call cap, taken atomically so parallel agents can never exceed it."""

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
    """The decider for the term loop: `Agents(...).decide_phase` matches simulation.Decider."""

    def __init__(
        self,
        blueprint: Blueprint,
        model: llm.Model | None = None,
        cap: int | None = None,
        phase_deadline_s: float = PHASE_DEADLINE_S,
        max_parallel: int = MAX_PARALLEL,
    ) -> None:
        self.bp = blueprint
        self.budget = CallBudget(config.max_llm_calls_per_run() if cap is None else cap)
        self.model = CappedModel(model or llm.get_model(), self.budget)
        self.phase_deadline_s = phase_deadline_s
        self.max_parallel = max_parallel
        self.memory: dict[str, list[str]] = {}
        self.prompts: dict[str, list[str]] = {}  # agent -> prompts sent, for checks and the decision log
        self.timeouts = 0
        self._tokens_lock = threading.Lock()
        self.input_tokens = 0
        self.output_tokens = 0

    # --- prompt ----------------------------------------------------------------------------

    def prompt(self, c: DecisionContext) -> str:
        p = self.bp.policy
        lines = [
            f"You are the {c.role} agent `{c.agent}` in a simulated term of one course "
            f"(week {c.week}, session {c.session}). Decide what you do now, as this person would.",
            "",
            "Who you are (from the approved blueprint):",
            f"- description: {c.profile.description}" if c.profile else "- description: (none)",
        ]
        if c.profile:
            lines.append("- goals: " + "; ".join(c.profile.goals))
            constraints = getattr(c.profile, "constraints", None)
            if constraints:
                lines.append("- constraints: " + "; ".join(constraints))
        if c.travel_buffer_min is not None:
            lines.append(f"- travel buffer: {c.travel_buffer_min} min (a longer transport delay makes you late)")
        lines += [
            "",
            "Policy:",
            f"- minimum attendance for exam eligibility: {p.threshold_pct}% ({p.scope})",
            f"- exception rule: {p.exception_rule}",
            f"- eligibility is checked in week {self.bp.scenario.checkpoint_week}",
            "",
            "What just happened (the events that triggered you):",
            *(f"- {t.event_id} week {t.week} {t.type}: {json.dumps(t.payload, ensure_ascii=False)}"
              + (f" changed {json.dumps(t.state_change, ensure_ascii=False)}" if t.state_change else "")
              for t in c.triggers),
        ]
        if c.attendance is not None:
            lines.append(f"Your attendance so far: {c.attendance.text()}; pending requests: "
                         f"{', '.join(c.attendance.pending) or 'none'}")
        elif c.pending_requests:
            lines.append(f"Pending exception requests: {', '.join(c.pending_requests)}")
        memory = self.memory.get(c.agent)
        if memory:
            lines += ["", "Your recent decisions:", *(f"- {m}" for m in memory)]
        lines += [
            "",
            "Actions you may propose (0 to 3; an empty list means you do nothing):",
            *(f"- {a}: params {ACTION_PARAMS[a]}" for a in sorted(ROLE_ACTIONS[c.role] - RULE_ACTIONS)),
            "Each action is {\"action\": <name>, \"params\": {...}}. "
            "Give a short reason and your current strategy.",
        ]
        return "\n".join(lines)

    # --- one phase -------------------------------------------------------------------------

    def decide_one(self, context: DecisionContext, prompt: str) -> PhaseDecision:
        outcome = llm.decide(prompt, AgentDecision, model=self.model, max_tokens=AGENT_MAX_TOKENS)
        with self._tokens_lock:
            self.input_tokens += outcome.input_tokens
            self.output_tokens += outcome.output_tokens
        if outcome.no_action:
            return PhaseDecision(agent=context.agent, error=outcome.error or "no reply")
        return PhaseDecision(agent=context.agent, proposals=outcome.value.actions, reason=outcome.value.reason,
                             strategy=outcome.value.strategy)

    def decide_phase(self, contexts: list[DecisionContext]) -> list[PhaseDecision]:
        """Triggered LLM agents decide in parallel on the same snapshot; results come back
        sorted by agent ID, so the engine validates them in an order independent of timing."""
        decisions: dict[str, PhaseDecision] = {}
        calls = []
        for c in contexts:
            if c.role not in LLM_ROLES:  # rule agents act in code, never through the model
                decisions[c.agent] = PhaseDecision(agent=c.agent, reason="rule agent")
                continue
            prompt = self.prompt(c)
            self.prompts.setdefault(c.agent, []).append(prompt)
            calls.append((c, prompt))

        if calls:
            pool = ThreadPoolExecutor(max_workers=min(self.max_parallel, len(calls)))
            futures = {pool.submit(self.decide_one, c, p): c for c, p in calls}
            done, _ = wait_futures(futures, timeout=self.phase_deadline_s)
            pool.shutdown(wait=False, cancel_futures=True)  # a late call's reply is discarded
            for future, c in futures.items():
                if future in done:
                    decisions[c.agent] = future.result()
                else:
                    self.timeouts += 1
                    decisions[c.agent] = PhaseDecision(
                        agent=c.agent, error=f"timeout: no reply within the {self.phase_deadline_s:g} s phase deadline")

        for d in decisions.values():
            if d.error is None and d.reason != "rule agent":
                actions = ", ".join(p.action for p in d.proposals) or "nothing"
                note = f"week {contexts[0].week}: {actions} because {d.reason[:120]}"
                if d.strategy:
                    note += f" (strategy: {d.strategy[:80]})"
                self.memory[d.agent] = [*self.memory.get(d.agent, []), note][-MEMORY_SIZE:]
        return [decisions[a] for a in sorted(decisions)]


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


def run_term(blueprint: Blueprint, agents: Agents | None = None, on_week=None) -> tuple[Engine, RunSummary]:
    """One simulated term with the LLM agents. Returns the engine (event log) and the summary."""
    agents = agents or Agents(blueprint)
    engine = Term(blueprint, agents.decide_phase).run(on_week)
    return engine, summarise(engine, agents)
