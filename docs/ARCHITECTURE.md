# Architecture

## In one line
A policymaker types an institutional rule. RuleStorm matches it to a template, fills in the rule and its conditions as values the policymaker approves, and runs a simulated term in which AI stakeholders react to disruptions inside a general rule engine. It then shows the exact chain of recorded events behind each problem it finds.

**Re-planned 24 Nov (Level 2, team decision).** Slices 1–6c were built on a fixed attendance model, with policy rules and the cast written in code. Level 2 replaces that core with one general engine made of fixed building blocks, plus **templates written as data**. It ships two templates: attendance and a structurally different hostel curfew. The AI picks a template and fills it from the policy; the user approves.

**Model change, 26 Nov evening (team decision; slices M0–M11).** Every failure so far was either planted (stress conditions piled on until the arithmetic forced one) or random (an AI person's mistake). The cause was structural, and the same in both templates:
- following the rule cost nothing;
- hardships happened once;
- the exception process had no friction except a queue number;
- results were only pass/fail;
- the readings that decide outcomes were hidden.

The change adds, on both templates:
- competing obligations with stakes on both sides;
- recurring disruptions;
- the template's readings as visible, changeable policy parameters;
- an engine-checked claim of cause, plus each person's current situation in their prompt;
- a per-run ledger of who carried the rule;
- a cause class on every harm.

See "Model change (M slices)" below.

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
            ├─ GET /api/runs/{id}/ledger ─> per person: margin to each check, absences by kind, requests, obligations,
            │      AI-mistake counts; per finding its harm flag and cause class (slice M3, M9)
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
| `fixture.py` | Export a finished run and restore it as run `demo` (slice 10); from M3 the hero is found by (kind, person, check), not by its position |
| `ledger.py` | Who carried the rule, by rules over a run's records, no AI call: per person the margin to every check (every ladder step too), absences excused, unexcused and pending, requests filed, refused, rejected and waited, obligations missed and lost, AI-mistake counts. `search.closeness` is a thin wrapper over it (slice M3) |
| `evaluation.py` | The pre-registered evaluation report over a repeat: AI-mistake rate, a ledger per run, the cause class of every harm, calls per run, and sampled decisions to read (slice M10; protocol in docs/EVALUATION.md) |
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
| **Person** | id, role, label; profile (description, at most 2 goals, at most 2 constraints) and numeric attributes, from the blueprint | Holds memory, strategy and attribute values; from M7c a `PersonState` recomputed from the records (see Person state) |
| **Attribute** | id, label, range, which role has it (e.g. `slack_min`) | Read by obstacle rules; changed only by an action with a `set_attribute` effect |
| **Duty** | id, label, owed by role, each step, the actions that plan to meet or miss it, `recorded_by` role, obstacle rule (`delay > attribute` means missed) | Creates each occurrence. **Recording is not an action:** at the recording phase the recorder rule records met or missed for everyone, applying each person's plan and any obstacle, with `caused_by`. A person with no plan is treated as planning to meet it |
| **Action** | id, label, allowed roles, parameters, one or more effects from a fixed library (`plan_meet, plan_miss, set_attribute, file_request, endorse, decide_request, message, respond, correct_record, cancel_occurrence`), preconditions from a fixed list (`own_occurrence`, `occurrence_recorded`, `occurrence_not_yet`, `not_already_covered`, …). `plan_meet` and `plan_miss` only record the person's plan for an upcoming occurrence; the outcome comes at recording. Example: `attend` = `plan_meet` plus an optional `set_attribute` on `slack_min` (today's "change your travel buffer") | Refuses anything not allowed (an `action_rejected` event with the reason code and a plain `detail`) and commits the rest. The engine writes the detail itself from the fixed reason library and the template's labels (for example "session 5 had not been recorded yet when you sent this"); templates hold no refusal sentences, and the person's prompt shows the detail, not the code |
| **Request type** | id, label, filed by, covers a duty, handled by a role, `processed: each_step / period_end` | see the three rows below |
| | **Consent:** optional `endorsed_by` role (the request first needs that role's consent; refused consent ends it) | A request filed with consent pending is not queued. The endorse action takes one `request` and one `bool` parameter, and only the `endorsed_by` role may take it (template check). It records `request_endorsed`, or `request_endorsement_refused`, which sets the request to rejected (its occurrences still count as missed) |
| | **Who decides:** `decided_by: rule / llm`. A rule applies the decision rule; an LLM role decides each queued request within capacity, with a reason, while the engine still enforces capacity, order and the allowed outcomes | LLM slot (built in L9b): `decision_awaiting` offers the requests within capacity, first come first served, and only the handled_by people are asked, in a phase of their own; their prompt lists the offered requests and the allowed outcomes (`approved`, `rejected`; some steps only if `partial_at_decide`). The decide action takes one `request` and one `outcome` parameter (plus an optional step list), and only the handled_by role may take it. Refused: a request not offered (`capacity`), decided twice, outside the slot, or an outcome not in the list. When the slot closes, offered requests nobody decided (no action or a failed call) stay pending as `decision_not_made`, and those beyond capacity as `queue_over_capacity` |
| | **Decision rule** from a fixed list (`approve_if_covered_missed`, `approve_if_filed_before_occurrence`, `approve_all`). **Policy parameters:** `timing: after_missed / in_advance`; `partial_at_submit: bool` (accept the valid occurrences, drop the rest, instead of refusing the whole request); `partial_at_decide: bool` (approve the qualifying occurrences instead of rejecting the whole request) | First come, first served within capacity per processing slot; `queue_over_capacity` holds the rest |
| **Count** | id, label, `rate` (met ÷ due, excluding listed statuses: `approved_request`, `cancelled`; pending counts as missed) or `tally` (number missed, excluding approved) | Recomputed on demand, always from records |
| **Check** | id, label, run by a checker role, count, comparison (`>=` / `<=`), and **either** one threshold at one timing parameter **or** an **escalation ladder** checked every period (an ordered list of threshold → outcome, each a blueprint parameter) | Records `check_evaluated` with both figures (as is, and if pending requests were approved). An escalation outcome is an event that can trigger listed roles. A ladder step is reached once the count no longer passes that step's threshold, by the same `engine.passes` a single check uses; comparisons are `>=`, `<=`, `>`, `<`, so a tally `<` 2 reaches its step at 2. Each step a person newly reaches is one `check_evaluated` (with `outcome`, `ladder_step`), recorded in ladder order even when several are reached at once; its `passed` is false only at the last step (built in L9a). A ladder period with no new step records where the person stands (`standing`, `ladder_step`, no `outcome`, so it notifies nobody) only if a request for an occurrence already recorded is still pending, so a wait before any penalty is visible at the check (added after slice 8) |
| **Disruption kind** | `obstacle` (delay on a duty for listed people, at an explicit list of steps in its period), `conflict` (a personal clash the person may miss the duty for; 26 Nov), `capacity` (queue capacity override in a period), `cancellation` (listed occurrences cancelled). Obstacles and conflicts state `routine`. From M6 an entry may recur (`until_period`, `every`); from M7 a conflict may name an `obligation`; from M8 each kind states `leaves_proof` | Applied at its phase, recorded as an event |
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

## Model change (M slices, 26 Nov evening)
Each item is a general block used by both templates. Template words stay in the templates.

**Why: the five gaps found in the code (26 Nov).**
1. A `conflict` never forced a miss, and attending through it cost nothing (`record_step`; rulebook "you miss the session only if you choose to").
2. A disruption had one `period`, so a routine work shift happened once.
3. Every filed, excusable miss was approved; the only friction was capacity and the check week.
4. The only detectors were `check_failed` and `pending_at_check`; margin lived inside the search.
5. Excused classes left the count (5 / 8 = 62.5% instead of 13 / 16 = 81%), and nothing showed it.

**Versions and defaults (M0).**
- One `policy.check_version(template, blueprint)` replaces the eight copies of `template.version != bp.template_version` (agents, comparison, counterfactual, explore, fixture, repeats, runner, search). An older blueprint gets a clear 409 "made with an older template", never a 500.
- `Parameter.default` gives every new value today's behaviour, so v1 blueprints, `tests/cases/*.json` and the demo fixture keep validating until the re-record.
- `Template.reads_versions` lists the blueprint versions a template still reads (`[1, 2]`). Both templates go to `@2` at their first edit in M1.

**One way of counting (M1).**
- One pure `count_records(kind, records, cancelled, excused, reading)` is used by `Engine.count`, `evidence.calculation`, the search's closeness and the ledger.
- The sentences that state the counting (rulebook, explore) read the same reading.
- `Count.excused_param` names a policy choice: `remove` (default: excused occurrences leave the count, as today) or `count_as_met`.

**Recurrence (M6).**
- A disruption entry may cover periods `period` … `until_period`, every `every` periods. `expand_disruptions` turns it into per-period copies before any check.
- Caps: 10 entries (unchanged), 24 expanded occurrences, 12 hitting any one person.
- Every reader of a raw `period` uses the expansion or shows the range: explore's queue lines, the search's changed values, the CLI, the UI.
- The fill is told that routine kinds recur as the profile implies. Variants and random scenarios may use ranges within the same caps.

**Competing obligations (M7).**
- A `conflict` kind may name an `obligation`: `label` (what is missed, e.g. "work shift"), `lost_label` (e.g. "job lost") and `limit_attribute`, a per-person `Attribute` the fill sets from the profile. The limit is labelled an assumption and is editable before approval.
- Meeting the policy duty during that clash records `obligation_missed`. Passing the limit records `obligation_lost` once, and the person stops having that clash.
- **A person with no plan during an obligation clash goes to the obligation** (`plan: default_obligation`), so a timeout or an untriggered person never silently gives up a job.
- The rulebook states both stakes with numbers, in a fixed order.
- New detector `obligation_lost`: the rule kept someone compliant at the cost of their job or care.
- Attendance: `work_shift_clash` and `family_emergency`. Curfew: `evening_job_shift` and `family_emergency`.


**Person state (M7c, 27 Nov).**
- The brief's agent schema (`memory`, `resources`, `knowledge`, `current_strategy`; "common schemas for agent state, observations, decisions and actions") was narrowed at the plan of 24 Nov to a profile, numeric attributes, 3 memory notes and a strategy line. Rules and stakes then reached people as prompt sentences, and their own tally didn't: in the M7b runs no one used the misses they had left. M7c restores the state.
- `Engine.person_state(person, step) -> PersonState`, recomputed from the records, never stored apart from them:
  - per duty and count: `missed`, `excused`, `pending`, the count's text, and `misses_left` before each check (the single check, or every ladder step), 0 when the next miss fails it;
  - per obligation the person can be hit by: `missed`, `limit`, `left`, `lost`;
  - their own requests and their current strategy (already in the context).
- `misses_to_fail` moves from rulebook.py into core (it is general); the rulebook and explore import it from there.
- `DecisionContext.state` carries it. The prompt shows one "Your state" block in place of the separate count lines; the lines frozen in tests/golden stay character for character inside it. The rules block keeps only the mechanics: a template's obligation `stakes` no longer hold `{limit}` ("past your limit you lose the job"); the number is in the state.
- Every `decision` event's payload records the `state` it was made from, so the evidence and the people route show what the person knew (the brief's "structured decision records: observation context").
- `GET /api/runs/{id}/people/{person}`: the person's profile and limits, and per decision the state it was made from, its actions and reason. It reads the run's events; no engine is rebuilt.
- Memory stays the last 3 decision notes; the tally is the state, not memory.

**Structured output (M7d, 27 Nov).**
- Bedrock Converse `outputConfig.textFormat` (`json_schema`) constrains decoding to the schema. Probed 27 Nov on `deepseek.v3.2` in ap-southeast-2: 6 of 6 real fills well-formed, 15–20 s; 5 of 6 passed every check (the other a wrong value, retried as now).
- `strict_schema(model)`: Bedrock enforces types, enums, `required`, `$defs` and `minItems` 0/1, but not min/max, lengths or `maxItems`, and needs `additionalProperties: false` on every object. Those keywords are dropped from what Bedrock sees; Pydantic still validates every reply, with the one retry.
- Limits: at most 12 optional properties and 16 union properties per schema. Measured 27 Nov: fill 9 and 2, variants 6 and 2, pick 0 and 0, on both templates.
- A label's `field` becomes an enum of the value names and sections, so a fill can't name "purpose".
- The first call with a new schema compiles a grammar (up to about 90 s; cached 24 h). The 5 fixed schemas (pick; fill and variants per template; the search reuses variants) are warmed once at server start, in the background; `RULESTORM_WARM_SCHEMAS=0` turns that off for tests and local work.
- A Bedrock `ValidationException` on the schema falls back to today's unconstrained call, logged. The repair of the key typo stays for that path.
- Not used for agent decisions (each action's `params` is an open object, which a strict schema forbids) or for the comparison (its schema changes with each blueprint, so each call would compile anew).

**The template's readings, shown and changeable (M8).**
- **What counts as exceptional:** a policy choice of `unforeseen_only` (routine causes are rejected), `any_documented`, or `decider_judges` (only on an LLM-decided request type: the decider weighs it, as today). Default: `unforeseen_only` on a rule-decided type (attendance, as today) and `decider_judges` on an LLM-decided one (curfew's warden, as today; checked 27 Nov: curfew's request type is `decided_by: llm`, and its wardens approved routine job-shift late entries).
  - The engine applies `unforeseen_only`, `any_documented`, proof and the deadline before any decider, so an LLM decider is offered only requests the policy allows; a rejection names the reading.
  - For a step not yet recorded (a request filed in advance), the cause is the disruption hitting that person at that step; none means not exceptional.
- **The people are told (M7b, M7c):** the rules block states each reading in force (what counts, proof, the deadline). With a deadline set, the person's state lists, per duty, the misses they can still file for and the last step to file; the rules carry no per-person numbers.
- **Proof:** each disruption kind states `leaves_proof` (a template reading, shown). A request type may name a `proof_param` (policy bool, default false): with it on, a cause that leaves no proof isn't excused. `cause_text` says "no documentation".
- **Filing deadline:** a request type may name a `deadline_param` (policy int, 0 = none), with a new precondition `within_deadline`.
- `GET /api/templates/{id}` adds `readings`: the count reading, routine, leaves_proof and obligation per kind, the decision-rule sentences, and which of them are parameters.
- What-ifs may change one policy value (int, bool or choice, with `stated_only` respected) as well as one environment value. `matched` accepts either. Policy versions may change the new policy values.
- A values check keeps ladder thresholds in order.
- **The new readings stay out of the blueprint fill.** They are `in_fill: false` (M7b's flag, as `excused_counting`), so M7d's fill schema, its label list and the 5 warmed schemas don't change. They take `Parameter.default`, are shown as template readings and are editable on the review screen, so the fill (25–30 s of a 55 s budget) grows only by recurrence ranges and obligation limits. M7b measures 5 fills per example, which must stay under 40 s.

**Integrity of the AI people (M4, M5).**
- **Claimed cause:** a new action-parameter type `cause`, optional, only on actions that plan a miss (attendance `skip`, curfew `stay_out_late`).
  - The engine accepts "none" (their own choice) or the exact ID or kind of a disruption hitting this person this step. There is no free-text matching: anything else is refused with the valid values listed.
  - Otherwise it refuses with `claim: not_affecting_you`, a detail from `Engine.situation` and the valid causes. The person is asked once more in the same step, so a refused claim never silently turns into attending.
- **"Your situation now":** a block in every prompt, from `Engine.situation(person, step)`: what affects them this step, or that nothing does. It sits after the trigger list, so the frozen golden lines stay as they are.
- **Intentions:** a decision may state up to 2 `intends` (actions planned later). A trigger `intention_due` asks the person at the step they named, at most once per person per step. The prompt reminds them ("You said you would …") and says it's a reminder, not a commitment. Met or unmet is recorded.
- `ActionParam.omit_means` words what leaving an optional value out means.
- The run summary adds `false_claims`, `intentions_stated`, `intentions_unmet`, `error_decisions_while_hit`.

**Results: harm, near misses and why (M2, M3, M9).**
- **Findings:** new kinds `near_threshold` (passed, spare ≤ 1 at the last step that harms) and `obligation_lost`, numbered after the old kinds so earlier IDs don't move.
  - Every finding has `harm` (true for check_failed, obligation_lost, pending_at_check).
  - Every harm has a `cause_class`, by rules over the records, in this order. All events are looked up by (person, step) for every step in the chain:
    1. *no_reply*: the model call for that person failed or timed out in a step of the chain. This is an infrastructure problem, not an AI mistake.
    2. *ai_mistake*: a refused false claim or a refused untrue correction.
    3. *forced*: misses caused by obstacles over slack alone reach the fail point.
    4. *process*: it needs a pending, late, proof-refused or deadline-refused request.
    5. *trade_off*: it comes from obligation clashes (attending cost the obligation, or meeting the obligation cost the duty), under the policy's reading of what is exceptional. Every `obligation_lost` is a *trade_off*.
    6. *chosen*: the remaining misses are skips when nothing affected the person.
  - The ledger shows, next to each *trade_off*, the assumptions that set it: how often the clash recurs and the person's limit. That way the policymaker sees the harm comes from the rule and the conditions, not from the AI.
- **Everything that used to mean "broke" uses `harm`:**
  - the search reruns only on harm, and a confirmed break needs the same kind **and person**, with neither finding *no_reply*, *ai_mistake* nor *forced*;
  - `explore hunt` stops only on harm;
  - the UI's red tone is harm.
- **Margins:** ladder margins are measured to every step, from the records (a ladder rarely emits events). Ranking and `near_threshold` use the last step.
- **Repeats and comparison** add the spread of margins, obligations lost, near misses, unexcused absences and AI mistakes.

**Evaluation before re-recording (M10).** docs/EVALUATION.md is written and committed before any run:
- fresh fills of both example policies, 5 repeats each, no code or prompt change in between (a fix restarts the protocol);
- the report covers the AI-mistake rate, the ledger of every run, the cause class of every harm, calls per run, and 15 sampled decisions to read;
- success is integrity and a full ledger, never "a failure appeared". No harm is a valid result;
- then one search per example, reported with cause classes;
- **pass lines, set beforehand:**
  - false claims plus no-reply decisions are at most 10% of decisions;
  - at most 150 calls per run;
  - no failed runs;
  - every fill under 40 s.

  A miss on any line is a no-go for M11.

**The demo run and the cutoff (M11).**
- `RULESTORM_RETIRED_BEFORE` is set only in the deploy that also ships the new fixture.
- `reset-demo` gives the restored run, blueprint and policy the restore time, so `demo` is never hidden by the cutoff.
- The demo run is chosen from the M10 runs:
  - a harm finding by docs/DEMO_FLOW.md's rule, if one exists;
  - otherwise the run with the smallest margin, exported with its `near_threshold` finding, or with no finding at all, in which case the ledger is the headline.
- The fixture test accepts both.

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
| Model realism (26 Nov evening, team decision) | Competing obligations, recurrence, readings as parameters, checked claims, ledger and cause classes (M0–M11), all general and on both templates | A policymaker needs to see who a rule hurts and why. A model where complying costs nothing can only show planted or random failures | Staged go/no-go: the 28 Nov checkpoint deploy (M0–M9 plus the UI, with the cutoff unset and the current fixture), M10 by 29 Nov 12:00 IST, M11 by 29 Nov 18:00 IST. On a no-go, deploy the last tag that passed its live checks, with the cutoff unset and the fixture it shipped with; the rest ships after 5 Dec for Round 2 |
| Search break | A harm finding for the same kind and person, repeated by the rerun, neither *no_reply*, *ai_mistake* nor *forced* (M2, M9) | A break caused by an AI error or by piled-on disruptions tells the policymaker nothing about the rule | Report "broke once" or "not broken" with the closest margin, never an invented break |

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
- **Model change (26 Nov evening):** build all of M0–M11, no cuts, deployed before the 30 Nov freeze (team decision). Old recordings are hidden with `RULESTORM_RETIRED_BEFORE` (an ISO time; anything stored before it reads as not found), never deleted.
- **Earlier team decisions (BRIEF):** no Streamlit, Vercel or Supabase; SQLite, not DynamoDB; 2–3 AWS accounts (one live); link shared with the team and judges only, no login; deploy freeze 30 Nov–5 Dec.

## Not doing
- **Everything in BRIEF "Not doing":** no Streamlit; no S3, ECR, Lambda, API Gateway, Cognito or load balancers; no DynamoDB store; no login; no AWS Organizations; no model training; no claims of real-world prediction.
- **Templates:** no AI-written templates, no template editor, no domains outside education, no building blocks beyond the table above.
- **Explanations:** no LLM-written finding explanations. The "AI interpretation" label shows the agents' own stated reasons.
- **AWS setup:** no scripted account setup (CLI or IaC), no deploy key, no Node on the instance, no Parameter Store.
- **Server:** one uvicorn worker, one active run at a time; no websockets or server-sent events, so the UI polls.
- **Libraries:** no Pandas or Plotly until a nice-to-have needs them.
- **Results:** no tuning of a template, prompt or scenario until a failure appears; changes are judged by docs/EVALUATION.md. No policy score, and no LLM-written explanation of a cause class.

## Critic findings rejected
- **"Make blueprint generation asynchronous":** rejected. The blueprint calls share one 55 s wall-clock budget inside CloudFront's 60 s, so a sync request is enough.
- **"Don't do Level 2 now; do Level 1.5 and move curfew to after the UI" (Level 2 critique, Fatal #1):** rejected. Level 2 is the team's decision. The risk is handled by building alongside the old engine, the 25 Nov 15:00 go/no-go gate and Level 1.5 as the fallback. Its hero advice (put the queue maths in the variants prompt) is adopted.
