# Slices

## Relay note
(Empty. Filled by /slice when a teammate takes over: next step, gotchas.)

## Requirements
- R1 (must): Accept a plain-language policy, purpose and environment (max 2,000 characters), pre-filled with our 80% example, so that `policy example` prints the stored policy with an `id` and the 80% text.
- R2 (must): Turn the policy and environment text into a frozen, approved Blueprint through the model adapter, with Pydantic range checks, so that `blueprint create` prints `threshold_pct: 80`, a transport disruption, an admin capacity, non-empty facts and assumptions and `status: valid`, and a run on an unapproved blueprint is refused. The Blueprint holds policy parameters, scenario values (each labelled as a user fact or an AI assumption) and a validation status.
- R3 (must): Run the deterministic engine so that `engine check` prints the attendance and queue results for a fixed test case and a student's attempt to edit attendance is rejected. The engine covers the attendance formula, the lateness rule, a FIFO queue within the approved capacity, eligibility in code, permission checks and event IDs.
- R4 (must): Have 6 agents decide through the model adapter when a trigger affects them, returning a validated `AgentDecision` that records its trigger. The admin and exam officer are rule agents. A per-run call cap applies, the phase deadline is 40 s, and every Bedrock error is recorded as "no action". Check: a test run records decisions only for triggered agents and none past the cap.
- R5 (must): Run the disruptions in the approved blueprint's schedule so that a run's event log contains a transport disruption and an admin capacity crunch at the listed weeks, and a fixed-input test shows the engine links the hero steps through `caused_by`.
- R6 (must): Run simulations in a background thread, one at a time, with pollable progress so that `POST /api/runs` returns a `run_id` at once (409 if one is running) and `GET /api/runs/{id}` moves to `completed`, `degraded` or `failed`.
- R7 (must): Detect objective failures and operational bottlenecks from the records so that a completed run lists "Exception-processing bottleneck creates an eligibility risk" with the ordered chain found by following `caused_by` links.
- R8 (must): Build the evidence chain for a finding so that `GET /api/findings/{id}/evidence` returns the ordered steps, each with `event_id`, state change, calculation and a label.
- R9 (must): Open any stored run by ID and restore the seeded demo run (a recorded real run, bundled with its policy and blueprint) with one command so that after `reset-demo`, the demo run and its hero finding load.
- R10 (must): Serve the app live on AWS (EC2 + Bedrock via the instance role, SQLite on EBS, CloudFront HTTPS, Budgets alert, daily caps, status-check alarm) so that the full curl flow works through the `cloudfront.net` URL and a run over the daily cap gets HTTP 429.
- R11 (nice): Counterfactual rerun with more admin capacity under matched conditions, so that the comparison shows queue length, delay and eligibility for both runs, labelled within-model evidence.
- R12 (nice): CloudWatch logs and custom metrics (LLM calls, tokens, run duration).
- R13 (nice): Three-policy comparison under matched conditions.
- R14–R27 (nice): Brief ranks 4–17. Not planned in this build.

**Proof conventions:**
- Run from the repo root with the virtual environment active.
- Run proofs in **Git Bash**. In PowerShell, `curl` is a different command: use `curl.exe` and put the body in a file, `-d "@body.json"`.
- `python -m pytest …` runs with `RULESTORM_ENV=test` and the fake model (set in `tests/conftest.py`).
- Every `cli` command without `pytest` uses real Bedrock and needs your own IAM user's profile in `AWS_PROFILE`.
- `curl` proofs need `python -m uvicorn rulestorm.api:app --port 8000` running.
- Test-only numbers (like Student C's 15/20) live in test files, never in app code.

## Slices
| # | Goal in user words | Covers | Proof command | Expected result | Status |
|---|---|---|---|---|---|
| 1 | The policymaker's policy, purpose and environment are saved, starting from our 80% example | R1 | `python -m rulestorm.cli policy example` then `curl -s -X POST localhost:8000/api/policies -H "Content-Type: application/json" -d '{"text":"x","purpose":"y","environment":"z"}'` | CLI prints JSON with `id` and `text` containing `80%`; curl returns JSON with a new `id`; a 2,001-character `text` returns HTTP 422 | done |
| 2 | RuleStorm can talk to Bedrock safely, and we know the account's real limits (day-0 smoke test) | R2, R4 (adapter) | `python -m pytest tests/test_llm.py -q` then `python -m rulestorm.cli llm smoke` | pytest passes four cases: valid reply; retry then valid; invalid twice → no action; exception → no action. Smoke prints, from real Bedrock in ap-southeast-2: `model`, `ok: true`, `auth: profile=<name>` (or `auth: instance-role` on EC2), `latency_ms`; a blueprint-sized call's `output_tokens` and `seconds`; the model's requests-per-minute and tokens-per-minute quotas from Service Quotas. Numbers written into BRIEF; `read_timeout` set from them | done |
| 3a | The policymaker gets an AI blueprint of their rule and scenario, with facts separated from assumptions | R2 | `python -m rulestorm.cli blueprint create --policy <id>` | Prints: `threshold_pct: 80`; `scenario.disruptions` with ≥1 `type: transport`; `scenario.admin_capacity_per_week` (≥0); `scenario.checkpoint_week` (1–10); non-empty `facts` and `assumptions`; `status: valid`; finishes in under 55 s. `pytest tests/test_blueprint.py -q` passes "threshold 150 rejected" and "invalid twice → status invalid with errors" | done |
| 3b | The policymaker approves the blueprint, and it can't change afterwards | R2 | `python -m rulestorm.cli blueprint approve <blueprint_id>` then `python -m pytest tests/test_approval.py -q` | approve prints `approved: true`. pytest passes: "approved blueprint cannot be edited" and "run on unapproved blueprint refused", and `POST /api/runs` with an unapproved ID returns HTTP 409 with `blueprint not approved` | done |
| 4 | The rule engine computes attendance, the exception queue and eligibility exactly, and blocks actions a role may not take | R3 | `python -m pytest tests/test_engine.py -q` then `python -m rulestorm.cli engine check --case tests/cases/student_c.json` | pytest passes. The CLI prints, for the test case: `15/20 = 75.0% (2 exceptions pending)`, `15/18 = 83.3% (if 2 approved)`, `queue FIFO: R1,R2 processed, R3 pending (capacity 2)`, `student edit_attendance: rejected (permission)`; each line carries an event ID `E-…` | done |
| 5 | A simulated term runs week by week with the blueprint's disruptions, and the engine records why each thing happened | R3, R5, R4 (triggers) | `python -m pytest tests/test_chain.py -q` | Passes, with fixed test inputs: (a) the log holds `transport_disruption` and `capacity_crunch` at the blueprint's weeks; (b) trigger rules fire (a disruption triggers the listed students, an absence triggers that student, a request pending a week triggers the student and advisor); (c) following `caused_by` from the eligibility evaluation reaches the disruption both when the student arrived late and when they skipped because of it | done |
| 6a | Six stakeholder agents make their own decisions when triggered, within a call budget and time limit | R4 | `python -m pytest tests/test_agents.py -q` | Passes: decisions only for triggered agents, each with `caused_by` = its trigger; a cap of 5 stops at exactly 5 calls and records `cap_hits: 1`; proposals sorted by agent ID before validation; a call slower than the phase deadline is recorded as a timeout no-action; a run with >10% error no-actions ends `degraded` | todo |
| 6b | Real agents run a real term, and we know how often the hero finding appears | R4, R5 | `python -m rulestorm.cli run local --blueprint <approved_id>` (3 times) | Each prints `status` (`completed` or `degraded`), `llm_calls` ≤ cap, `llm_errors`, per-agent decision counts and a `rejected` count (may be 0) with reasons. **Checkpoint 26 Nov:** read the 3 event logs by hand and write into BRIEF how many show a request pending at the checkpoint and the measured run duration | todo |
| 7a | Runs happen in the background and the timeline can be followed while they progress | R6 | `curl -s -X POST localhost:8000/api/runs -H "Content-Type: application/json" -d '{"blueprint_id":"<id>"}'` twice, then `curl -s localhost:8000/api/runs/<run_id>` every few seconds | The first POST returns a `run_id` within 1 s. The second returns HTTP 409 with the same `run_id`. GET shows `status: running` with `week` rising, then `completed` or `degraded`, with a `timeline` list | todo |
| 7b | Spending stays capped and broken runs are visible, not stuck | R6, R10 (caps) | `python -m pytest tests/test_runner.py -q`, then set `MAX_RUNS_PER_DAY=0` in `.env`, restart, and repeat the 7a POST | pytest passes: "runner exception → failed with error"; "running at startup → failed (interrupted)"; "4 threads racing for 1 remaining call → exactly 1 succeeds". The POST returns HTTP 429 | todo |
| 8 | RuleStorm finds the problems in a run on its own: failures and bottlenecks, with the events behind them | R7 | `python -m pytest tests/test_detect.py -q` then `curl -s localhost:8000/api/runs/<6b_run_id>/findings` | pytest: the slice-5 test run yields `Exception-processing bottleneck creates an eligibility risk`, with a `chain` running from the disruption to the eligibility evaluation. curl: the findings on a real 6b run match what the hand-check of that run's event log found in 6b (same finding titles, same request IDs) | todo |
| 9 | Clicking a finding shows the exact chain of events, state changes and calculations behind it (hero) | R8 | `curl -s localhost:8000/api/findings/<finding_id>/evidence` | JSON `steps` in chain order, each with `event_id`, `state_change` and a `label` in {`recorded fact`, `calculated`, `AI interpretation`}. The eligibility step's `calculation` shows the recorded attendance figure and the figure if pending requests were approved, both computed from that run's events. Answers in under 1 s | todo |
| 10 | Any finished run can be opened again, and the demo run is restored with one command | R9 | `python -m rulestorm.cli run export <real_run_id> --out rulestorm/fixtures/demo_run.json`, then `python -m rulestorm.cli reset-demo`, then `curl -s localhost:8000/api/runs/demo` and `curl -s localhost:8000/api/runs/demo/findings` | reset-demo prints `restored run demo (schema 1) with policy and blueprint`. The run returns `status: completed`; findings contain the hero finding. `pytest tests/test_fixture.py -q` passes: the file opens as UTF-8 without a byte-order mark, the schema version matches, `llm_errors == 0`, and the hero finding is present. The fixture is a real Bedrock run, recorded by 28 Nov noon | todo |
| 11 | The app runs on our own AWS server and calls Bedrock with the server's own role | R10 | In a Session Manager shell on the instance: `bash deploy/deploy.sh <tag>`; then from a laptop `curl -s http://<elastic-ip>/api/health` | deploy prints the tag and `rulestorm.service active (running)`; the service runs as a non-root user (`AmbientCapabilities=CAP_NET_BIND_SERVICE` for port 80); curl returns `{"ok":true}`; on the instance, `python -m rulestorm.cli llm smoke` prints `auth: instance-role` and `ok: true` with no AWS keys on the machine; `docs/DEPLOY.md` checklist written (role, instance, EIP, security group, Budgets alert) | todo |
| 12 | Judges get a safe HTTPS link that works for every action, and we're told if it goes down | R10 | `curl -s -o /dev/null -w "%{http_code}" https://<dist>.cloudfront.net/api/health`, then the slice-1, 3a and 7a POSTs through the same URL | health returns 200 and `{"ok":true}`; each POST returns the same status code and the same JSON keys as against localhost (no 403); the blueprint POST finishes under 60 s; with `MAX_RUNS_PER_DAY=0` in `/etc/rulestorm.env`, a run POST returns 429; DEPLOY.md lists the CloudFront settings and the status-check alarm, with its SNS email subscription confirmed | todo |
| 13 | The policymaker reruns the same term with more admin capacity and compares outcomes (stretch: before the UI only if slices 1–12 are done by 27 Nov, else after it) | R11 | `curl -s -X POST localhost:8000/api/runs/<run_id>/counterfactual -H "Content-Type: application/json" -d '{"admin_capacity_per_week":5}'` then `curl -s localhost:8000/api/runs/<run_id>/compare/<new_run_id>` | POST returns a new `run_id` whose blueprint differs only in `admin_capacity_per_week` (same disruptions and profiles); a value outside 0–50 returns HTTP 422; compare returns `queue_length`, `processing_delay` and `eligibility` for both runs and `label: within-model evidence, not real-world causality` | todo |
| 14 | We can watch LLM calls, tokens and run time in CloudWatch (after the UI, if time) | R12 | On the instance, start one run, then `aws cloudwatch list-metrics --namespace RuleStorm --region ap-southeast-2` | Lists `LLMCalls`, `Tokens`, `RunDurationSeconds`; app log lines appear in log group `/rulestorm/app` | todo |
| 15 | Strict, flexible and progressive policies are compared under the same conditions (after the UI, if time) | R13 | `curl -s -X POST localhost:8000/api/comparisons -H "Content-Type: application/json" -d '{"blueprint_id":"<id>"}'` then `curl -s localhost:8000/api/comparisons/<id>` | Three runs with the same scenario values and different exception rules; a trade-off table with attendance, eligibility and admin workload per policy and no single overall score | todo |

Status values: todo · doing · done · cut

**Order and dates:**
- **Today:** one named teammate creates one AWS account and uses it as the Dev account. The live account is added before slice 11.
- **Core slices:** 1–10 first. Slices 2, 3a, 6b, 8 (curl) and 10 need Bedrock; while the account isn't ready, build 1, 4, 5 and 6a.
- **26 Nov:** checkpoint after 6b (the hit rate is written into BRIEF).
- **By 27 Nov:** slices 11–12.
- **28 Nov morning:** the UI phase (/ui) starts, whatever is done. The fixture (slice 10) is recorded by 28 Nov noon.
- **Slice 13 (counterfactual):** the one stretch item. Do it before the UI only if 1–12 are done by 27 Nov; otherwise after it.
- **After the UI, if time:** slices 14–15.
- **29 Nov:** last deploy.

**For the UI phase:** `.gitignore` currently ignores every `dist/` folder. /ui must add `!web/dist/` so the built UI is committed, and `deploy.sh` must stop if `web/dist/index.html` is missing.

**Another way to slice it:** by layer (store, then adapter, then engine, then agents, then API). That's worse because nothing works end to end until the last layer. We would only find out at the very end whether real runs produce the hero chain, which is the riskiest part.

## Riskiest slice
Slice 6b, because real Bedrock agents must decide reliably, and the hero finding must then come out of real runs with nothing in code forcing it. The example input is kept descriptive, so the numbers are AI assumptions.

**Fallback:**
- Switch the model (DeepSeek V3.2, then Qwen3 235B).
- Shorten the prompts and memory.
- Keep doing real runs and export the first clean one that shows the finding.
- The user may edit the input on screen.
- If no real run shows it by 27 Nov evening, the demo shows the real findings the runs did produce (for example, a bottleneck without the eligibility step) and says so plainly.
- Never a fake model or hand-made run in the app or the demo.

## Slice critic findings rejected
- **Cut the credit-activity steps and the second and third accounts:** rejected. These are team decisions (BRIEF, Account and credits). Only the order changed: one account today, the live account before slice 11.
- **Daily cap on creating policies:** rejected. Saving a policy calls no model and costs no credits.
- **Concrete numbers in the example input:** rejected by the team (24 Nov). The example stays descriptive.
- **No slices for Bharat Impact evidence:** not a build slice. The team deferred non-technical research (see BRIEF Gaps).
