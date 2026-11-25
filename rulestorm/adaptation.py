"""How the AI people adapted during a run (slice 19), found by rules over the run's own records.
No model call. Three kinds:

- **changed their own value** (`value_changed`): an `attribute_set` that really changed a person's
  value (for attendance, a student's travel buffer: "leaves earlier"). Its **effect** is read from
  the records that follow: an obstacle whose delay falls between the old and the new value, and the
  person's record for that occurrence. A raised buffer that let them attend despite the delay, or a
  lowered one that made them miss it, is listed with the event IDs. Setting the same value again
  (60 -> 60) is not a change.
- **did something for the first time** (`first_action`): a person's first request filed, first
  message to someone, first correction of a record.
- **changed their stated strategy** (`strategy_shift`): their own words, when the new strategy shares
  at most a third of its meaningful words with their previous one (word stems, small words left out;
  the smaller strategy's words are the base, so a reworded strategy doesn't count). Labelled AI
  interpretation: it is what they said, measured only by the words they used.
"""

import re
from typing import Any

from rulestorm.core.model import Template

FIRSTS = {
    "request_filed": "filed {a_request} for the first time",
    "message_sent": "sent a message for the first time",
    "response_given": "gave advice for the first time",
    "record_corrected": "corrected a record for the first time",
}
SHIFT_OVERLAP = 1 / 3  # calibrated 25 Nov on the demo run and L-850dd3cb
_WORD = re.compile(r"[a-z0-9%]+")
_SMALL = set("the and for with while any all this that from its into when after before about our your their "
             "them they use using via stay keep can not but".split())


def _stems(text: str) -> set[str]:
    return {w[:5] for w in _WORD.findall(text.lower()) if len(w) > 2 and w not in _SMALL}


def _overlap(a: str, b: str) -> float:
    """Shared word stems over the smaller strategy's stems: 1.0 = one says nothing new."""
    sa, sb = _stems(a), _stems(b)
    if not sa or not sb:
        return 1.0
    return len(sa & sb) / min(len(sa), len(sb))


def _where(template: Template, period: int, step: int | None) -> str:
    cal = template.calendar
    return f"{cal.period_label} {period}" + (f", {cal.step_label} {step}" if step is not None else "")


def _records(events: list[dict]) -> dict[tuple[str, str, int], tuple[str, str]]:
    """(duty, person, step) -> (final outcome, the event that set it)."""
    out = {}
    for e in events:
        for key, change in (e.get("state_change") or {}).items():
            parts = key.split(".")
            if len(parts) == 4 and parts[0] == "record":
                out[(parts[1], parts[2], int(parts[3]))] = (change["to"], e["event_id"])
    return out


def _value_changes(template: Template, events: list[dict]) -> list[dict]:
    t = template
    attributes = {a.id: a for a in t.attributes}
    duties_by_attribute = {d.obstacle_attribute: d for d in t.duties if d.obstacle_attribute}
    records = _records(events)
    missed, met = t.terms.get("duty_missed", "missed"), t.terms.get("duty_met", "met")
    changes = []
    for i, e in enumerate(events):
        if e["type"] != "attribute_set":
            continue
        for key, change in (e.get("state_change") or {}).items():
            attribute_id, _, person = key.partition(".")
            old, new = change.get("from"), change.get("to")
            if old == new or old is None or new is None or attribute_id not in attributes:
                continue
            changes.append((i, e, attribute_id, person, old, new))
    out = []
    position = {e["event_id"]: i for i, e in enumerate(events)}
    for n, (i, e, attribute_id, person, old, new) in enumerate(changes):
        attribute = attributes[attribute_id]
        duty = duties_by_attribute.get(attribute_id)
        # this change holds for records made after it, until the person's next change of the same value
        # (a delay announced earlier in the same occurrence counts: the record comes after the change)
        until = next((j for (j, _, a, p, _, _) in changes[n + 1:] if a == attribute_id and p == person), len(events))
        effects = []
        for o in events:
            if o["type"] != "obstacle" or not duty or o["payload"].get("duty") != duty.id:
                continue
            if person not in o["payload"].get("people", []) or o["step"] is None:
                continue
            delay = o["payload"].get("delay", 0)
            outcome, record_id = records.get((duty.id, person, o["step"]), (None, None))
            low, high = sorted((old, new))
            if not (low < delay <= high) or outcome is None or not (i < position.get(record_id, -1) < until):
                continue
            where = _where(template, o["period"], o["step"])
            if new > old and outcome == "met":
                effects.append({"event_ids": [o["event_id"], record_id], "text":
                                f"{where}: recorded {met} despite a delay of {delay} ({o['payload'].get('description', '')}); "
                                f"with the old {old} they would have been {missed}"})
            elif new < old and outcome == "missed":
                effects.append({"event_ids": [o["event_id"], record_id], "text":
                                f"{where}: recorded {missed} after a delay of {delay}; the old {old} would have covered it"})
        out.append({
            "kind": "value_changed", "person": person, "event_id": e["event_id"], "period": e["period"],
            "step": e["step"], "label": "recorded fact", "from": old, "to": new,
            "caused_by": e.get("caused_by", []),
            "text": f"{person} changed their {attribute.label} from {old} to {new} ({_where(template, e['period'], e['step'])})",
            "effects": effects,
        })
    return out


def _firsts(template: Template, events: list[dict]) -> list[dict]:
    request = template.terms.get("request", "request")
    a_request = ("an " if request[:1].lower() in "aeiou" else "a ") + request
    seen, out = set(), []
    for e in events:
        if e["type"] not in FIRSTS:
            continue
        who = e["payload"].get("person") if e["type"] == "request_filed" else e["actor"]
        if (who, e["type"]) in seen:
            continue
        seen.add((who, e["type"]))
        out.append({"kind": "first_action", "person": who, "event_id": e["event_id"], "period": e["period"],
                    "step": e["step"], "label": "recorded fact", "action": e["type"],
                    "text": f"{who} {FIRSTS[e['type']].format(a_request=a_request)} ({_where(template, e['period'], e['step'])})",
                    "effects": []})
    return out


def _shifts(template: Template, events: list[dict]) -> list[dict]:
    last: dict[str, tuple[str, str]] = {}
    out = []
    for e in events:
        if e["type"] != "decision":
            continue
        strategy = (e["payload"].get("strategy") or "").strip()
        if not strategy:
            continue
        who = e["actor"]
        before = last.get(who)
        last[who] = (strategy, e["event_id"])
        if before and before[0] != strategy and _overlap(before[0], strategy) <= SHIFT_OVERLAP:
            out.append({"kind": "strategy_shift", "person": who, "event_id": e["event_id"], "period": e["period"],
                        "step": e["step"], "label": "AI interpretation", "from": before[0], "to": strategy,
                        "previous_event_id": before[1],
                        "text": f"{who} changed their stated strategy ({_where(template, e['period'], e['step'])})",
                        "effects": []})
    return out


def adaptations(template: Template, events: list[dict]) -> list[dict[str, Any]]:
    """Every adaptation in a run, in run order."""
    seq = {e["event_id"]: e["seq"] for e in events}
    found = _value_changes(template, events) + _firsts(template, events) + _shifts(template, events)
    return sorted(found, key=lambda a: seq.get(a["event_id"], 0))
