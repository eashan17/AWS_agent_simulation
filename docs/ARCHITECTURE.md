# Architecture

## In one line
A policymaker types an attendance rule. RuleStorm turns it into checked parameters and runs ten simulated weeks in which student and staff agents react to disruptions inside a rule engine. It then shows the exact chain of recorded events behind each problem it finds.

## Pieces and data flow
Arrows show which way data moves. Everything runs in one Python process on one EC2 instance.

    browser (UI phase: React + Vite static files, built on a laptop, served by FastAPI)
      └─> CloudFront (HTTPS; /api/* all methods, no caching, 60 s origin timeout)
            └─> EC2 :80  FastAPI, one uvicorn worker (systemd)
            ├─ POST /api/policies ─────────────> store.save_policy (text ≤ 2,000 chars)
            ├─ POST /api/blueprints ───────────> policy.interpret ──> llm.decide ──> Bedrock Converse (ap-southeast-2)
            │                                     └─> Pydantic Blueprint check (types + ranges), facts vs assumptions ──> store
            ├─ POST /api/blueprints/{id}/approve ─> store
            ├─ POST /api/runs ─> one active run? (else 409) ─> daily run cap (atomic, else 429)
            │      ─> runner thread (returns run_id at once; any exception → status failed + error)
            │      runner: the approved, frozen blueprint (policy parameters + scenario values, incl. student profiles)
            │        └─> engine loop, one decision phase per session (20)
            │              ├─ disruption schedule ─> events
            │              ├─ affected LLM agents (4 students, faculty, advisor) ─> llm.decide, in parallel
            │              │     (max 4, same snapshot; per-call cap taken atomically) ─> AgentDecision ─> sorted by agent ID
            │              ├─ rule agents in code: attendance admin (FIFO queue within weekly capacity),
            │              │     examination officer (eligibility rule at the checkpoint)
            │              └─ validate permissions/preconditions ─> commit ─> event log
            │                    (event_id, seq, week, type, actor, state change, caused_by[]) ─> store
            │      after the last week: detectors ─> findings, each with its ordered chain
            │              [(role, event_id), …] ─> store
            ├─ GET /api/runs/{id} ─────────────> status, week, timeline (the UI polls every 3 s)
            ├─ GET /api/runs/{id}/findings
            └─ GET /api/findings/{id}/evidence ─> evidence.build: reads the finding's chain,
                                                   adds state changes, both attendance figures, labels
    CLI: python -m rulestorm.cli <command> calls the same core functions as each route.
    On startup: any run still marked running → failed (interrupted).

**Modules** (in `rulestorm/`):

| Module | What it holds |
|---|---|
| `education.py` | The education model's structure only: entity and action types, the 8 agent roles and the 4 student archetypes, and the pre-filled example input text. No scenario numbers: those come from the blueprint |
| `policy.py` | Blueprint schema and `interpret`. Each student profile holds a description, 1–4 goals, constraints and a travel buffer, all from the user's text or approved AI assumptions (slice 3c) |
| `llm.py` | Model adapter: Bedrock and a scripted fake |
| `engine.py` | State, actions, permissions, arrival and lateness rule, FIFO queue, attendance and eligibility maths, event log |
| `agents.py` | 6 LLM agents and 2 rule agents, with compact memory and current strategy. A student's prompt is built from its blueprint profile (`DecisionContext.profile`); faculty and advisor prompts use their role, the policy parameters and the policy's stated purpose. No agent goals or personalities are written in code |
| `detect.py` | Objective-failure and bottleneck detectors; follows `caused_by` links and writes the ordered chain onto each finding |
| `evidence.py` | Builds the hero view from a finding's chain, including the attendance figure with pending requests approved |
| `store.py` | Storage interface + SQLite |
| `runner.py` | Background thread, progress, caps, one-active-run rule |
| `api.py`, `cli.py` | Routes and terminal commands, both calling the same core functions |
| `fixtures/demo_run.json` | The seeded demo run, with a schema version |
| `deploy/deploy.sh` | The deploy script |

**Decision triggers** (general mechanics in `education.py`, not scenario values; added after the slice critique, 24 Nov). Which events make an agent decide:
- A disruption triggers the students it lists.
- A student's own absence triggers that student.
- Attendance within 5 points of the threshold triggers the student and the advisor.
- A request pending for a week or more triggers the student and the advisor.
- A faculty-relevant event (session cancelled, attendance falling across students) triggers the faculty member.

**Engine causality rules** (these make every hero step a rule, not a label):
- Every decision records `caused_by=[the event that triggered it]`, and every action and event it produces records `caused_by=[decision_id]`.
- A student who decides to attend arrives late if the disruption delay is more than their travel buffer. That absence records `caused_by=[disruption_id, decision_id]`.
- A student who decides to skip because of a disruption produces an absence linked through the decision to that disruption, so it still counts.
- An exception request records the absences it covers.
- The queue-over-capacity event records the requests it holds.
- The eligibility evaluation records the attendance figure and the pending requests.
- The detector follows these `caused_by` links from the eligibility evaluation back to the root disruption. It stores the chain it finds, in order, on the finding, instead of matching a fixed list of steps.

**Where scenario values come from (team rule: no hard-coded scenario rules):**
- Every number and event the run uses comes from the user's input or from an AI assumption shown for approval. That covers each student's description and goals (slice 3c; only the 4 archetype names are fixed), student constraints (commute, work hours, family commitments), admin capacity per week, checkpoint week, and the disruption schedule (week, type, size, who is affected).
- The policymaker approves it all on the review screen, and the approved blueprint is frozen, so a run and its counterfactual use the same values.
- The code holds only the engine's general mechanics (attendance formula, FIFO queue, lateness rule, permissions, eligibility check), as BRIEF must-have 3 defines them.
- The pre-filled example input describes the conditions of our spec's sample run in plain words, for example "the attendance office can process only a few exception requests a week" or "transport disruptions happen during the term". It is ordinary user input and editable on screen.

**Hero chain from real runs:**
- From the first day Bedrock works, we do real runs from the example input and record how often the finding appears.
- Nothing is changed in code to make it appear. If it rarely appears, that is reported honestly.
- The demo replays a recorded real run in which it did appear (must-have 9).

**Model adapter contract:** `decide(prompt, schema) -> schema instance`.
- It asks for JSON in the prompt (no tool use) and validates the reply with Pydantic. If that fails, it retries once with the validation error included.
- boto3 settings are adaptive retries and `connect_timeout=5`; `read_timeout` starts at 25 s and is reset from the day-0 smoke-test measurement. Agent calls get up to 5 attempts.
- Each decision phase has a 40 s deadline. Calls still unfinished then are recorded as timeouts ("no action").
- Blueprint calls get exactly 2 Bedrock calls in total: the first try plus the validation retry, with no boto retries. The blueprint's `maxTokens` is capped and its fact and assumption lists kept short, so both attempts finish under 55 s, inside CloudFront's 60 s.
- Each run counts `llm_errors` (error or timeout no-actions) and `cap_hits`. A run ends `degraded` instead of `completed` when more than 10% of its decisions were error no-actions or the cap stopped it.
- Any exception (throttling, timeout, access error) or a second invalid reply gives a recorded "no action" decision with the error text. For a blueprint, it gives `status: invalid` with the errors.
- The model ID is a setting. `RULESTORM_MODEL=fake` selects a fake model for automated tests only. The app refuses to start with it unless `RULESTORM_ENV=test`.

**Store tables** (SQLite, WAL mode, one connection per thread):

| Table | Fields |
|---|---|
| policies | the stored policy texts |
| blueprints | policy parameters, facts, assumptions, status, approved |
| runs | status (running / completed / degraded / failed), week, model ID, blueprint ID, counts, llm_errors, cap_hits, error |
| events | run_id, event_id, seq, week, type, actor, payload, state_change, caused_by |
| decisions | agent, prompt hash, raw reply, parsed decision, accepted/rejected + reason, error |
| findings | run_id, kind, title, chain |
| daily_usage | date, runs, llm_calls, blueprint_calls |

Caps are taken atomically: `UPDATE … SET n = n + 1 WHERE date = ? AND n < cap`, where rowcount 0 means over the cap.

## Decisions
| Decision | Choice | Why (from the user's problem) | Fallback if it fails |
|---|---|---|---|
| Language and API | Python 3.12 + FastAPI + Pydantic + boto3 | The spec's stack. Pydantic gives the schema check that the blueprint and every agent decision need | — (proved by kickoff) |
| UI | React + Vite + Tailwind, built on a laptop, `web/dist` committed and served by FastAPI (team choice) | The timeline and evidence views are interactive. It fits the /ui and Claude Design flow, and there's no Node on EC2 | FastAPI templates + plain JS for the 3 hero screens |
| AI model, blueprint | DeepSeek V3.2 (`deepseek.v3.2`) on Bedrock Converse, in-Region Sydney (Region fixed by the account, 24 Nov). Changed from Mistral Large 3 after the day-0 smoke test (team choice, 24 Nov) | Fast and steady on our account: 2 s for a tiny reply, 8–9 s for a blueprint, against Mistral's 17–84 s and 13–65 s (BRIEF, smoke test results). The Free plan blocks cross-Region | Qwen3 235B (a config change). The day-1 bake-off decides |
| AI model, agent decisions | Same model and adapter. Only the 6 agents with real choices, and only when an event affects them | Agents must decide, not opine. Fewer calls keep cost and run time down | Qwen3 235B (no Claude model runs in-Region in Sydney). Never a fake model in the app |
| Admin and exam officer | Rule-following code (team choice) | The spec allows it, and it keeps the queue and eligibility steps exact | — |
| Blueprint scope | Bedrock fills the parameters of our education model from the policy and environment text. Policy: threshold % (50–100), per-course scope, exception rule, outcomes to monitor. Scenario: student constraints, admin capacity per week (≥0), checkpoint week (1–10), disruption schedule. Each value is labelled as a user fact or an AI assumption. Approved values are frozen (team choice) | The policymaker writes plain language and approves every value. The engine stays tested code, there are no hard-coded scenario rules, and matched runs share the same values | If the check fails twice, show the errors; the user edits the input text and tries again |
| Search over documents | No | The input is one short policy text | — |
| Background runs | A thread in the single uvicorn process, with one active run at a time. Progress goes to the store, and the UI polls. Exceptions mark the run failed, and interrupted runs are marked failed on startup | Must-have 6. A run is several minutes of Bedrock calls, and judges may start one on their own | SQS worker (nice-to-have 14) |
| Parallel calls | Affected agents in one phase are called in parallel (max 4; 2 if Bedrock limits are low), all on the same snapshot. Proposals are sorted by agent ID before validation | Cuts wall-clock time, and sorting keeps results independent of thread timing | Sequential calls |
| Storage | SQLite on the instance's EBS disk, behind one Storage interface, with the same backend in tests | The hero view reads one finding and its listed events. No free-tier capacity limits (see BRIEF Storage decision) | A JSON file per run on disk, behind the same interface |
| Demo data | `fixtures/demo_run.json`: an export of one real, `completed` (not degraded) Bedrock run from the example input that contains the hero finding. It bundles its policy and approved blueprint, so the demo never waits on Bedrock. It must be recorded after slice 3c, so the bundled blueprint passes the current schema (student descriptions and goals present). It carries a schema version and has a test that loads it, checks `llm_errors == 0` and finds the finding. Written in UTF-8 by Python, not by a shell redirect. `reset-demo` loads it. Recorded by 28 Nov noon | The 3-minute demo must reach the hero moment without waiting for a fresh run, and it replays what actually happened | Keep doing real runs and export the first one with the finding. Never a hand-made or fake-model run |
| Spend guard | A per-run LLM-call cap, plus global daily caps on runs, LLM calls and blueprint calls, all taken atomically. Settings live in `/etc/rulestorm.env` on EC2 and `.env` locally. Over a cap → HTTP 429. One active run → 409 | Credit exhaustion suspends the live account and kills the link | Budgets alert email; optional budget action denying Bedrock |
| Hosting | One EC2 t3.small or t4g.small (standard CPU credits), Ubuntu 24.04 (Python 3.12 built in), ap-southeast-2 (Sydney), Elastic IP, systemd service on port 80, IAM instance role, Session Manager (no SSH port) | The PS needs a live AWS link. One box has no request timeouts for long runs | — (required) |
| HTTPS link | CloudFront, origin = the EC2 public DNS name (Elastic IP attached first). `/api/*`: all methods, CachingDisabled + AllViewer origin-request policies, 60 s origin timeout. Static files cached | Browsers warn on plain HTTP | Submit `http://<elastic-ip>` |
| Setup and deploy | Live account set up once in the console, from a checklist the deploy slice writes (`docs/DEPLOY.md`): role, instance, EIP, security group, CloudFront, Budgets, alarm + SNS. Repo made public after the secret scan. `deploy/deploy.sh <tag>` (about 10 lines, run in a Session Manager shell): fetch, check out the tag, pip install, restart the service | Least setup time on a brand-new account. It can still put the submitted tag back | Copy a tarball up through the Session Manager shell if git fails |
| Monitoring | EC2 status-check alarm → SNS email (must-have 10). CloudWatch logs and metrics are R12 | We must know if the judged link dies | Check `/api/health` by hand twice a day during judging |

## Speed target
- **Hero moment:** opening a stored run, its findings and a finding's evidence each answer in under 1 second.
- **Blueprint:** under 30 seconds typical and under 60 seconds hard (timeouts above), with a progress message.
- **Fresh run:** progress is visible within 5 seconds of starting and updates every 3 seconds. The target for a whole run is under 5 minutes; it's measured on the first Bedrock day and written into BRIEF.

## Settled questions
- **Build hours:** about 40–60 across the team. Scope is the must-haves plus the counterfactual (R11). CloudWatch metrics (R12) and the three-policy comparison (R13) come only after the UI. The UI phase starts on the morning of 28 Nov whatever is done; the last deploy is 29 Nov.
- **Must-have 4:** 6 agents decide through Bedrock (4 students, faculty, advisor). The attendance administrator and examination officer are rule-following code. All 8 appear in the simulation.
- **Must-have 2:** the blueprint fills the parameters of our education model, covering both policy and scenario values. Nothing is hard-coded to force an outcome; every value comes from the user's input or an approved AI assumption (team rule, 24 Nov). Full CSR generation stays nice-to-have 15.
- **Agent structure (slice 3c, 24 Nov):** the 8 roles, the 4 archetype names, role permissions, triggers and engine mechanics are fixed in code, as BRIEF must-have 4 defines them. Each student's description, goals, constraints and travel buffer come from the blueprint, and every decision comes from Bedrock at run time. AI-defined roles, actions or permissions would be the full CSR (nice-to-have 15) and are not in this build.
- **Fake model:** for automated tests only, never in the app or the demo. The demo replays a recorded real run.
- **After the slice critique (24 Nov, team approved):**
  - decision triggers and `caused_by` links on every decision, with the detector following them;
  - `degraded` run status and a 40 s phase deadline;
  - the blueprint timeout set from measurement, with the demo export bundling its policy and blueprint.
- **Example input:** it stays descriptive (conditions in words). The AI proposes the numbers as assumptions and the user approves them. We don't write concrete numbers into the example (team decision, 24 Nov).
- **Region (24 Nov, after the first account was created):** ap-southeast-2 (Sydney), fixed by the account's new AWS experience. Mistral Large 3, DeepSeek V3.2, Qwen3 235B, Kimi K2.5, gpt-oss and Nova Pro were checked live as on-demand in-Region models; no Claude model is. t3.small and t4g.small are Free-plan eligible there.
- **UI:** a React + Vite + Tailwind static build served by FastAPI.
- **Hero input:** the seeded demo run (must-have 9). In the demo, a run started before going on stage shows progress; the demo never needs a new run to be allowed.
- **Global caps:** live in `/etc/rulestorm.env`, not Parameter Store (BRIEF must-have 10 said Parameter Store; changed to cut setup).
- **From earlier team decisions (BRIEF):**
  - No Streamlit, no Vercel, no Supabase.
  - SQLite, not DynamoDB.
  - 2–3 AWS accounts: one live, the rest dev.
  - The link is shared with the team and judges only, with no login. The live URL stays out of the public README until after Round 1.
  - Deploy freeze from 30 Nov to 5 Dec.

## Not doing
- Everything in BRIEF "Not doing":
  - No Streamlit.
  - No S3, ECR, Lambda, API Gateway, Cognito or load balancers.
  - No DynamoDB store.
  - No login.
  - No AWS Organizations.
  - No model training.
  - No claims of real-world prediction.
- No LLM-written finding explanations. The "AI interpretation" label shows the agents' own stated reasons.
- No scripted AWS account setup (CLI or IaC), no deploy key, no Node on the instance, no Parameter Store.
- Only one uvicorn worker and one active run at a time.
- No websockets or server-sent events; the UI polls.
- No Pandas or Plotly until a nice-to-have needs them.

## Critic findings rejected
- **"Make blueprint generation asynchronous" (part of #3):** rejected. Exactly two Bedrock calls at a 25 s read timeout (no boto retries for blueprints) finish inside the 60 s origin timeout, so a sync request is enough and saves a second polling flow.
