# Architecture

## In one line
A policymaker types an institutional rule. RuleStorm matches it to a template, fills in the rule and its conditions as values the policymaker approves, and runs a simulated term in which AI stakeholders react to disruptions inside a general rule engine. It then shows the exact chain of recorded events behind each problem it finds.

**Re-planned 24 Nov (Level 2, team decision).** Slices 1–6c were built on a fixed attendance model, with policy rules and the cast written in code. Level 2 replaces that core with one general engine made of fixed building blocks, plus **templates written as data**. It ships two templates: attendance and a structurally different hostel curfew. The AI picks a template and fills it from the policy; the user approves.

## Pieces and data flow
Everything runs in one Python process on one EC2 instance. Arrows show the direction data moves.

    browser (UI phase: React + Vite static files served by FastAPI; screens in docs/USER_JOURNEY.md)
      └─> CloudFront (HTTPS; /api/* all methods, no cache, 60 s origin timeout)
            └─> EC2 :80  FastAPI, one uvicorn worker (systemd)
            ├─ GET  /api/templates ─> each template's id, title, scope line, example input
            ├─ GET  /api/templates/{id} ─> its terms, calendar labels, people, roles, parameter specs (U0)
            ├─ POST /api/policies ─> store (each text ≤ 2,000 chars)
            ├─ POST /api/blueprints ─> blueprint cap (atomic, else 429) ─> blueprint.interpret
            │     call 1, pick: policy texts + every template's scope line ─> {template_id | "none", reason}
            │     call 2, fill: that template's values model (built from its parameter specs)
            │     (both share one 55 s wall-clock budget) ─> check values against the template
            │     ─> status valid | invalid | out_of_scope ─> store
            ├─ GET  /api/blueprints/{id} ─> the stored record (U0)
            ├─ PATCH /api/blueprints/{id}/values {changes} ─> corrected values, checked by the template, become
            │      the policymaker's facts; refused once approved (slice 18)
            ├─ POST /api/blueprints/{id}/approve ─> store (frozen by DB trigger)
            ├─ POST /api/blueprints/{id}/variants ─> blueprint cap ─> explore (environment parameters only)
            ├─ POST /api/runs ─> one active run (409) ─> daily run cap (429) ─> runner thread
            │      runner: Model = template (data) + frozen blueprint values
            │        └─> core.Term over the template calendar, in the fixed phase order:
            │              period start: capacity disruptions, then pending-request triggers
            │              each step:    obstacles ─> triggered LLM people decide (agents.decide_phase:
            │                            prompt from template + profile, same snapshot, max 4 parallel,
            │                            call cap, 40 s deadline) ─> sorted by person ID ─> permission and
            │                            precondition check (from the Model) ─> commit ─> recorder records the duty
            │              period end:   queue processing, then checks (if due)
            │              every event: event_id, seq, period, step, type, actor, payload, state_change, caused_by[]
            │      after the last period: detect (check failed; request pending at the check) ─> findings + chain
            ├─ POST /api/runs/{id}/counterfactual ─> the run's blueprint with one environment value changed,
            │      approved ─> the same runner (409 / 429 as above)
            ├─ GET /api/runs/{id} (polled every 3 s, ?after=<seq>), /api/runs/{id}/findings
            ├─ GET /api/runs/{a}/compare/{b} ─> queue length, waiting time and checks for both runs
            ├─ GET /api/runs/{id}/adaptations ─> value changes and their effect, first actions, strategy shifts (slice 19)
            ├─ POST /api/comparisons {blueprint_id} ─> Bedrock (strict / flexible / progressive policy values)
            │      ─> 3 approved blueprints, run one after another in the background (slice 15)
            ├─ GET /api/comparisons/{id} ─> progress, then a trade-off table per version (no score)
            ├─ POST /api/blueprints/{id}/search {max_runs} ─> rounds of 2 Bedrock-targeted + 1 random scenario,
            │      each round told how close the last runs came; a break must repeat on a rerun (slice 16)
            ├─ GET /api/searches/{id} ─> rounds, closeness per run, result (broken / not_broken + closest)
            ├─ POST /api/blueprints/{id}/repeats {times, include_run} ─> the same blueprint run again, in turn (slice 21)
            ├─ GET /api/repeats/{id} ─> per person failed X of N, findings per run, each measure's spread
            └─ GET /api/findings/{id}/evidence ─> ordered steps, labels in the template's own terms
    CLI: python -m rulestorm.cli <command> calls the same core functions as each route.
    On startup: any run still marked running → failed (interrupted).

**Modules** (in `rulestorm/`):

| Module | What it holds |
|---|---|
| `core/model.py` | The building-block schema (Pydantic) and the **template check**: schema, references, known effects and preconditions, plus a dry run with a scripted decider |
| `core/engine.py` | State, actions, permissions, preconditions, duties, request queues, counts, checks and the event log, all driven by the Model. No policy rule and no domain word in code |
| `core/term.py` | The calendar loop in the fixed phase order, disruptions, triggers |
| `templates/attendance.json`, `templates/hostel_curfew.json` | The two templates: building-block definitions, parameter specs, terms, scope line, example input, version |
| `blueprint.py` (from `policy.py`) | Policy input, the two-call interpret (pick, then fill), the per-template values model, approval |
| `llm.py` | Model adapter: Bedrock Converse and a scripted fake |
| `agents.py` | LLM people: prompts generated from the template (with the 6b fixes kept), memory, strategy, cap, deadline, run summary |
| `explore.py` | Stress variants on the template's `environment` parameters, with the counting and queue maths in the prompt; `hunt` (slice H) runs the approved variants, then the parent, until a run has a finding |
| `detect.py`, `evidence.py` | General detectors and the evidence view (slices 8–9) |
| `counterfactual.py` | One-change reruns and the two-run comparison (slice 13) |
| `rulebook.py` | The "How the rules work" block every person's prompt carries, generated from the template and the blueprint's values: when each check runs and that it is final, how many misses fail it, what doing nothing means, how delays and personal clashes work, which absences are a valid exception, how requests queue, and the last step that can't be excused in time (26 Nov, demo fix) |
| `repeats.py` | Repeated runs of one blueprint, summarised as how often each person fails, each finding appears and each measure's spread (slice 21) |
| `adaptation.py` | How the AI people adapted, by rules over a run's records: a real change to their own value and the later records it changed, first actions, stated-strategy shifts (slice 19) |
| `editing.py` | Corrects single values and per-person values of an unapproved blueprint; each correction becomes a fact (slice 18) |
| `search.py` | Guided scenario search: closeness from each run's records, random scenarios within the template's ranges, rounds that push the closest weak point, a confirming rerun (slice 16) |
| `comparison.py` | Strict, flexible and progressive policy versions under the same environment and people, run in turn, compared as a trade-off table (slice 15) |
| `telemetry.py` | One CloudWatch embedded-metric log line per finished run: `LLMCalls`, `Tokens`, `RunDurationSeconds` (slice 14) |
| `catalog.py` | A template's display words, labels and parameter specs for the screens (slice U0); only shipped template IDs can be named |
| `fixture.py` | Export a finished run and restore it as run `demo` (slice 10) |
| `store.py`, `runner.py`, `api.py`, `cli.py` | Storage (SQLite), background runs, routes, terminal commands |
| `fixtures/demo_run.json` | The seeded demo run on the new format, with a schema version |
| `deploy/deploy.sh`, `deploy/rulestorm.service`, `deploy/rulestorm.env` | The deploy script, the systemd unit and the server's settings template (slice 11; steps in docs/DEPLOY.md) |

The old `engine.py`, `simulation.py` and `education.py` were deleted at the switch-over (L7, 24 Nov); the old engine stays at git tag `pre-level2`.

## The building blocks (fixed in code, `rulestorm/core/`)
A template may only use these. Anything outside them needs new engine code, by design.

| Block | Shape | Engine behaviour |
|---|---|---|
| **Calendar** | number of periods (e.g. weeks), steps per period (sessions / nights), labels, and a **fixed phase order**: period start (capacity disruptions, then pending-request triggers) → each step (obstacles → decisions, including endorsements (the consenting people are asked again, in a short phase of their own, about requests filed in that step: added in L9d) → requests with `processed: each_step` → recording) → period end (requests with `processed: period_end` → checks) | Steps through time in exactly that order. For attendance it is today's order, which decides "pending at the checkpoint"; for curfew it means a permission is filed, consented to and decided before that night is recorded |
| **Role** | id, label, `llm: bool` plus `rules: [recorder / queue_processor / checker]` (a role may be both, like faculty: an LLM that also records attendance), allowed action IDs | LLM roles decide when triggered, and their prompt lists only their allowed actions. Rules aren't actions: they run automatically at their phase and are never offered to an LLM |
| **Person** | id, role, label; profile (description, at most 2 goals, at most 2 constraints) and numeric attributes, from the blueprint | Holds memory, strategy and attribute values |
| **Attribute** | id, label, range, which role has it (e.g. `slack_min`) | Read by obstacle rules; changed only by an action with a `set_attribute` effect |
| **Duty** | id, label, owed by role, each step, the actions that plan to meet or miss it, `recorded_by` role, obstacle rule (`delay > attribute` means missed) | Creates each occurrence. **Recording is not an action:** at the recording phase the recorder rule records met or missed for everyone, applying each person's plan and any obstacle, with `caused_by`. A person with no plan is treated as planning to meet it |
| **Action** | id, label, allowed roles, parameters, one or more effects from a fixed library (`plan_meet, plan_miss, set_attribute, file_request, endorse, decide_request, message, respond, correct_record, cancel_occurrence`), preconditions from a fixed list (`own_occurrence`, `occurrence_recorded`, `occurrence_not_yet`, `not_already_covered`, …). `plan_meet` and `plan_miss` only record the person's plan for an upcoming occurrence; the outcome comes at recording. Example: `attend` = `plan_meet` plus an optional `set_attribute` on `slack_min` (today's "change your travel buffer") | Refuses anything not allowed (an `action_rejected` event with the reason code and a plain `detail`) and commits the rest. The engine writes the detail itself from the fixed reason library and the template's labels (for example "session 5 had not been recorded yet when you sent this"); templates hold no refusal sentences, and the person's prompt shows the detail, not the code |
| **Request type** | id, label, filed by, covers a duty, handled by a role, `processed: each_step / period_end` | see the three rows below |
| | **Consent:** optional `endorsed_by` role (the request first needs that role's consent; refused consent ends it) | A request filed with consent pending is not queued. The endorse action takes one `request` and one `bool` parameter, and only the `endorsed_by` role may take it (template check). It records `request_endorsed`, or `request_endorsement_refused`, which sets the request to rejected (its occurrences still count as missed) |
| | **Who decides:** `decided_by: rule / llm`. A rule applies the decision rule; an LLM role decides each queued request within capacity, with a reason, while the engine still enforces capacity, order and the allowed outcomes | LLM slot (built in L9b): `decision_awaiting` offers the requests within capacity, first come first served, and only the handled_by people are asked, in a phase of their own; their prompt lists the offered requests and the allowed outcomes (`approved`, `rejected`; some steps only if `partial_at_decide`). The decide action takes one `request` and one `outcome` parameter (plus an optional step list), and only the handled_by role may take it. Refused: a request not offered (`capacity`), decided twice, outside the slot, or an outcome not in the list. When the slot closes, offered requests nobody decided (no action or a failed call) stay pending as `decision_not_made`, and those beyond capacity as `queue_over_capacity` |
| | **Decision rule** from a fixed list (`approve_if_covered_missed`, `approve_if_filed_before_occurrence`, `approve_all`). **Policy parameters:** `timing: after_missed / in_advance`; `partial_at_submit: bool` (accept the valid occurrences, drop the rest, instead of refusing the whole request); `partial_at_decide: bool` (approve the qualifying occurrences instead of rejecting the whole request) | First come, first served within capacity per processing slot; `queue_over_capacity` holds the rest |
| **Count** | id, label, `rate` (met ÷ due, excluding listed statuses: `approved_request`, `cancelled`; pending counts as missed) or `tally` (number missed, excluding approved) | Recomputed on demand, always from records |
| **Check** | id, label, run by a checker role, count, comparison (`>=` / `<=`), and **either** one threshold at one timing parameter **or** an **escalation ladder** checked every period (an ordered list of threshold → outcome, each a blueprint parameter) | Records `check_evaluated` with both figures (as is, and if pending requests were approved). An escalation outcome is an event that can trigger listed roles. A ladder step is reached once the count no longer passes that step's threshold, by the same `engine.passes` a single check uses; comparisons are `>=`, `<=`, `>`, `<`, so a tally `<` 2 reaches its step at 2. Each step a person newly reaches is one `check_evaluated` (with `outcome`, `ladder_step`), recorded in ladder order even when several are reached at once; its `passed` is false only at the last step (built in L9a). A ladder period with no new step records where the person stands (`standing`, `ladder_step`, no `outcome`, so it notifies nobody) only if a request for an occurrence already recorded is still pending, so a wait before any penalty is visible at the check (added after slice 8) |
| **Disruption kind** | `obstacle` (delay on a duty for listed people, at an explicit list of steps in its period), `capacity` (queue capacity override in a period), `cancellation` (listed occurrences cancelled) | Applied at its phase, recorded as an event |
| **Trigger** | from today's five: an obstacle hits a person; a person's own duty is missed; a count comes within N of the threshold (plus listed roles); a request has been pending ≥ N periods (plus listed roles); ≥ K people missed in one step (to a listed role). Also, for the new blocks: a request awaiting consent reaches its `endorsed_by` person; a request awaiting an LLM decision reaches its `decided_by` person at its processing slot; an escalation outcome reaches its listed roles; **a message or response reaches the person it is for** (`message_received`, at most once per person per period, so two people can't chat every step; added 24 Nov after L7) | Decides who is asked in each phase. Each template chooses which triggers it uses: attendance uses today's five plus `message_received`, so the advisor's advice reaches the student (real runs after the change: 15 and 9 decisions, 18 and 11 calls on the 6b scenario, against 6b's 13 and 14–17). No other new triggers |
| **Parameter spec** | name, type, range, `kind: policy / environment / people`, a sentence template for prompts | What the blueprint must fill. Variants vary only `environment`; the three-policy comparison varies only `policy` |

**General-feature rule (24 Nov):**
- A block or engine feature is added only if a second template could use it.
- Template-specific words, labels and sentences live in the template, never in `core/` or `prompts.py`. Parameter sentences may name other parameters' values; that's general formatting, kept.
- Tests prove behaviour and numbers exactly, not one template's old wording.
- The test-case loader for `engine check --case` moves out of `core/engine.py` and gets a general case format in L9c.

**Causality rules (general forms of the ones slices 4–5 proved):**
- Every decision records `caused_by=[its trigger]`, and every action it produces records `caused_by=[decision_id]`.
- A missed occurrence caused by an obstacle records `caused_by=[disruption_id, decision_id]`.
- A request records the occurrences it covers; an endorsement and a decision record the request.
- `queue_over_capacity` records the requests it holds.
- A check records its count and the pending requests.
- Detectors follow a person's own path of links from a check back to the root disruption, not every ancestor (slice 5 gotcha, IDEAS.md), and store the ordered chain on the finding.
- **Hunt (built in slice H):** `explore hunt <id> --max-runs N` runs each approved variant, then the parent, again from the first while runs are left, through `runner.run_now`: the background runner's path in the foreground, so each run is saved with its findings, takes the daily caps and can be opened by ID. It stops at the first run with a finding, a failed run, or the daily run cap.
- **Evidence (built in slice 9, `evidence.py`):** `GET /api/findings/{id}/evidence` returns the finding's chain as steps in run order, each with `event_id`, period and step, `state_change` (empty when the event changed nothing), a sentence and a label. Labels: `AI interpretation` for a person's decision (with their own reason in `interpretation`); `calculated` for rule work (queues, decision slots, counts, checks, and a request decided by a rule); `recorded fact` for everything else. Sentences are general patterns filled with the template's terms and labels; `evidence.py` holds no template word (tested). The check step's `calculation` recomputes the count from the run's events before the check (records and corrections, cancellations, requests and their decisions), as it stood and with pending requests approved, and says whether that matches the figures the check recorded. Templates are cached per process, so an answer takes about 0.01 s.
- **Detectors (built in slice 8, `detect.py`):** `check_failed` is a `check_evaluated` with `passed` false (on a ladder, its last step); `pending_at_check` is one with pending requests. One finding of each kind per person and check, the first. The chain follows `caused_by` back from the check, but never through an event about another person who owes the template's duty (as actor, `person`, a `people` list without them, or a request of theirs); events about nobody in particular (a disruption, a queue that held the request) stay. It is stored in run order, so it starts at the disruption when one hit them and ends at the check. Titles come from the template's terms `finding_check_failed` and `finding_pending_at_check`. Finding IDs are `<run_id>-F<n>`. The runner saves findings before marking a run finished; `GET /api/runs/{id}/findings` works them out on first use for a run that ended before slice 8. The case runner's failed-check chain uses the same detector.

## Templates (data, `rulestorm/templates/`)
Each file carries `id`, `version`, a scope line, terms (display words), building-block definitions, parameter specs and its example input. The template check runs in pytest for every file. It is the slim, template-only form of the Brief's 4-stage validation (nice-to-have 8).

**attendance@1** is a port of today's model:
- **Calendar and people:** 10 weeks × 2 sessions. 5 roles, 8 people: commuter, resident, working and family students (LLM), faculty (LLM, plus the recorder rule), advisor (LLM), attendance office (queue processor rule), exam officer (checker rule).
- **Duty, request, count, check:** duty attend class; request exception; count attendance % (rate); check exam eligibility (attendance ≥ threshold, once, at the checkpoint week).
- **Actions (7, today's LLM actions):** students `attend`, `skip`, `submit_exception_request`, `ask_advisor`; faculty `edit_attendance`, `cancel_session`; advisor `advise_student`. Today's `record_attendance` (faculty), `process_exception_queue` (attendance office) and `evaluate_eligibility` (exam officer) aren't actions any more: they're the recorder, queue processor and checker rules.
- **Parameter kinds:**
  - `policy`: threshold, scope, request timing, partial at submit, partial at decide, decision rule;
  - `environment`: office capacity per week, checkpoint week, disruptions (as slice 6c varied them; the early-checkpoint variant is the one that broke);
  - `people`: the 8 profiles and each student's `slack_min`.
- **Example input:** the 80% example stays the pre-filled default.

**hostel_curfew@1** is a different structure, not a renamed copy (team ask, 24 Nov):

| | attendance@1 | hostel_curfew@1 |
|---|---|---|
| People | 8: 4 students + 4 staff | **10: 6 residents + guardian + warden + security + discipline committee** |
| Calendar | 10 weeks × 2 sessions | **8 weeks × 5 nights** |
| Who records the duty | faculty (an LLM that also records) | **security (rule only)** |
| Request flow | student → office queue → rule decides | **resident → guardian must consent (LLM) → warden decides each request (LLM, within a nightly capacity)**, filed in advance, decided before the night |
| Count and rule | attendance % (rate) ≥ threshold, once, at the checkpoint | **late returns (tally), checked every week on an escalation ladder:** warning → guardian informed → disciplinary |
| Who reacts to outcomes | advisor (near the threshold) | **guardian, triggered by "guardian informed"** |
| Disruptions | transport, office capacity | transport delay and lab overrun (obstacles, on chosen nights), warden away (capacity) |

Residents' labels and profiles come from the blueprint. Its actions:
- residents: `return_on_time` (`plan_meet`), `stay_out_late` (`plan_miss`), `request_late_entry` (`file_request`, in advance);
- guardian: `give_consent` (`endorse`) and `talk_to_resident` (`respond`);
- warden: `decide_permission` (`decide_request`), at the queue's nightly slot.

Security (the recorder) and the discipline committee (the checker) are rules. Built in L9c: there is no welfare officer, so the cast stays at 10, and the guardian's `talk_to_resident` carries advice.

Parameter kinds:
- `policy`: curfew time, the ladder thresholds, request timing, partial acceptance;
- `environment`: the warden's capacity per night (a queue processed each step has its capacity per slot), disruptions;
- `people`: the 10 profiles and each resident's `slack_min`.

The template has its own pre-filled example policy (for example: "Residents must return by 10 pm; late entry needs prior permission from the warden with guardian consent; repeated late returns lead to disciplinary action").

## Blueprint (template + values)
- **Shape:** `Blueprint = {template_id, template_version, values, facts, assumptions}`. `values` holds policy parameters, people (profile + attributes), capacities, check timing or ladder thresholds, and disruptions. Each is checked against the template's parameter specs and references; for example, a disruption's affected people must exist.
- **Two calls, always:**
  1. **Pick:** the policy texts plus every template's scope line. The reply is `template_id` or `"none"` with a reason (`max_tokens` about 100, a few seconds). `none` gives `status: out_of_scope`.
  2. **Fill:** that template's own Pydantic values model, built from its parameter specs.

  Both share the 55 s wall-clock budget. The pick is shown on the review screen as one more labelled assumption.
- **Labels and size:** labels are grouped by section (policy rules, people, environment) so the lists stay short. Profiles are short on purpose (a description under 12 words, at most 2 goals and 2 constraints of under 6 words), so a fill with 8 people stays near 900 output tokens. The fill's `max_tokens` is set from a measured p95.
- **Silent policy rules:** when the policy text doesn't say (for example, whether exceptions can be requested in advance), the AI proposes a value and labels it an **assumption**. This is how "after the absence only" stops being hard-coded.
- **Spend guard:** blueprint and variant calls take the `blueprint_calls` daily cap atomically before calling Bedrock (HTTP 429 when it's used up).
- **Broken runs (built in 7b):** at server start, a run still marked `running` was cut off by a restart and becomes `failed` ("Interrupted: the server stopped while the run was going"). A failed run's GET shows only the error's class and a short message (at most 120 characters); ARNs, 12-digit account IDs and access key IDs are replaced, in run errors and in model errors recorded in decisions. The full error goes to the server log only.
- **Demo:** it never needs a live blueprint call; the fixture bundles its approved blueprint.

**Where values come from (team rule, 24 Nov, unchanged):**
- Every number, rule and event a run uses comes from the user's input or an AI assumption the user approves, frozen with the blueprint.
- The code holds only the building blocks.
- The templates hold structure (who exists, what they may do, what is counted and checked), never scenario numbers.
- The pre-filled example inputs are ordinary, editable user input.

**Hero chain from real runs:** nothing in code or a template is changed to make a finding appear. The demo replays a recorded real run (must-have 9). The hero is whichever real finding is strongest at the 26 Nov checkpoint (team choice). Chosen 25 Nov: the eligibility failure in L-ff6f0ca8 (`check_failed`, the working student at 72.7% after storms), bundled in `fixtures/demo_run.json` and restored as run `demo` with `reset-demo`, which re-detects the findings from the bundled events and refuses a file whose blueprint no longer fits its template.

## What carries over and what is ported
- **Unchanged:**
  - `llm.py` (adapter, 55 s wall-clock budget);
  - `store.py` (tables unchanged; records store `template_id@version`);
  - the API routes and CLI shape;
  - the agent framework (`CallBudget`, `CappedModel`, parallel phases, deadline, degraded status);
  - the runner (7a, built 24 Nov: `runner.py`, one run at a time, events saved each period, the run file written at the end as `run local` writes it) and the caps (7b, built 24 Nov), deploy, and the UI plan.
- **Ported in its own slice:**
  - **Agent prompts:** generated from the template, keeping the 6b fixes (the slack line, the absences no request covers, the outcomes of the person's last actions). A golden-prompt test (built in L5 as an exact copy) is narrowed at the switch-over (L7): an exact match only for the lines carrying the 6b fixes, and the same facts (not the same wording) for the rest. That keeps one template's old wording from shaping the engine.
    Added on the general engine (L9b–L9d): a "Now:" line naming the current step, with the step on every event line; each person's own requests with the steps they cover and what became of them; for a consenting person, the requests waiting for their consent; for an LLM decider at an open slot, the offered requests and the allowed outcomes; and the number of actions they may propose.
  - **`explore.py`:** reads the template's terms and event types, and its prompt gains the queue maths and a general **misses until the check fails** figure (from the count kind, threshold and check timing), which replaces the attendance-only `absences_to_fall_below`.
- **Built on the general model from the start:** detectors (slice 8) and evidence (slice 9), both done.
- **Switch-over rule:** the old engine is deleted only after a real attendance run on `core/` matches 6b. That means decisions only for triggered people, similar counts (about 13 decisions, 14–17 calls) and no new kinds of rejection reason.
- **Go/no-go on 25 Nov at 15:00:** if there's no match, fall back to "Level 1.5": add request timing and partial acceptance to today's engine, and move curfew to after the UI. The fallback code is at git tag `pre-level2` (commit `189ac53`).
- Old blueprints and run logs aren't migrated (dev data only).

## Model adapter contract
`decide(prompt, schema) -> schema instance`. Unchanged:
- **JSON and validation:** JSON in the prompt, written compactly on one line (asked for since 24 Nov: pretty-printed replies were 40% whitespace and took a curfew fill to 40–44 s; now 28.9–30.0 s), Pydantic validation, one retry with the error included. A fill's retry still only just fits the 55 s budget: after a 30 s first try about 25 s remain, and a fill takes about 27 s.
- **Timeouts:** adaptive boto retries, `connect_timeout=5`. Agent calls use `read_timeout` 25 s and get up to 5 attempts. Each decision phase has a 40 s deadline; calls unfinished then are timeout "no actions".
- **Blueprint calls:** no boto retries, at most 2 attempts per call, and all calls share one 55 s wall-clock budget (each attempt runs in a background thread and is abandoned at the deadline). A retry is skipped if under 15 s remain.
- **Actions per decision:** 0 to 3, or one per request waiting for that person (to consent to, or to decide at an open slot) if more; the reply's token limit grows by 80 for each action above 3 (added in L9d, after a guardian with four requests could consent to only three).
- **Run status:** `llm_errors` and `cap_hits` are counted; a run ends `degraded` when more than 10% of its decisions were error no-actions or the cap stopped it.
- **Fake model:** `RULESTORM_MODEL=fake` is for automated tests only (`RULESTORM_ENV=test`).

## Store tables
SQLite, WAL mode, one connection per thread:

| Table | Fields |
|---|---|
| policies | the stored policy texts |
| blueprints | template id + version, values, facts, assumptions, status, approved, parent_id (stress variants), counterfactual_of (slice 13 reruns, kept apart so they never count as variants), comparison_of (slice 15 policy versions; `variant` names which), search_of (slice 16 search scenarios) |
| searches | blueprint id, status, record (rounds, scenarios, runs with closeness, result) (slice 16) |
| comparisons | blueprint id, status, record (versions with their blueprint and run, kept values, progress) (slice 15) |
| runs | status (running / completed / degraded / failed), period and periods, template, model ID, blueprint ID, summary (decisions, calls, llm_errors, cap_hits, tokens), error, started and finished times. A new run is inserted only if none is running, in one statement (built in 7a) |
| events | run_id, seq, and the whole event (event_id, period, step, type, actor, payload, state_change, caused_by), saved after each period so the timeline can be followed live |
| decisions | person, prompt hash, raw reply, parsed decision, accepted/rejected + reason, error |
| findings | id (`<run_id>-F<n>`), run_id, kind, and the whole finding (title, person, check, the count as is and if pending approved, pending requests, disruptions, chain) (built in slice 8) |
| daily_usage | date, runs, llm_calls, blueprint_calls |

Caps are taken atomically: `UPDATE … SET n = n + 1 WHERE date = ? AND n < cap`; rowcount 0 means over the cap.

## Decisions
| Decision | Choice | Why (from the user's problem) | Fallback if it fails |
|---|---|---|---|
| Generality | Level 2: fixed building blocks + templates as data (team choice, 24 Nov) | Policy rules in code contradict the product: a policymaker's rule must change the simulation without code | Level 1.5 on the old engine (tag `pre-level2`), decided at the 25 Nov 15:00 gate |
| Second template | Hostel curfew, with a different structure: 10 people, consent step, LLM-decided requests, escalation ladder (team choice) | Shows the engine is general, not renamed; a debated rule in Indian colleges | Ship attendance only; curfew after the UI |
| Template pick | The AI picks in the first of two blueprint calls; the user confirms on the review screen (team choice) | No extra step for a non-technical user; the scope guard stops wrong models | The user picks from `GET /api/templates` |
| Template authoring | Written by us, checked by the template check in pytest | Level 2 trusts tested templates; AI-written templates are Level 3 | A template bug found in a real run is fixed in the file and its version is raised; blueprints keep the version they were made with |
| Rule-run roles | A fixed library: recorder, queue processor, checker | Keeps the queue and check steps exact and free of LLM calls | Where a role needs judgement, `decided_by: llm` (slice L9b) |
| Language and API | Python 3.12 + FastAPI + Pydantic + boto3 | The spec's stack; Pydantic checks every blueprint and decision | — |
| UI | React + Vite + Tailwind, built on a laptop, `web/dist` committed and served by FastAPI (team choice); screens, calls and states in docs/USER_JOURNEY.md | Interactive timeline and evidence views; no Node on EC2 | FastAPI templates + plain JS for the hero screens |
| AI model | DeepSeek V3.2 (`deepseek.v3.2`) on Bedrock Converse, in-Region Sydney, for the blueprint and agent decisions (team choice after the day-0 smoke test) | Fast and steady on our account; the Free plan blocks cross-Region | Qwen3 235B (a config change) |
| Search over documents | No | The input is one short policy text | — |
| Background runs | A thread in the single uvicorn process, one active run at a time, progress in the store, the UI polls | Must-have 6; judges may start a run themselves | SQS worker (nice-to-have 14) |
| Parallel calls | Triggered people in one phase are called in parallel (max 4), on the same snapshot, with proposals sorted by person ID | Faster runs, and results don't depend on thread timing | Sequential calls |
| Storage | SQLite on the instance's EBS disk, one Storage interface, the same backend in tests | Evidence chains are relational; no free-tier capacity limits | A JSON file per run |
| Demo data | `fixtures/demo_run.json`: one real, `completed` Bedrock run on the new format, bundling its policy and approved blueprint, with a schema version and a test. Recorded by 28 Nov noon | The demo reaches the hero moment without waiting, and replays what really happened | Keep doing real runs; never a hand-made run |
| Spend guard | Per-run call cap, plus daily caps on runs, LLM calls and blueprint calls, all atomic; settings in `/etc/rulestorm.env` and `.env` (defaults: 150 calls a run; 20 runs, 2,000 calls and 50 blueprint requests a day; 0 means none). Over a cap → 429; one active run → 409, checked first so a refused duplicate costs nothing. A run stopped by the daily call cap ends `degraded` (built in 7b) | Credit exhaustion suspends the live account | Budgets alert email |
| Hosting | One EC2 t3.small (standard CPU credits), Ubuntu 26.04 LTS with Python 3.14 (built 25 Nov; 24.04 was the plan), ap-southeast-2, Elastic IP, systemd on port 80, IAM instance role, Session Manager | The PS needs a live AWS link | — |
| HTTPS link | CloudFront (built 25 Nov: https://d2emiyaz9dq4bi.cloudfront.net, E1IG4DB09R82EC), origin = the EC2 public DNS name; `/api/*` all methods, CachingDisabled + AllViewer, 60 s origin timeout | Browsers warn on plain HTTP | Submit `http://<elastic-ip>` |
| Setup and deploy | One-time console checklist (`docs/DEPLOY.md`, Budgets alert first); `deploy/deploy.sh <tag>` in a Session Manager shell, which also runs `reset-demo` so the demo run exists on a fresh instance | Least setup on a new account; the hero path must work on the live link | Tarball through Session Manager |
| Monitoring | EC2 status-check alarm → SNS email | We must know if the judged link dies | Check `/api/health` by hand |

## Speed target
- **Hero moment:** opening a stored run, its findings and a finding's evidence each answer in under 1 second.
- **Blueprint:** under 30 s typical (pick about 3 s, fill about 22–27 s; measured 24 Nov: curfew 28.9–30.0 s, attendance 24.7 s), 55 s hard limit, with a progress message.
- **Fresh run:** progress within 5 s, updates every 3 s. A whole run under 5 min (attendance measured at 20–54 s; curfew at 34–62 s with 19–23 calls, L9d).

## Settled questions
- **Level 2 (24 Nov):** chosen over Level 1. Generality comes from fixed building blocks plus templates as data. AI-drafted templates (Level 3) aren't in this build.
- **Templates:** attendance (ported) and hostel curfew (a different structure). The AI picks, the user confirms.
- **Hero:** chosen 25 Nov: the eligibility failure `demo-F1` (from L-ff6f0ca8), restored as run `demo` on every deploy.
- **Go/no-go:** 25 Nov at 15:00, with Level 1.5 as the fallback.
- **Old data:** old blueprints and run logs aren't migrated.
- **Scope:** both templates are education-institution policies, so "no domains other than education" stays.
- **Build hours:** slices so far took about 10–30 minutes each. The UI phase starts on the morning of 28 Nov whatever is done; the last deploy is 29 Nov.
- **LLM and rule roles:** LLM people decide only when triggered. Rule roles (recorder, queue processor, checker) are code from the fixed library. All people appear in the simulation.
- **Fake model:** tests only, never in the app or the demo.
- **Example inputs:** they stay descriptive. The AI proposes numbers as assumptions and the user approves them.
- **Region:** ap-southeast-2 (Sydney), fixed by the account. No Claude model runs in-Region there.
- **Global caps:** live in `/etc/rulestorm.env`, not Parameter Store.
- **Counterfactual (slice 13, 25 Nov):** `counterfactual.py` copies a run's blueprint with one single-value `environment` parameter changed (a list such as `disruptions` can't be changed this way), labels it a fact, approves it and starts its run through the normal runner (409 and the daily caps apply). It is stored with `counterfactual_of`, not `parent_id`, so `explore run` and `hunt` never pick it up. `GET /api/runs/{a}/compare/{b}` reads both runs' events: longest queue and periods over capacity, waiting time from `request_decided.waited_periods`, and every check result; it lists every value the blueprints differ in and says `matched` only when that is one environment value.
- **Live account (25 Nov, team decision):** our one current account is the live account, and development stays in it too, so the live caps are lower than the code's defaults (10 runs and 1,000 model calls a day, in `deploy/rulestorm.env`). It had USD 100 of credits on 25 Nov; the server, address and disk take about USD 18 up to 17 Dec. Bedrock was already called here during development, so the Budgets alert comes before the first deploy rather than before the first Bedrock call. The deploy (`deploy/deploy.sh`, `deploy/rulestorm.service`, `docs/DEPLOY.md`) installs a git tag into `/opt/rulestorm/releases/<tag>`, keeps the store in `/var/lib/rulestorm`, and runs the app as user `rulestorm` on port 80 with only `CAP_NET_BIND_SERVICE`.
- **Earlier team decisions (BRIEF):** no Streamlit, Vercel or Supabase; SQLite, not DynamoDB; 2–3 AWS accounts (one live); link shared with the team and judges only, no login; deploy freeze 30 Nov–5 Dec.

## Not doing
- **Everything in BRIEF "Not doing":** no Streamlit; no S3, ECR, Lambda, API Gateway, Cognito or load balancers; no DynamoDB store; no login; no AWS Organizations; no model training; no claims of real-world prediction.
- **Templates:** no AI-written templates, no template editor, no domains outside education, no building blocks beyond the table above.
- **Explanations:** no LLM-written finding explanations. The "AI interpretation" label shows the agents' own stated reasons.
- **AWS setup:** no scripted account setup (CLI or IaC), no deploy key, no Node on the instance, no Parameter Store.
- **Server:** one uvicorn worker, one active run at a time; no websockets or server-sent events, so the UI polls.
- **Libraries:** no Pandas or Plotly until a nice-to-have needs them.

## Critic findings rejected
- **"Make blueprint generation asynchronous":** rejected. The blueprint calls share one 55 s wall-clock budget inside CloudFront's 60 s, so a sync request is enough.
- **"Don't do Level 2 now; do Level 1.5 and move curfew to after the UI" (Level 2 critique, Fatal #1):** rejected. Level 2 is the team's decision. The risk is handled by building alongside the old engine, the 25 Nov 15:00 go/no-go gate and Level 1.5 as the fallback. Its hero advice (put the queue maths in the variants prompt) is adopted.
