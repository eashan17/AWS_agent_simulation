"""The education model's structure and the pre-filled example input.

No scenario numbers live here: those come from the approved blueprint.
The example input is ordinary, editable user input, kept descriptive.
"""

from typing import Literal

# The 4 student archetypes the simulation always has (BRIEF must-have 4).
Archetype = Literal["commuter", "resident", "working", "family"]
ARCHETYPES: dict[str, str] = {
    "commuter": "long-distance commuter",
    "resident": "lives on or near campus",
    "working": "has fixed work hours",
    "family": "has family responsibilities",
}

# General mechanics of the education model (BRIEF must-have 3), not scenario values.
TERM_WEEKS = 10
SESSIONS_PER_WEEK = 2

# The 8 agents: 4 students (LLM), faculty and advisor (LLM), attendance admin and
# examination officer (rule-following code). Agent ID -> role.
AGENT_ROLES: dict[str, str] = {
    **{archetype: "student" for archetype in ARCHETYPES},
    "faculty": "faculty",
    "advisor": "advisor",
    "attendance_admin": "attendance_admin",
    "exam_officer": "exam_officer",
}

# What each role may do. The engine refuses any other action with reason "permission":
# students cannot edit attendance or approve their own exceptions.
ROLE_ACTIONS: dict[str, frozenset[str]] = {
    "student": frozenset({"attend", "skip", "submit_exception_request", "ask_advisor"}),
    "faculty": frozenset({"record_attendance", "edit_attendance", "cancel_session"}),
    "advisor": frozenset({"advise_student"}),
    "attendance_admin": frozenset({"process_exception_queue"}),
    "exam_officer": frozenset({"evaluate_eligibility"}),
}

EXAMPLE_POLICY = {
    "text": (
        "Students must maintain at least 80% attendance in each course to be "
        "eligible for examinations. Exceptional circumstances may be considered "
        "through formally approved exceptions."
    ),
    "purpose": (
        "Improve class participation, encourage consistent attendance and "
        "maintain academic standards."
    ),
    "environment": (
        "One institution and one course over a term. Students include a "
        "long-distance commuter, a resident student, a student with fixed work "
        "hours and a student with family responsibilities. Faculty, an academic "
        "advisor, an attendance administrator and an examination officer are "
        "involved. Transport disruptions happen during the term. The attendance "
        "office can process only a few exception requests a week, and "
        "eligibility is checked at a set point in the term."
    ),
}
