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
