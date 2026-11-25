# User journey and screens

What the UI phase (`/ui`) builds, screen by screen, on top of the finished core. Everything here uses routes that exist and were proved in slices 1–13 and U0. Two optional routes that don't exist yet are listed at the end; the screens work without them.

Written 25 Nov from the code and real responses (run `demo`, run L-960f5653, the live server). Field names below are the real JSON keys.

## Who and where
- **User:** a policymaker at an Indian college. Non-technical; writes rules in plain language; keeps the final decision. On stage, also the judges, who may click through it themselves.
- **Device:** a laptop browser first (judges and the demo video). It must also work on a phone, read-only, at 16 px side margins with no sideways scrolling.
- **Link:** https://d2emiyaz9dq4bi.cloudfront.net. The UI is served by FastAPI from the same server (`web/dist`), so every call is a same-origin `/api/...` request. No login, no keys in the browser, and Bedrock is never called from the browser.
- **Words on screen:** take the template's own words (week/night, session, absent/late, exception request, eligible/not eligible) from `GET /api/templates/{id}` (`terms`, `calendar`, `people`, `roles`, `parameters`). Never hard-code "attendance" or "student" in the UI: the curfew template must read just as well. A run's `template` is `"attendance@1"`; the ID is the part before `@`.

## The two paths

**A. Demo path (3 minutes, no waiting, no Bedrock):**
Home → **Open the demo run** → Run (finished) → Findings → **Evidence (the hero)** → What if? → Compare.
The demo run is a real recorded run, restored on every deploy. Its hero is `demo-F1`: the working student falls to 8 / 11 = 72.7% against 80% at the early week-6 check and loses exam eligibility, after a train disruption in week 5 and storms in week 6. No exception was filed in time.

**B. Full path (a new policy, about 1–2 minutes of waiting in total):**
Home → Policy input → (wait 15–30 s) Blueprint review → Approve → optional Stress test → Run (live, 30–60 s) → Findings → Evidence → What if? → (30–60 s) Compare → Decide.

| BRIEF journey step | Screen |
|---|---|
| 1. Draft the policy | S2 Policy input |
| 2. Check what the rule means | S3 Blueprint review (+ S4 Stress test) |
| 3–4. Roll out, live with the consequences | S5 Run |
| 5. Find out what went wrong (hero) | S6 Findings → S7 Evidence |
| 6. Fix the rule | S8 What if? → S9 Compare |
| 7. Decide | S9's closing panel |

The BRIEF's 8-screen demo journey maps onto this: Landing = S1; Policy input = S2; Blueprint + approval = S3; Launch and Live simulation = S5 (one screen); Discovery = S6 + S7; Comparison = S9, one condition at a time. **Not in this build, so not designed:** strict vs flexible vs progressive comparison (slice 15), repeated runs as distributions, replay, an agent memory view, and a final assessment report.

## Rules for every screen
- **Polling, not live connections:** the server has no websockets. Poll `GET /api/runs/{id}?after=<last seq>` every 3 s while a run is `running`, and stop when it isn't.
- **Waiting:** a blueprint takes 15–30 s (55 s at most) in one request. Show a working state with a running seconds counter and the sentence "Reading your policy and building the simulation. This takes up to a minute." Disable the button so it can't be sent twice. A request still unanswered after 65 s is a failure: say so and offer to try again.
- **One run at a time, for everyone:** starting a run while any run is going returns **409** with that run's `run_id`. Say "Another simulation is running right now" and offer "Watch it". Judges may hit this.
- **Daily limits:** **429** means the server's daily limit (10 runs, 1,000 model calls, 50 blueprint requests a day) is used up. Say "Today's limit for new simulations is reached. You can still open the demo run and any finished run." Never retry a 429 automatically.
- **Errors:** show the server's `detail` sentence; it's already in plain words (for example "threshold_pct is a policy value; a counterfactual changes only an environment condition: …"). For 5xx or network errors: "The server didn't answer. Try again in a minute." Never show a stack trace.
- **IDs:** show run and finding IDs small and copyable (`demo`, `L-960f5653`, `demo-F1`, `E-0111`). They are the evidence trail, not decoration.
- **Labels:** three evidence labels must look clearly different everywhere they appear, each with a one-line legend:
  - **recorded fact:** what the engine recorded;
  - **calculated:** what a rule worked out;
  - **AI interpretation:** a person's own stated reason.
  Blueprint values carry two: **fact** (from your text) and **assumption** (the AI's proposal).
- **The within-model label:** any comparison shows "within-model evidence, not real-world causality" as a visible banner, not a footnote.
- **Speed:** opening a run, its findings and a finding's evidence each answer in under 1 s through CloudFront (measured 0.20–0.33 s). Show content at once; skeletons only for the slow calls (blueprint, a live run).

## S1 Home
- **Goal:** know what RuleStorm does, and get to the demo or a new test in one click.
- **Calls:** `GET /api/templates` → `[{id, version, title, scope, example_input: {text, purpose, environment}}]`.
- **Shows:**
  - One line on what it is: "See how a rule plays out against students' real constraints and staff capacity, before rollout."
  - One honest line: "It explores possible responses in a simulation; it does not predict what a real college will do."
  - **What it can model:** one card per template, with `title` and `scope` (today: "Attendance and exam eligibility" and the hostel curfew).
- **Actions:**
  - **Open the demo run** (primary on stage) → S5 for run `demo`.
  - **Test a new policy** → S2.
  - **Open a run by ID:** a text field and button. → S5; a 404 says "No run with that ID."
- **States:** if `/api/templates` fails, still show both buttons.

## S2 Policy input
- **Goal:** write the rule in plain words; nothing else to configure.
- **Fields:** **Policy**, **Purpose**, **Environment** (who is affected, what the college is like). Each takes 1–2,000 characters, with a live counter; stop typing at 2,000, since the server answers 422 above it.
- **Pre-filled:** the attendance template's `example_input`. Chips "Use the attendance example" and "Use the hostel curfew example" fill all three fields from each template's `example_input`. The user may edit anything.
- **Action: Build the simulation:**
  1. `POST /api/policies {text, purpose, environment}` → `{id: "P-…", text, purpose, environment, created_at}`.
  2. Then `POST /api/blueprints {policy_id}` → a blueprint record (S3). Show the waiting state while it runs (see "Waiting" above).
- **Errors:**
  - 422 (a field empty or too long): show it under the field.
  - 429: "Today's limit for building new simulations is reached."
  - No answer after 65 s: "Building took too long. Try again." Each try costs one of the day's 50 blueprint requests.

## S3 Blueprint review and approval
- **Goal:** see how RuleStorm understood the rule, tell **your facts** apart from **the AI's assumptions**, and approve it.
- **Data:** the record from `POST /api/blueprints`, which has these keys:
  - `id`, `status` (`valid` | `invalid` | `out_of_scope`), `errors[]`, `template_id`, `template_version`, `pick_reason`, `seconds`, `approved`, `policy_id`;
  - `blueprint: {values, facts[], assumptions[]}`, where each fact or assumption is `{field, statement}`.
- **If `out_of_scope`:**
  - Say "RuleStorm can't model this policy yet."
  - Show `pick_reason` and the template cards from S1 ("What it can model").
  - Button: **Edit the policy** (→ S2, fields kept).
- **If `invalid`:** say "The AI's draft didn't pass the checks", list `errors[]` in a collapsed panel, and offer **Try again** (a new `POST /api/blueprints` with the same `policy_id`).
- **If `valid`, show:**
  - **Header:** the template's title (e.g. "Attendance and exam eligibility"), with "Why this model" = `pick_reason`, labelled **assumption**. Show the blueprint ID small.
  - **Three sections, in this order**, grouping the values by their parameter `kind`:
    - **Policy rules** (kind `policy`). For attendance: `threshold_pct` 80, `scope` per_course, `exception_rule` (text), `request_timing` after_missed / in_advance, `partial_at_submit`, `partial_at_decide`, `decision_rule`.
    - **Conditions** (kind `environment`). For attendance: `office_capacity_per_week` 5, `checkpoint_week` 6, and `disruptions[]`.
    - **People** (kind `people`): `profiles` and `slack_min`.
  - **Each value** shows its description in plain words, the value, and a **fact** or **assumption** badge with its `statement`. To find the badge, look for a label whose `field` is the value's name; if there is none, use the label whose `field` is its section (`policy`, `environment` or `people`); if there is still none, show no badge. Facts are listed first, then assumptions.
  - **Disruptions:** one row each, in week order. Each is `{kind, period, steps, people, delay, capacity, description}`, for example "Week 5, session 1 of the week: Train line disruption, 45 min delay, affects commuter, resident, working, family". Here `steps` count within the week (1 = the week's first session). Events later use term-wide step numbers (session 9 = week 5's first).
  - **People:** one card per person.
    - From `profiles`: `{description, goals[≤2], constraints[≤2]}` per person ID.
    - Plus their number in `slack_min` (attendance: the travel buffer in minutes; curfew: the slack per resident).
    - The card's title is the person's label from the template, e.g. "working: has fixed work hours".
    - Rule-run roles (the attendance office and the exam officer) have no profile. Show them in a "Run by rules, not AI" row.
- **Actions:**
  - **Approve:** `POST /api/blueprints/{id}/approve` → the record with `approved: true`. Once approved, it can't be changed, and the screen says so ("Frozen: every run uses exactly these values").
  - After approval:
    - **Run this term** (S5): `POST /api/runs {blueprint_id}`;
    - **Stress-test it first** (S4).
  - **Edit (slice 18):** before approval every single value has **Edit** (a number field within its range, a menu, a yes/no or a text box) and the people section has **Edit each person's …**. `PATCH /api/blueprints/{id}/values {changes}` checks the value against the template (422 shows the reason under the field) and returns the record with the value as **your fact** ("Corrected by you: … 8 -> 2"). Lists (disruptions, profiles) aren't edited here: to change those, go back to S2 and build again. Approved blueprints show no Edit (409 "frozen").
- **Errors on approve:** a 409 "blueprint not valid" shouldn't happen from this screen. If it does, show it.

## S4 Stress test (optional)
- **Goal:** let the AI propose up to 3 harsher but plausible versions of the conditions, each aimed at a different weak point. The policy and the people stay the same.
- **Calls:** `POST /api/blueprints/{id}/variants` → `{parent_id, status, errors[], variants: [blueprint record…], attempts, seconds}`. This is one model call, 15–20 s, with the same waiting state as S2. Each variant record has `variant` (its name), `weak_point`, `status` and its own `id`.
- **Shows:** one card per variant:
  - its name and weak point;
  - **what changed** against the parent: compare the two `values` and show only the `environment` keys that differ (office capacity 5 → 1; checkpoint week 8 → 6; disruptions added). Policy and people never differ;
  - a fact/assumption badge on each changed value. The changed values are always assumptions.
- **Actions:**
  - **Approve** on each card: `POST /api/blueprints/{variant_id}/approve`.
  - **Run** on each approved card: `POST /api/runs`. Only one runs at a time; the others wait.
- **Errors:** 409 "blueprint not approved" (the parent must be approved first); 429 for the daily blueprint limit.

## S4b Search for breaks (slice 16b, optional)
- **Goal:** let RuleStorm look for the conditions that break an approved policy, instead of the policymaker guessing.
- **Where:** Blueprint review → **Search for breaks** tab, `#/blueprint/<id>/search[/<search id>]`.
- **Calls:** `POST /api/blueprints/{id}/search {max_runs: 3 | 6 | 9}` → `{id, status: "running", …}`, then `GET /api/searches/{id}` every 3 s while `running`.
- **Shows:** the within-model banner; runs used of the maximum; each round (round 2 onwards says which weak point it pushes); one card per scenario: targeted by the AI or random (no AI), its weak point, what changed (environment values only), each run and rerun with its ID, findings and a closeness bar ("working: 2 absences to spare before 'not eligible' (week 10)").
- **End:** `broken`: the scenario, both run IDs and an **Evidence** button per finding (to S7); `not_broken`: "The policy held: not broken in N runs" with the closest scenario. Never an invented break.
- **Errors:** 409 with `search_id` ("Another search is running right now" → Watch it), with `run_id` (Watch it) or `comparison_id`; 429 when today has fewer than 3 runs left.
- **Demo:** a search takes several minutes and up to 9 of the day's runs, so record one before the demo and open it by its address.

## S9b Compare policies (slice 17, optional)
- **Where:** Blueprint review → **Compare policies** tab, `#/blueprint/<id>/compare[/<comparison id>]`.
- **Calls:** `POST /api/comparisons {blueprint_id}` (waits for one AI call, 10–30 s: show the waiting state), then `GET /api/comparisons/{id}` every 3 s while `running`.
- **Shows:** the within-model banner; values kept in every version (`kept`); one card per version with its approach, what it changed and its run; the trade-off table (`table.rows`, one column per version) and the per-person check rows, rows that differ marked; the AI-choice `note`; "You decide" with links to each run's findings. No score, no winner.
- **Errors:** 409 (a run, search or comparison is going), 429 (fewer than 3 runs left today), `invalid` (the AI's versions failed the checks).

## S5 Run (launch, live timeline, finished)
- **Goal:** watch the term unfold week by week, see who decided what and why, then go to the findings.
- **Calls:**
  - **Start:** `POST /api/runs {blueprint_id}` answers within 1 s with `{run_id, status: "running"}`.
  - **Poll:** `GET /api/runs/{run_id}?after=<last seq>` every 3 s. It returns `{run_id, blueprint_id, template, status, period, periods, model_id, summary, error, started_at, finished_at, timeline: [event…]}`. With `after`, the timeline holds only the new events; append them.
  - `status` is one of `running`, `completed`, `degraded` or `failed`.
- **Header:**
  - run ID;
  - template title;
  - status as a badge;
  - progress "Week 4 of 10" (`period` / `periods`), as a bar while running;
  - when finished: the duration (`finished_at` − `started_at`) and the model (`model_id`).
- **The timeline:**
  - **Grouped:** by week (`period`), then by session or night (`step`; null means the week-end phase: queue processing and checks). Newest last, and it scrolls to follow while running.
  - **Every event:** `{event_id, seq, period, step, type, actor, payload, state_change, caused_by[]}`.
  - **Filter chips:** Disruptions · AI decisions · Refused · Requests · Records · Checks. Default: everything except routine records.
  - **How to show each type** (real types in the demo run, with counts):

| `type` | Chip | Show as | Key payload fields |
|---|---|---|---|
| `obstacle` (3) | Disruptions | ⚠ "Train line disruption: 45 min delay for commuter, resident, working, family" | `description`, `delay`, `people`, `duty` |
| `capacity_changed` (1) | Disruptions | ⚠ "Office short-staffed: capacity this week 5 → 2" | `description`, `capacity`, `state_change` |
| `occurrence_cancelled` (1) | Disruptions | "Session 8 cancelled" (`step`) | `description`, `state_change` |
| `decision` (28) | AI decisions | the person's label, their `reason` in quotes, and their `strategy` underneath; an empty decision says "chose to do nothing" (`no_action`); a failed call (`error`) says "no decision (the AI call failed)" | `proposals[]`, `reason`, `strategy`, `no_action`, `error` |
| `action_rejected` (4) | Refused | ✕ "family's exception request refused: session 9 had not been recorded yet when you sent this" | `action`, `detail` (plain words, show this), `reason` (code, hide) |
| `duty_planned` (17), `attribute_set` (1) | AI decisions | small: "commuter plans to attend", "travel buffer 60 → 60" | `state_change` |
| `request_filed` (4) | Requests | "family filed exception request R1 for session 9: '<reason>'" | `request_id`, `steps`, `reason` |
| `request_decided` (4) | Requests | "R1 approved after 0 weeks" | `decision`, `approved_steps`, `rejected_steps`, `waited_periods` |
| `queue_processed` (10) | Requests | small: "Office processed R1 (capacity 5); waiting: none" | `capacity`, `processed[]`, `pending[]` |
| `queue_over_capacity` | Requests | ⚠ "Office over capacity: R3 waits" | `held[]` |
| `decision_awaiting`, `decision_not_made`, `request_endorsed`, `request_endorsement_refused` | Requests | curfew: the warden's slot, a guardian's consent | `offered`, `held` |
| `duty_recorded` (76) | Records | grid per person: present/absent per session, in the template's words | `person`, `outcome` (met/missed), `obstacle` |
| `record_corrected` (6) | Records | "faculty corrected working's session 9: absent → absent" | `state_change` |
| `many_missed` (3), `count_near_threshold` (4) | Checks | "3 students absent in session 9" · "working is at 80.0%, at the threshold" | `people`; `person`, `value`, `threshold` |
| `message_sent`, `response_given` (4) | AI decisions | "advisor → working: 'Your attendance is exactly at the 80% threshold…'" | `to`, `advice` (attendance) or the template's message field |
| `check_evaluated` (4) | Checks | ✓/✕ "exam eligibility for working, week 6: 72.7% (needs ≥ 80) → not eligible" | `person`, `count.value`, `threshold`, `passed`, `pending_requests[]`; curfew ladder: `outcome`, `ladder_step`, `standing` |

- **People strip** (side or top): one chip per person, showing their latest count (from `count_near_threshold` and `check_evaluated`), how many decisions they made (`summary.decisions_by_agent` when finished), and their last reason. Clicking a person filters the timeline to their events. Their profile comes from the blueprint; see the gaps.
- **When finished:**
  - `completed`: a summary row with decisions, model calls, refused actions (`summary.rejected[]`, each `{event_id, agent, action, reason}`) and errors. Primary button: **See what went wrong** → S6.
  - `degraded`: as completed, plus "Some AI calls failed or hit the limit (`summary.llm_errors`, `cap_hits`); results may be thinner."
  - `failed`: show `error`, a short sentence, and offer "Run it again".
- **Errors on start:** 409 with `run_id` ("Another simulation is running" → Watch it); 409 "blueprint not approved"; 429.

## S6 Findings
- **Goal:** see what went wrong in this run, found by rules from the records, not written by an AI.
- **Calls:** `GET /api/runs/{run_id}/findings` → `{run_id, status, findings: [...]}`. It is empty while the run is going.
- **Each finding** has `{finding_id, kind, title, person, check, check_label, check_event_id, period, outcome, count: {met, due, missed, value, pending[], approved[], rejected[]}, count_if_pending_approved: {…}, pending_requests[], disruptions[], chain[]}`.
- **One card each:**
  - **Kind badge:** `check_failed` = "Objective failure", `pending_at_check` = "Bottleneck".
  - **Title:** in the template's words, e.g. "Students fall below the attendance threshold and lose exam eligibility".
  - **Who and when:** the person's label and "week 6" (`period`).
  - **The figure:** "8 / 11 = 72.7%, needs 80%" (`count`), then `outcome` ("not eligible").
  - For a bottleneck, the figure as it would be if waiting requests were approved: "92.9% now, 100% if R5 were approved" (`count_if_pending_approved`, shown only when it differs).
  - **Size:** "15 linked events", "3 disruptions".
  - **Action:** **Show the evidence** → S7.
- **Empty state:** "No problems found in this run." Offer **Stress-test the policy** (S4) and **What if?** (S8). Never invent a finding.

## S7 Evidence (the hero moment)
- **Goal:** click a finding and see the exact chain of events, state changes and calculations behind it, each labelled.
- **Calls:** `GET /api/findings/{finding_id}/evidence` → `{finding_id, run_id, kind, title, person, steps: [...]}` in under 1 s.
- **Each step:** `{event_id, period, step, type, actor, label, text, state_change, interpretation, calculation}`.
- **Layout:** one vertical chain in run order, from the disruption at the top to the check at the bottom. Each step shows:
  - the `event_id` chip and "week 5 · session 9" (`period`, `step`; no step = "end of week");
  - the **label badge**, in the three distinct styles;
  - `text`, already a sentence in the template's words: "Train line disruption: a delay of 45 on 'attend class' for commuter, …";
  - `state_change`, as "from → to" rows (e.g. `check.exam_eligibility.working: — → failed`); hide it when empty;
  - for **AI interpretation** steps, `interpretation`: the person's own reason in quotes, attributed ("faculty said: …");
  - for the **check step**, `calculation` as a highlighted block:
    - `recorded.text` ("attendance 8 / 11 = 72.7%") against "needs ≥ 80" → `outcome`;
    - and `if_pending_approved.text`, when it differs;
    - plus "✓ recomputed from this run's records" when `matches_recorded` is true.
- **Top:** the finding's title and person, with a one-line legend for the three labels.
- **Bottom actions:** **What if?** (S8, for this run) and **Back to findings**.
- **Demo note:** the hero is `demo-F1`, 15 steps from the week-5 train disruption, through the week-6 storms and the faculty's corrections, to `E-0111` (the check). Two faculty "corrections" change nothing (absent → absent; see IDEAS). Show them as recorded, never hide them.

## S8 What if? (counterfactual)
- **Goal:** rerun the same term with one condition changed and everything else kept the same.
- **Form:**
  - **Condition:** only the template's single-value `environment` parameters. For attendance that is `office_capacity_per_week` (0–50) and `checkpoint_week` (1–10); for curfew, `warden_capacity_per_night` (0–20). Show each with its description and its value in this run.
  - **New value:** a number field within the parameter's range (or a toggle for true/false, or a menu of choices).
  - Policy values and the disruption list are not offered: the server refuses them (422).
- **Action:** `POST /api/runs/{run_id}/counterfactual {parameter, value}` → `{run_id, status: "running", source_run_id, blueprint_id, source_blueprint_id, changed: {parameter, from, to}, label}`.
  - Then show S5's progress for the new run inline ("Week 3 of 10"). When it finishes → S9 with `GET /api/runs/{source}/compare/{new}`.
- **Errors:** 422 with `detail`, shown under the field ("office_capacity_per_week = 51 is not allowed: Input should be less than or equal to 50"; "… is already 5 in this run"); 409 (another run going); 429.
- **Copy:** "Same people, same disruptions, same policy. Only this one condition changes. The AI people still make their own choices, so some differences come from them."

## S9 Compare (and decide)
- **Goal:** see both runs side by side, and judge whether the changed condition mattered.
- **Calls:** `GET /api/runs/{a}/compare/{b}` → `{label, template, differences: [{parameter, kind, from, to}], matched, note, runs: [run_a, run_b]}`.
- **Each run's figures:**
  - `queue_length: {longest, periods_over_capacity}`;
  - `waiting_time: {unit: "periods", decided, mean, longest, never_decided}`;
  - `requests_filed`;
  - `checks: [{check, person, period, value, threshold, passed, pending_requests}]`;
  - `check_failed[]` and `pending_at_check`.
- **Layout:**
  - **Banner (always):** "within-model evidence, not real-world causality".
  - **What changed:** "Office capacity per week: 5 → 1" (`differences`).
    - If `matched` is false: "These runs differ in more than one condition, or in none, so this isn't a controlled comparison."
  - **Two columns** (this run | the what-if run), one row per measure: longest queue, weeks over capacity, average and longest wait (in the template's period word), requests filed, never decided.
  - **Check results table:** one row per person, two columns of ✓/✕ with the value (72.7% ✕ | 80.0% ✓). Highlight rows where the outcome flips.
  - **Note** (always shown, not hidden): `note`, i.e. "The AI people decide afresh in each run, so their choices can differ even when every condition is matched." The real L-960f5653 pair shows why: the working student passed and the family student failed instead.
- **Decide panel (bottom):** no AI verdict and no score. Show "You decide", the findings of each run (links to S6), and **Try another condition** (S8) or **Test a new policy** (S2).
- **Errors:** 409 (a run still going: keep polling); 404; 422 (different templates).

## Read routes for the screens
Built in slice U0 (25 Nov), read-only, no Bedrock, each under 0.01 s:

- **`GET /api/templates/{id}`** (S2–S9): `{id, version, ref, title, scope, terms, calendar: {periods, steps_per_period, period_label, step_label}, example_input, roles: [{id, label, llm, rules}], people: [{id, role, label}], attributes: [{id, label, role, min, max}], parameters: [{name, kind, type, min, max, choices, attribute, max_length, description}], disruption_kinds: [{id, label, kind}], checks: [{id, label, comparison, ladder}], counterfactual_parameters: [names]}`.
  - Use `parameters[].kind` to group S3's sections and `description` as each value's plain words.
  - Use `people[].label` and `roles[].llm` / `rules` for the people cards and the "Run by rules, not AI" row.
  - Use `calendar.period_label` and `step_label` for "week 5 · session 9".
  - Use `terms` for the outcome words.
  - Use `counterfactual_parameters` with each one's `min`/`max`/`choices` for S8's form.
  - Only shipped template IDs (`attendance`, `hostel_curfew`) answer; anything else is 404.
- **`GET /api/blueprints/{id}`** (S3 after a reload, S5's people strip, S8's current values): the stored record, exactly as `POST /api/blueprints` returned it, with `approved` as it is now. 404 if missing. To get there from a run, use the run's `blueprint_id`.

Still not built, and not needed for the demo path:

| Route | Needed by | Without it |
|---|---|---|
| `GET /api/blueprints/{id}/variants` | S4 after a reload | Variants show only right after the POST |
| `GET /api/runs?limit=20` | S1, a list of recent runs | Open by ID only (meets must-have 9) |

## Demo script hooks (for /ship 2)
- **Open with:** S1 → **Open the demo run**, then S5 already finished (170 events), then S6 → `demo-F1` → S7. The hero lands at about 1 minute.
- **What if?** on the demo run, either:
  - **live:** office capacity 5 → 1 takes 30–60 s of real Bedrock and uses one of the day's 10 runs;
  - **pre-recorded:** run the what-if once before the demo and open its comparison directly (`/api/runs/demo/compare/<that run>`).

  Every deploy restores run `demo`, but a what-if run made before a deploy stays in the store.
- **Never** show a fake or hand-made run (BRIEF).
