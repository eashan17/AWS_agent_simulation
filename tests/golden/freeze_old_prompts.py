"""Freezes the old engine's agent prompts (rulestorm.agents.Agents.prompt) for the fixed contexts
in contexts.json into <name>.txt. Slice L5 ran this once, before any prompt code changed; the
golden-prompt test (tests/test_prompts.py) then compares the template-generated prompts with
these files. It needs the old modules, so it stops working once slice L7 deletes them.

    python tests/golden/freeze_old_prompts.py
"""

import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # for test_blueprint.VALID

from rulestorm.agents import Agents  # noqa: E402
from rulestorm.engine import Attendance, Event  # noqa: E402
from rulestorm.llm import FakeModel  # noqa: E402
from rulestorm.policy import Blueprint, Profile, StudentProfile  # noqa: E402
from rulestorm.simulation import DecisionContext  # noqa: E402
from test_blueprint import VALID  # noqa: E402


def main() -> None:
    data = json.loads((HERE / "contexts.json").read_text(encoding="utf-8"))
    bp_data = copy.deepcopy(VALID)
    bp_data["policy"].update({k: data["policy"][k] for k in ("threshold_pct", "scope", "exception_rule")})
    bp_data["scenario"]["checkpoint_week"] = data["policy"]["checkpoint_week"]
    agents = Agents(Blueprint.model_validate(bp_data), model=FakeModel([]), cap=0)

    for name, c in data["contexts"].items():
        profile = c["profile"]
        if c["role"] == "student":
            profile = StudentProfile(archetype=c["person"], travel_buffer_min=c["travel_buffer_min"], **profile)
        else:
            profile = Profile(**profile)
        context = DecisionContext(
            agent=c["person"], role=c["role"], week=c["period"], session=c["step"],
            triggers=[Event(**t) for t in c["triggers"]], profile=profile,
            last_outcomes=c["last_outcomes"],
        )
        if c["role"] == "student":
            context.attendance = Attendance(student=c["person"], **c["attendance"])
            context.travel_buffer_min = c["travel_buffer_min"]
            context.pending_requests = context.attendance.pending
            context.uncovered_absences = c["uncovered"]
        else:
            context.pending_requests = c["pending_requests"]
        agents.memory[c["person"]] = c["memory"]
        (HERE / f"{name}.txt").write_text(agents.prompt(context) + "\n", encoding="utf-8", newline="\n")
        print(f"froze {name}.txt")


if __name__ == "__main__":
    main()
