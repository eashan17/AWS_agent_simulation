# Brief: RuleStorm

**AI-Powered Policy Simulation and Stress Testing**
*Discover what happens when policies meet real people.*

Source: `Idea+PS/RuleStorm_Consolidated_Product_and_MVP_Specification (2).md` (our spec). Rules: `RULES.md`.

## Problem
"A policymaker at an Indian educational institution risks students being held ineligible for exams and staff being overloaded when they roll out a rule like *80% attendance for exam eligibility*, because they have no practical way to see how the rule interacts with students' real-life constraints and the institution's processing capacity before implementation."

A strict attendance rule can affect a long-distance commuter, a student with fixed work hours and a student with family responsibilities differently. It can also create extra work for faculty, advisors and administrators. These consequences may be overlooked during policy design.

## Persona
- **Role:** institutional decision-maker / policymaker at an Indian educational institution (the person who drafts or approves academic rules such as attendance and exam eligibility). `[MISSING: a named, real person in this role we have spoken to]`
- **Context:** setting or revising an attendance policy that applies to students with very different circumstances (commuters, residents, working students, students with family commitments) and that runs through faculty, advisors, the attendance office and the examination office.
- **Goal:** improve class participation, encourage consistent attendance and maintain academic standards, and investigate plausible consequences before rollout. They keep the final decision.
- **Frustrations:** no way to test how a rule plays out against student constraints and institutional capacity before it goes live; problems such as exception backlogs surface only after students are affected. `[MISSING: their own words from an interview]`
- **Tech comfort:** non-technical. Writes the policy in plain language; does not configure simulation rules or create AI agents by hand.
- **Who benefits downstream:** students (whose eligibility is at stake) and the faculty, advisors and administrators who carry the workload. RuleStorm is a decision-support tool for institutions. It does not replace student services or decide policy for a university.

## Journey
| Step | Today (with the pain) | With RuleStorm |
|---|---|---|
| 1. Draft the policy | Rule written and approved without testing it against student constraints or staff capacity. `[MISSING: how institutions draft and review these rules today]` | Types the policy, its intended purpose and the education environment in plain language. |
| 2. Check what the rule means | Thresholds, exceptions and enforcement are left for staff to interpret after rollout. | Reviews an AI-generated blueprint: policy interpretation, stakeholders, goals, constraints, rules, outcomes to monitor, with **user-provided facts separated from AI assumptions** and a validation status. Approves it. |
| 3. Roll out | The rule goes live on real students. | Starts a simulation: one synthetic institution, one course, 20 sessions over 10 simulated weeks, 8 stakeholder agents. |
| 4. Live with the consequences | Disruptions (transport, workload, timetable, admin overload) hit; requests pile up; nobody sees the pattern until exam time. | Watches disruptions, agent decisions, strategy changes, requests and attendance/eligibility change week by week. |
| 5. Find out what went wrong | Discovered after a student is wrongly held ineligible, if at all. | **Clicks a discovered finding and sees the exact chain of events behind it** (hero). |
| 6. Fix the rule | Revised after harm is done. | Runs a counterfactual (e.g. more admin capacity) and compares strict, flexible and progressive policies under matched conditions. |
| 7. Decide | — | Reviews trade-offs and decides whether the consequences are acceptable. The policymaker keeps the decision. |

## Hero moment
The policymaker clicks the finding **"Exception-processing bottleneck creates an eligibility risk"** and RuleStorm opens the actual chain of events that answers *"Why did the student become ineligible at the eligibility checkpoint?"*:

1. Transport disruption caused missed attendance.
2. The student submitted an exception request.
3. The administrator received more requests than available processing capacity.
4. The student's request remained pending.
5. The examination officer evaluated the current attendance record.

On screen: each step with its **event ID**, the **state change** it caused, and the **deterministic calculation** (e.g. Student C at 15/20 = 75% while exceptions are pending, versus 15/18 = 83.3% once two are approved; illustrative numbers from our sample run). Recorded facts, calculated outcomes and the AI's interpretation are labelled separately. Root mechanism shown: the interaction between an external disruption, student constraints, administrative capacity and eligibility timing.

This is what shows a functioning simulation, not a chatbot listing a policy's possible downsides.

## USP
"Unlike asking a chatbot to list a policy's downsides, or research sandboxes such as PolicySim that test social-media platform interventions, we turn a plain-language institutional policy into a validated simulation where AI stakeholders make constrained, adaptive decisions inside a deterministic rule engine, and every finding traces back to recorded events and calculations, so an Indian institution's policymaker can find and investigate a hidden consequence (like an exception backlog that makes an eligible student look ineligible) before rollout."

Our differentiator is the combination of five mechanisms (policy-to-simulation translation; behaviour inside a governed environment; consequence discovery rather than scenario execution; dual-purpose exploration; inspectable policy comparison), not "multiple AI agents". We do not claim to be the first to do pre-deployment LLM policy simulation.

## Must-haves (the minimum that gets the MVP running end to end, through the hero moment)
**Re-plan, 24 Nov (team decision, Level 2):** the engine becomes general: fixed building blocks (people, duties, actions, request queues, counts, checks, disruptions) plus **templates written as data**. The blueprint first picks a template (or says the policy is out of scope), then fills its values: policy rules, people, capacities, timing and disruptions, each labelled fact or assumption. No policy rule stays in code: request timing and partial acceptance become blueprint values. Two templates ship. **Attendance** (below) is the must-have path. **Hostel curfew** has a different structure (10 people, guardian consent, a warden deciding requests, an escalation ladder) and proves the engine is general, but isn't a must-have. The must-haves below are read through templates; see docs/ARCHITECTURE.md and docs/SLICES.md.

1. **Policy input**: plain-language policy, intended purpose and the education environment (journey step 1). Pre-filled with our 80% attendance example.
2. **AI blueprint + approval**: Amazon Bedrock turns the policy into a structured policy definition and education blueprint (thresholds, exceptions, eligibility rule, stakeholders, outcomes to monitor). Pydantic schema check before it can run. Review screen shows user-provided facts vs AI-generated assumptions; the user approves (step 2).
3. **Deterministic simulation engine** over a declarative education config: one course, 2 sessions/week, 20 sessions, 10 weeks; attendance % = attended ÷ countable completed sessions × 100 (approved exceptions and cancelled sessions excluded, pending/rejected exceptions counted as absences); exception queue with limited admin capacity processed FIFO; eligibility evaluated by code. Agents only propose actions; the engine validates permissions (e.g. students cannot edit attendance or approve their own exceptions) and commits state. Every event and state change gets an ID (step 3).
4. **Eight stakeholder agents with event-triggered decisions**: 4 student archetypes (commuter, resident, working, family commitments) + faculty, advisor, attendance administrator, examination officer, each with goals, constraints, resources, information, a compact memory and a current strategy. Bedrock is called only for agents affected by an event, returns a structured `AgentDecision` (action, target, reason, strategy update), with a hard cap on LLM calls per run (step 3–4).
   *(24 Nov, slice 3c: each person's description, goals and constraints come from the blueprint. Level 2, same day: the 8 roles, their permissions and the request rules move out of code into the attendance template and the blueprint, so nothing about the cast or the rules is hard-coded. Templates are written by us; AI-written templates (Level 3) stay out of this build.)*
5. **Disruption schedule**: at least a transport disruption and an administrative capacity crunch, the two events the hero chain depends on (step 4).
6. **Simulation timeline view**: current week, events, agent decisions, accepted/rejected actions, requests, attendance and eligibility as the run progresses, with the run ID (step 4). The run executes in a **background thread or process on the instance**, never inside the web request; the UI polls its progress from the store every few seconds (no websockets, so it works through CloudFront).
7. **Finding detection from records**: deterministic detectors for **objective failure** (student ineligible or at risk at the eligibility checkpoint) and **operational bottleneck** (queue above capacity; request still pending at the checkpoint), producing the finding card (step 5). *(Level 2: written on the general model, as "check failed" and "request pending at the check", titled in the template's terms. Hero: whichever real finding is strongest at the 26 Nov checkpoint, found on purpose by slice H, team choice 24 Nov.)*
8. **Evidence chain view (hero)**: clicking a finding shows the linked event IDs, state changes and calculation, with recorded facts, calculated outcomes and AI interpretation labelled separately (step 5).
9. **Open a stored run + seeded demo run**: open any completed run by its run ID, and keep one pre-seeded completed run (containing the hero chain) that is restored with one command from a JSON fixture in the repo. Needed because a fresh run is about 150 mostly sequential Bedrock calls (several minutes), so the 3-minute live demo and the video must reach the hero moment from a stored run. Read-only view, not the full replay mode (nice-to-have 9). Measure real run duration on day 1 and write it here: `[MISSING: measured run duration]`.
10. **Live on AWS**: the whole app (backend, engine, frontend and the store) runs on **one Amazon EC2 instance** (ap-southeast-2, Sydney) with an Elastic IP, in our **live account** (see Account and credits), and calls **Amazon Bedrock** through the instance's IAM role (no hard-coded keys). Runs, events and findings are stored in **SQLite on the instance's EBS disk** behind one storage interface (same backend in tests; see Storage decision), since must-have 8 needs stored event records anyway. The judges' link is **HTTPS through Amazon CloudFront** (always free) in front of the instance; if CloudFront setup takes more than about an hour, submit the plain EC2 address and move CloudFront to the nice-to-haves. Before the first Bedrock call: an AWS Budgets alert, and a **global daily cap on runs and LLM calls** (one value in Parameter Store, checked before each run starts). An **EC2 status-check alarm emails us via SNS** if the link dies. Required by the rules: without a live AWS link there is no valid submission. See **Technical decisions** below.

## Nice-to-haves (our other features, ranked by demo impact per hour)
Items marked **(spec: MUST)** are MUST HAVE in our spec; they moved here only because the hero moment still runs without them. Nothing is deleted.

1. **Controlled counterfactual rerun** (spec: MUST): raise admin processing capacity, keep policy, initial profiles and disruption schedule matched, compare queue length, delay and eligibility. Labelled *within-model evidence, not real-world causality*.
2. **CloudWatch logs and metrics** (spec: MUST; always-free allowance): app logs to CloudWatch Logs (short retention); custom metrics for LLM calls, tokens and run duration (≤10 metrics). Run details also shown in the app. (The EC2 status-check alarm moved to must-have 10.)
3. **Three-policy comparison** (spec: MUST): Strict / Flexible / Progressive under matched initial conditions; trade-off table, no single universal score.
4. **Versioned run artefacts** (replaces the spec's S3 + DynamoDB item): versioned CSR JSON, run manifests, results and finding indexes as extra tables in the **same SQLite store** as must-have 10, through the same storage interface. No second storage path.
5. **Agent inspector**: click an agent to see goals, constraints, memory and recent decisions.
6. **Observable strategy adaptation highlighted** (spec: MUST): mark the moment an agent changes strategy (e.g. Student A leaves earlier after week 3) and show it affecting later decisions.
7. **Behavioural-pattern discovery + novelty comparison** (spec: MUST): third discovery mechanism; flags unusual or recurring action sequences against prior runs.
8. **Full four-stage validation** (spec: MUST): schema, references, semantics (units, ranges, permissions, calculations), and an execution dry-run; invalid definitions returned for correction; validation status on the blueprint screen.
9. **Run manifest + replay mode** (spec: MUST): manifest of model/prompt/policy/CSR/engine versions, initial state, event schedule, proposals, validation results, committed actions; replay a recorded episode for inspection.
10. **Repeated runs** (spec: MUST): account for stochastic LLM decisions; show outcomes as distributions/episode traces, retain run IDs and action records for each.
11. **Scenario exploration loop** (spec: MUST): baseline + varied scenarios, 60% targeted / 40% random split (engineering starting point), outcome-based prioritisation, guided follow-up variations, LLM-proposed variations with evidence computed from records.
12. **Remaining disruption families** (spec: MUST): academic workload spike; timetable conflict / class cancellation; events that interact.
13. **Editing assumptions before approval** (spec: MUST): correct material AI assumptions on the review screen.
14. **SQS run queue + worker process on the same instance** (spec: MUST if async; SQS is always free up to 1M requests/month): replaces must-have 6's background thread. The UI puts a run on the queue; a worker process on the EC2 instance runs it, so a queued run survives a backend restart. UI polls run progress from the store and shows failed/incomplete runs. **Run each run once:** the worker claims the run with a conditional update (`status = running WHERE status = queued`) and deletes the message right after claiming; the run ID is the idempotency key, so a message that reappears after the visibility timeout is ignored instead of starting a second run (which would double the Bedrock spend).
15. **Full CSR and governed execution** (spec: MUST; *partly pulled into the build on 24 Nov by Level 2: a fixed building-block CSR with templates written by us, checked by a template check. Still not built: AI-generated definitions and the full 4-stage validation of them*): domain-independent Canonical Simulation Representation, versioned action contracts (preconditions, roles, resources, effects, conflict rule), snapshot-based decision phases, explicit recorded conflict resolution, model/prompt provenance, bounded concurrency, timeouts/retries, caching of interpretation.
16. **Final assessment dashboard sections** (spec: MUST): policy comparison, stakeholder impact, consequence findings, evidence and explanation, simulation timeline, run details.
17. **Extended product** (spec: NICE; *Level 2 ships two education templates, attendance and hostel curfew*): domain templates (education, transportation, public services, organisations, urban resource allocation); advanced ambiguity resolution with targeted questions; visual clause editor; larger agent populations; advanced long-term memory and reflection; sophisticated behavioural profiles; advanced multi-agent coordination and social interactions; behavioural calibration; more sophisticated environments (multiple courses/departments/institutions); complex resource networks; larger event catalogues; domain-specific environment modules; TPE / evolutionary search; contextual bandits; automated pattern clustering; advanced novelty detection; learned exploration strategies; advanced visualisations; exportable reports; uncertainty and sensitivity analysis; larger experiment batches; automated policy variation; advanced statistics (confidence intervals, variance); additional policy domains; custom environment builder; scalable/distributed execution; real-world validation with expert feedback and institutional data; SFT/DPO only if justified by validated data.

## Not doing
- Not predicting exactly what real people will do, and not deciding whether a policy is good or bad. The policymaker decides.
- No single universal policy score; we show trade-offs.
- The LLM does not enforce the policy, change authoritative state, or generate code that we execute. The CSR is declarative; no arbitrary LLM-generated Python.
- No SFT/DPO, contextual bandits or other model training in the MVP.
- No copying, modifying or incorporating PolicySim's public code without a confirmed licence or the maintainers' permission.
- No claim that RuleStorm is the first LLM policy-simulation platform.
- No claim of measured improvement for Indian students; impact is a potential benefit shown through a synthetic simulation unless we run a real pilot.
- No claim that temperature 0 guarantees identical fresh runs.
- No domains other than education in the MVP. (Both Level 2 templates are education-institution policies.)
- No AI-written templates (Level 3) and no template editor in this build.
- **No Streamlit** (team decision, 24 Nov 2026).
- **Only two services that spend credits: EC2 (one instance, with its EBS disk and Elastic IP) and Bedrock** (team decision, 24 Nov 2026). Other AWS services are used only if they are **always free** within our usage and actually help (see Technical decisions); usage above an always-free allowance is also paid from credits. **Not using**, because they spend credits or have no job in our design: S3, ECR, Secrets Manager, Lambda, Step Functions, API Gateway, Cognito, Amplify, load balancers, and DynamoDB as the store (see Storage decision). These were in our spec's AWS plan (MUST or NICE); they are dropped, not deferred.
- **No login, passcode or per-visitor rate limit** (team decision, 24 Nov 2026): the link is shared only with our team and the judges. The global daily cap and Budgets (must-have 10) cover runaway spend.
- **No AWS Organizations** linking our accounts: joining one ends an account's Free Tier credits immediately.
- No EKS, large fleets or provisioned model throughput.
- Not listing any AWS service in the Build Summary unless it is actually deployed.

## Evidence we have
All from our spec. None of it yet shows the size of the problem in India.

| Claim | Number | Source | Year |
|---|---|---|---|
| Problem evidence for Indian institutions (attendance rules, exception backlogs, students held ineligible) | `[MISSING]` | `[MISSING]` | — |
| LLM agents with memory, reflection and planning produced emergent social interactions in a simulated environment | 25 agents | Park et al., *Generative Agents*, ACM UIST, https://arxiv.org/abs/2304.03442 | 2023 |
| Agents built from interviews of real people replicated their General Social Survey answers 85% as accurately as the people replicated their own answers two weeks apart | 1,052 people; 85% | Park et al., https://arxiv.org/abs/2411.10109 ; Stanford HAI brief https://hai.stanford.edu/news/ai-agents-replicate-human-survey-responses | 2024 / 2025 |
| Survey of LLM-empowered agent-based modelling across social, physical, cyber and hybrid systems | — | Gao et al., *Humanities and Social Sciences Communications*, https://www.nature.com/articles/s41599-024-03611-3 | 2024 |
| Agent-based modelling can reveal policy side effects and nonlinear behaviour | — | *Complex System Policy Modelling Approaches for Policy Advice*, https://www.mdpi.com/2079-8954/12/8/302 | 2024 |
| Closest prior work: LLM multi-agent sandbox for proactive policy evaluation on social media | — | Huang et al., *PolicySim*, ACM Web Conference, https://arxiv.org/abs/2603.19649 | 2026 |
| Protocol for LLM-driven ABM: roles, round-based scheduling, validation checks, reason-action logs, replication records | — | Hu and Shen, *MASS*, https://arxiv.org/abs/2603.18003 | 2026 |
| Plausible-sounding agent behaviour is not evidence of operational validity | — | Larooij and Törnberg, *Artificial Intelligence Review*, https://link.springer.com/article/10.1007/s10462-025-11462-6 | 2025 |
| Standard Lambda max timeout | 900 s | https://docs.aws.amazon.com/lambda/latest/dg/configuration-timeout.html | — |
| AWS Free Tier credits for new customers | up to USD 200 over six months | https://aws.amazon.com/free/ ; problem statement p. 4 | — |

## Technical decisions (AWS, checked online 24 Nov 2026)
What the PS requires: "build and deploy on the AWS Free Tier", a live URL on AWS through Demo Day (17 Dec 2026). Facts below are from AWS's own pages; re-check in the console on day 1.

**Team decisions (24 Nov 2026):**
- **Minimum deployment:** one EC2 instance (+ disk + IP) and Bedrock are the only services that spend credits. Always-free services that help are added back (table below).
- **No Streamlit.** The frontend is served from the same EC2 instance; its framework is chosen in /build-plan.
- **"Free Tier" = anything free in AWS:** always-free allowances and anything covered by Free Tier credits both count.
- **Any AWS-hosted link the judges can open is acceptable.** We still put the free CloudFront HTTPS link in front (must-have 10) because browsers increasingly warn before opening plain-HTTP sites; the plain EC2 address is the fallback. No domain needed.
- **2–3 AWS accounts, one per teammate**, for more credits (see Account and credits). The link stays with our team and the judges.

### Account and credits
- **New accounts on the AWS Free plan** (accounts created after 15 July 2025 get the new Free Tier). The plan ends **after 6 months or when credits run out, whichever comes first**; then AWS **suspends the account** (data kept 90 days). A new account lasts well past 17 Dec, so **credit exhaustion is the only real threat to the live URL**. ([Free Tier terms](https://aws.amazon.com/free/terms/), [Free Tier FAQs](https://aws.amazon.com/free/free-tier-faqs/))
- **Credits: USD 100 at sign-up + USD 20 per activity, up to USD 100 more, per account.** Activities: launch an EC2 instance; use a model in the Bedrock playground; set up a cost budget in AWS Budgets; create a web app with Lambda; create an RDS database; create a DynamoDB table. Five of the six reach the USD 200 cap. In each account do EC2, Bedrock playground and Budgets (we need them), plus two of DynamoDB / Lambda / RDS just for the credit (create, then delete so nothing keeps running). ([Free Tier activities](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier-plans-activities.html), [Billing: Free Tier](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier.html))

**2–3 accounts (team decision, 24 Nov 2026).** AWS's rules that shape this:
- *"You are not eligible to receive Free Tier Credits for more than one account"* ([terms](https://aws.amazon.com/free/terms/)), and anyone who has ever held an AWS account is ineligible ([FAQs](https://aws.amazon.com/free/faqs/)). So **each account belongs to a different teammate**, created with **their own email, phone and payment card**, and only by a teammate who has never had an AWS account. Two accounts on one person's card or identity risk losing the credits or the account. Whether a reused card alone disqualifies is not stated officially (forum answers only).
- **Never join the accounts into an AWS Organization**: credits expire immediately ([FAQs](https://aws.amazon.com/free/faqs/)). Accounts stay separate; nothing is shared between them, and credits cannot be moved between them.

| Account | Owner | What runs there |
|---|---|---|
| **Live** | `[MISSING: teammate's name]` | Only the judged deployment (EC2 + Bedrock + always-free services). Nobody develops or experiments here, so its credits go only to the live link through 17 Dec. |
| **Dev 1** (and **Dev 2** if a third teammate qualifies) | `[MISSING: teammates' names]` | Each owner's own development, the model bake-off, test runs and three-policy comparison experiments. Also the **standby**: the same deploy script can bring the app up here if the live account fails. The link would change (Elastic IP and CloudFront belong to one account), so use standby only in an emergency, and never during the Round 1 judging window (30 Nov–5 Dec). |

- **One setup script, run per account**: Region, Bedrock model access, IAM role and users, Budgets alert, CloudFront. Each account needs its own Bedrock model access and its own Budgets alert.
- **Access without shared keys**: every teammate signs in to the account they use with `aws login` and a named profile (for example `rulestorm-dev`). It opens the browser and gives temporary credentials (12 hours, renewable for 90 days), so there are **no access keys** on laptops or in the repo. Our first account signs in as `AccountFullAccessRole`, the new experience's own role, not root keys. Teammates who own no account get their own sign-in to the owner's account, never a shared login. On EC2 the instance role replaces all of this.
- **Keys never reach the repo**: `.env*` in `.gitignore` from the first commit; a secret scan (gitleaks or git-secrets) as a pre-commit hook before the repo is made public; delete all access keys after Demo Day. A leaked key in a public repo is the fastest way to drain an account's credits.
- **Plan choice (open, our call).** Since anything covered by credits counts as free, either plan is allowed:
  - **Free plan:** cannot overspend, but no cross-Region inference, and the account is suspended (URL down) if credits run out.
  - **Paid plan with the same credits:** unused credits carry over and the account is not suspended when they run out, but anything beyond credits is billed to the card. It allows cross-Region inference, so Claude models become usable from Sydney through Geo or Global profiles.
  - Upgrading Free → Paid is possible at any time; Paid → Free is not. **Start every account on the Free plan**, and upgrade only if the model bake-off shows the in-Region models are not good enough. The plan is chosen per account, so a Dev account can test a Paid-plan model without touching the live account.

### What the Free plan allows (and blocks)
- **Blocked for every service: "Multi-Region or cross-Region features."** So **no Bedrock cross-Region inference profiles** (no `global.`, `apac.` or `au.` profiles). Only models with **in-Region** support in ap-southeast-2 can be used. ([Free plan service list](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html))
- **Included:** EC2 (+ EBS), Bedrock, S3, DynamoDB, SQS, CloudWatch + Logs, IAM, Budgets, ECR, Lambda, API Gateway, Amplify, Elastic Beanstalk, Lightsail, CloudFront, Route 53, ACM, ELB, ECS. AWS Marketplace limited to "Bedrock and Free only".
- **Not available:** App Runner (not listed, so treat as unavailable), Bedrock AgentCore (Paid-plan only per the Free Tier page), Lambda@Edge, IAM Identity Center, DynamoDB Accelerator, Kinesis, Redshift, Textract/Transcribe/Translate.

### Region: Sydney (ap-southeast-2), fixed by the account (24 Nov 2026)
The first account was created on the **new AWS experience**, which gives it **ap-southeast-2 (Sydney)** as its project Region. Regional resources (EC2, Bedrock) go there. This replaces our earlier Mumbai plan. Latency from India is higher (roughly 150 ms more per request), which doesn't matter for this app. The Bedrock calls are made from the instance in Sydney, not from the browser. Each later account will be checked the same way when it's created.

### Bedrock model (in-Region Sydney only)
These are **checked live against our account** on 24 Nov 2026 with `aws bedrock list-foundation-models --region ap-southeast-2 --by-inference-type ON_DEMAND`, a read-only call that costs nothing. Sydney prices come from [Bedrock pricing](https://aws.amazon.com/bedrock/pricing/). Prices marked * were read from a summary of the page, not quoted directly.

| Model | Model ID in Sydney | Sydney price per 1M tokens (in / out) | Notes |
|---|---|---|---|
| **Mistral Large 3** | `mistral.mistral-large-3-675b-instruct` | USD 0.515 / 1.545 | Was the default; too slow on our account in the day-0 smoke test (below). |
| **DeepSeek V3.2** | `deepseek.v3.2` | USD 0.6386 / 1.9055 | **Default since the day-0 smoke test (team choice, 24 Nov).** |
| **Moonshot Kimi K2.5** | `moonshotai.kimi-k2.5` | USD 0.618 / 3.09 | |
| **Qwen3 235B A22B 2507** | `qwen.qwen3-235b-a22b-2507-v1:0` | USD 0.2266 / 0.9064 * | Cheap; worth a bake-off slot. |
| **OpenAI gpt-oss-120b** | `openai.gpt-oss-120b-1:0` | USD 0.1545 / 0.618 * | Cheapest; weaker at long structured output (to test). |
| **Amazon Nova Pro** | `amazon.nova-pro-v1:0` | not found on the page | AWS's own model. |

**No Claude model runs in-Region in Sydney.** Claude (Sonnet/Opus/Haiku 4.x–5.5, Fable/Mythos), Nova 2 Lite, Kimi K3 and GPT-6.x are available from Sydney only through Geo (`au.`/`apac.`) or Global inference profiles, which the Free plan blocks. They are usable only on a Paid plan.

**Decision:** write one thin model adapter (`decide(prompt, schema) -> JSON`) so the model is a config value. **Default: DeepSeek V3.2 on bedrock-runtime Converse** (in-Region; chosen over Mistral Large 3 after the day-0 smoke test showed Mistral at 13–84 s per call). Store the chosen model ID in the run manifest.

**Unverified, so check before writing engine code:** whether each candidate handles the Converse API and long structured JSON reliably was not checked. Converse support was read from translated copies of the compatibility table. Our account has model access listed for all candidates above, but a real call is the proof; some models may still ask for a one-time access or Marketplace step, and the Free plan allows only "Bedrock and Free" Marketplace items.
- **Day-0 smoke test (first thing, in a Dev account):** one script calls each candidate once, first from a laptop using the `aws login` profile and later from the EC2 instance using its IAM role. It prints success, auth method, latency, a blueprint-sized call's output tokens and time, and the model's requests-per-minute and tokens-per-minute quotas.
- **Day-1 bake-off (Dev account):** run 20 agent decisions and 3 blueprint generations each on Mistral Large 3, DeepSeek V3.2 and Qwen3 235B. Keep whichever passes the Pydantic schemas most often at an acceptable cost and latency.
- **Do not depend on tool use.** Ask for JSON in the prompt, validate with Pydantic at the boundary, retry once with the validation error in the prompt, then fall back to a safe "no action" decision that the engine records as such.
- Record the results here, per model: JSON reliability, tool use, auth method, latency. Bake-off: `[MISSING: bake-off results]`

**Day-0 smoke test results (24 Nov 2026, laptop, `auth: profile=rulestorm-dev`, ap-southeast-2, `python -m rulestorm.cli llm smoke --model <id>`, read timeout 120 s, no boto retries).** "Tiny" = a 10-token JSON reply; "blueprint" = a ~590-token prompt asking for a blueprint-sized JSON (4 students, 3 disruptions, 5 facts, 5 assumptions), checked with Pydantic.

| Model | Runs | Tiny call (s) | Blueprint call (s) | Blueprint output tokens | Blueprint JSON valid | Quota: requests / tokens per minute |
|---|---|---|---|---|---|---|
| Mistral Large 3 | 5 | 16.8–84.0 (Bedrock's own `latencyMs` 11–18 s on a 10-token reply) | 13.0–65.1; one ReadTimeout at the 25 s default | 475–518 | yes (4/4 that finished) | 100 / 100M |
| DeepSeek V3.2 | 3 | 1.9–2.3 | 7.9–9.0 | 418–476 | yes (3/3) | 100 / 100M |
| Qwen3 235B A22B 2507 | 3 | 1.7–1.8 | 3.8–4.1 | 296–321 | yes (3/3) | 100 / 100M |
| Moonshot Kimi K2.5 | 1 | 5.7 | 12.6 | 442 | yes (1/1) | 100 / 100M |
| Amazon Nova Pro | 1 | 1.9 | 2.8 | 429 | yes (1/1) | **13** / 1M (on-demand) |
| OpenAI gpt-oss-120b | 1 | 2.5 | not reached | — | tiny reply cut off at the 50-token cap (`{"`), so not a fair test | — |

All calls passed through the adapter (`rulestorm/llm.py`), so JSON-in-prompt plus Pydantic works on every model tried. Tool use was not tested (not needed). The instance-role run (`auth: instance-role`) is still to do, in slice 11.

**Cost check (our estimate, not measured):** if one agent decision is about 2,000 input + 300 output tokens, DeepSeek V3.2 in Sydney costs about USD 0.0018 per call, so a 150-call run is about USD 0.28 and 100 runs about USD 28 (Mistral Large 3 would be about USD 0.22 and USD 22). Measure the real token counts in the first run and set the per-run call cap and the global daily cap from that.

**Slice 6b checkpoint: first real runs (24 Nov 2026, laptop, DeepSeek V3.2, `python -m rulestorm.cli run local --blueprint B-883733cf`).** Blueprint from the example input: admin capacity 3 a week (AI assumption), 90-min rail delay for the commuter in week 3, storm for all four students in week 6, office down to 1 in week 7, checkpoint week 8.
- **Run duration:** 20–54 s per whole term (target was under 5 min). 13 decisions and 14–17 model calls per run (a few first replies needed the validation retry), 0 errors, 0 timeouts, cap never reached.
- **Tokens:** about 700 in and 130 out per call, 9–11k in and about 2k out per run, so far below the 2,000 + 300 estimate above. The per-run cap of 150 leaves about 10× headroom.
- **Request pending at the checkpoint (the hero condition): 0 of 6 runs.** Runs 1–3: students asked for an exception for that day's class before it took place; the engine correctly refused, but the agent was not told, and several then said "I already submitted" and never filed. Fixed (agents now see what became of their last actions and which absences no request covers; facts only, nothing tells them to file). Runs 4–6: agents understood the refusal; 2 of 3 runs filed one request in week 6 (one approved, one rejected because a covered session had been attended), processed the same week. With capacity 3 a week and at most one request, no queue formed.
- **Reasons fit the profiles:** yes, read by hand in all 6 logs. The commuter cites travel fatigue and the train, the working student the fixed shifts, the family student keeping slack for care emergencies, the resident high grades; the advisor warns the commuter at 80% and 81.8%. Students well above 80% mostly chose not to file for a single absence.
- **3 fresh blueprints from the same example input (B-3b330bf8, B-3b358000, B-6aaa9be6), one run each: 0 of 3.** Every blueprint again set capacity 3 a week (the AI reads "only a few a week" as 3) with 2–3 disruptions, each hitting one class. One request was filed in 3 runs, approved the same week. All students ended at 87.5–100%, all eligible. **Total: 0 of 9 real runs.**
- **Why, from the logs:** a disruption costs each affected student one class, so a student loses at most 1–2 of 16 and stays far above 80%. Students that far above the line rarely file, and 3 a week clears the few requests that come in. The agents behave plausibly; the example input, as the AI reads it, does not create enough absences or a small enough office for a backlog.
- **Option A, harsher environment text (test policy P-aadd0cb8, blueprint B-06d7d674, run L-d15b4469): 0 of 1.** "Strikes can last several weeks" and "one or two requests a week" still gave only 2 transport disruptions and capacity 2; the worst student ended at 87.5% with 1 request. So the plausible-scenario reading itself is the limit, not the wording.
- **Slice 6c stress variants from the unchanged example (parent B-3b330bf8), 6 variants, one run each: the policy broke in 1 of 6; the exception-backlog chain appeared in 0 of 6.** The first 3 variants (2–3 disruptions each) all held. After the prompt was told the engine's counting rule (at 80% and week 8, 4 unexcused absences break eligibility; worked out from the blueprint's own values), the AI proposed "Early checkpoint bottleneck" (B-868a538c, run L-b0631988): a 3-week strike in weeks 1–3, checkpoint week 3. **The commuter (60%) and the working student (50%) were ineligible at the checkpoint although every absence came from the strike.** From the log: both filed on the day of each disruption, before the class had happened, and were refused; the working student's request for classes 1 and 3 was refused whole because class 3 had not happened yet, and they never refiled class 1 alone; only 1 request was approved. Capacity (3 a week) was never the limit, so no queue formed. This is an objective failure (must-have 7), with a `caused_by` chain from the strike to each eligibility evaluation, not the bottleneck chain.
- **Slice L8 stress variants on the general engine (parent B-6b40a68b, the 6b scenario), 3 variants, one run each: broke the policy: 1 of 3.** The prompt now carries the misses that fail the check and the queue maths, both worked out from the template. "Severe Office Backlog with Multiple Disruptions" (B-462c9396, run L-9e90555f: office capacity 1 a week, an outage in week 3, flooding and rail failures in weeks 4–6) **filled the exception queue: requests were held every week from 4 to 9, and 2 (the commuter's and the working student's) were still pending at the week-8 check.** Both stayed eligible (86.7% and 92.9%), so this is the bottleneck chain (must-have 7), not an objective failure. The other two variants (early checkpoint at week 5; late checkpoint with cancellations) held.
- **Slice L9d: a real hostel curfew policy ran end to end on the same engine.** The template's example policy became `hostel_curfew@1` in 40–44 s (three tries, no retry). Its approved blueprint (B-11eb423f) ran a full 8-week term (run L-692db8f4) **in 34.2 s, 19 model calls, 0 errors**, with decisions only by the residents, the guardian and the warden. When a 45-minute transport delay hit four residents, three asked for late entry and the guardian consented and the warden approved all three on the same night, before security recorded it.
- Event logs: `runs/L-*.json` on the laptop that ran them (not committed).

**Credit runway (live account, do on day 1):** (instance hourly price × hours from launch to 17 Dec) + Elastic IP (USD 0.005/hr) + EBS disk + Bedrock budget for judging and Demo Day, compared with the credits the live account actually received. `[MISSING: runway estimate]`. Development and experiments spend Dev-account credits, not this.

### The deployment (everything we deploy)
**Spends credits (the minimum):**

| Piece | What | Why it is the minimum |
|---|---|---|
| **Amazon EC2** (+ its EBS disk) | One Free-plan-eligible instance in ap-southeast-2 running the backend (simulation engine, validators, Bedrock calls), the background run worker, the frontend and the SQLite store on its EBS disk | The PS needs a live link hosted on AWS; one box does it all, and long simulation runs have no request timeout to fight |
| **Elastic IP** | Fixed public address for that instance | The instance's address and public DNS name (CloudFront's origin) stay the same after a stop/start until Demo Day |
| **Amazon Bedrock** | LLM for the blueprint and agent decisions | The product needs an LLM; Bedrock is AWS's own and needs no outside API key |

**Always free within our usage (no credits), added back because they help:**

| Service | Free allowance per month | What it does for RuleStorm | Stay-free rule |
|---|---|---|---|
| **Amazon SQS** (nice-to-have 14) | 1M requests ([pricing](https://aws.amazon.com/sqs/pricing/)) | Run queue between the UI and the worker; queued runs survive a restart | Long polling (20 s) keeps one idle worker around 130k requests/month; claim-once rule in nice-to-have 14 |
| **Amazon CloudWatch** | 5 GB logs, 10 custom metrics, 10 alarm metrics, 3 dashboards; EC2 metrics sent free ([pricing](https://aws.amazon.com/cloudwatch/pricing/)) | App and worker logs; LLM-call/token/run-duration metrics; EC2 status-check alarm on the live link | Log retention 7 days; ≤10 custom metrics; ≤10 alarms |
| **Amazon SNS** | 1M publishes, 1,000 email deliveries ([application integration](https://aws.amazon.com/free/application-integration/)) | Emails us when the CloudWatch alarm fires | A handful of emails |
| **AWS Systems Manager** | Parameter Store standard parameters and Session Manager on EC2: no charge ([pricing](https://aws.amazon.com/systems-manager/pricing/)) | Parameter Store holds the model ID, the per-run and global daily call caps and budgets so we change them without redeploying; Session Manager gives a shell on the instance with no SSH key or open port 22 | Standard parameters only (advanced cost USD 0.05 each) |
| **AWS Budgets** | Monitoring and notifications free ([pricing](https://aws.amazon.com/aws-cost-management/aws-budgets/pricing/)) | Email alert on credit spend in every account; also earns a USD 20 credit activity. Optional (about 10 minutes of console setup, no code): an action-enabled budget that attaches an IAM policy denying `bedrock:InvokeModel*` to the instance role at a threshold, so Bedrock stops but the instance and link stay up. Never use a budget action that stops EC2 | Plain budgets; the first 2 action-enabled budgets are also free. Budget figures update a few times a day, not live, so the daily cap in the app is the real guard |
| **IAM role** | Free (IAM's page shows no price) | Lets the instance call Bedrock, SQS, CloudWatch and Parameter Store with no keys in code | — |
| **Amazon CloudFront** (must-have 10) | 1 TB out, 10M requests ([pricing](https://aws.amazon.com/cloudfront/pricing/pay-as-you-go/)) | The HTTPS `*.cloudfront.net` link the judges get, in front of the instance, so browsers show no "not secure" warning | Origin = the instance's EC2 public DNS name (CloudFront takes a DNS name, not an IP); caching off for the app's API paths; origin timeout above our slowest request; UI polls (no websockets). Fallback: submit the EC2 address |

Caveats: AWS's pages say "always free on the Free and Paid plan" explicitly for SQS, SNS and CloudFront. For CloudWatch, Systems Manager and Budgets the free allowance is on the pricing page but the plan wording is not stated. Whether a CloudWatch alarm's EC2 recover/reboot action costs anything is not stated; we only use an email alarm. Anything above an allowance is paid from credits, so set the Budgets alert first and check Billing → Free Tier usage after day 1.

**Free but no job in our design (not added):** Lambda (1M requests), Step Functions (4,000 transitions), EventBridge Scheduler (14M invocations), DynamoDB (see below; a table may be created and deleted once per account only for the USD 20 credit activity).

### Storage decision: SQLite on the instance, not DynamoDB (24 Nov 2026)
We checked whether DynamoDB's free allowance restricts our use case. It does:
- **Our reads are relational and analytical:** following an evidence chain is a walk over cause → effect links between events; the policy comparison, counterfactual and novelty detection compare whole runs; the analysis engine uses Pandas. DynamoDB is a key-value store, so each of these becomes "load the whole run into memory, then work in Python", plus hand-built indexes.
- **The free capacity is small for that:** 25 write and 25 read units in total per Region, shared by every table and secondary index. A write unit covers 1 KB, so a decision item with memory and context costs several units; loading a run of about 1,000 items of about 1 KB needs about 125 read units, so with 25 per second it relies on burst capacity, or the evidence view waits several seconds. Console defaults can also pick on-demand mode (no free allowance) or turn on auto scaling above 25.
- **Items are capped at 400 KB**, so traces must be split.

**SQLite on the instance's EBS disk** has none of these limits, costs nothing beyond the disk we already pay for, answers evidence chains with one SQL query (recursive CTE), and Pandas reads it directly. It also gives one storage path: the same backend in tests (a temporary file) and on the instance.
- **Rules:** one storage interface in the code; WAL mode so the web process and the run worker can share the file; the whole app stays on this one instance anyway.
- **Cost of the switch:** data lives on one disk. The demo runs are safe because must-have 9's seeded run is a JSON fixture in the repo, restored with one command. If the instance is lost, re-run the deploy script and restore the fixture. Optional: an EBS snapshot before submission (small credit cost).
- **What we give up:** DynamoDB in the Build Summary. Services used stay real and explained: EC2 + EBS, Bedrock, CloudFront, CloudWatch, SNS, Systems Manager, Budgets, IAM (+ SQS if nice-to-have 14 ships).
- This reverses our spec's "the live demo must not depend on the EC2 local filesystem" (written for the S3 + DynamoDB plan, now superseded).

### Instance, link and release
- **EC2 Free-plan-eligible types (checked live in ap-southeast-2, 24 Nov 2026, `aws ec2 describe-instance-types --filters Name=free-tier-eligible,Values=true`):** t3.micro, t3.small, t4g.micro, t4g.small, t8i.micro, t8i.small, t9g.micro, t9g.small, c7i-flex.large, m7i-flex.large. On the new plan **EC2 is paid from credits** (no 750-hour allowance listed). Start with **t3.small or t4g.small**; hourly Sydney prices could not be read online, so read them in the console before launching. ([Free Tier compute](https://aws.amazon.com/free/compute/)) **Launch t3 in "standard" CPU credit mode** (new t3 instances default to unlimited, which bills USD 0.05 per vCPU-hour of surplus CPU from credits), or use t4g with the same setting.
- **Public IPv4 / Elastic IP: USD 0.005 per hour**, in use or idle, about USD 3.60 per 30 days. ([VPC pricing](https://aws.amazon.com/vpc/pricing/))
- **The link:** the CloudFront `https://…cloudfront.net` address (submitted), with `http://<elastic-ip>` / the `ec2-…amazonaws.com` name on port 80 as the fallback. No domain.
- **Freeze the judged link:** tag the submitted version in git; **no deploys to the live account from 30 Nov to 5 Dec** (Round 1 judging, time unknown); a one-command deploy script that can put the tagged version back on the instance. New work is tested in a Dev account first. The status-check alarm (must-have 10) tells us if the link dies.
- **Data transfer:** 100 GB/month out is free, aggregated across services; our traffic is far below that.
- **Conflict with /kickoff:** it scaffolds Next.js and deploys to **Vercel**. A Vercel URL is not hosted on AWS. If we use /kickoff, skip its Vercel deploy and serve the built frontend from the EC2 instance.
- **Build Summary angle:** two services spend credits (EC2, Bedrock); everything else runs inside always-free allowances. That is a design choice worth stating: one instance keeps long runs uninterrupted and holds the event store next to the engine, Bedrock keeps inference in-Region in Sydney, CloudFront gives the judges an HTTPS link, CloudWatch and SNS watch the live link, Parameter Store and Budgets cap spend, all at no credit cost; a separate live account keeps development spend away from the judged link.

## Our notes (kept as written)
Everything from our spec that did not fit above, tightened. The full original stays in `Idea+PS/`.

### Product definition
RuleStorm is a general-purpose, AI-powered policy-testing platform that simulates how policies affect stakeholders, how stakeholders react and adapt, and how their interactions may produce unintended consequences. A policymaker submits a proposed policy, its intended purpose and information about the environment. RuleStorm builds a simulated environment of AI stakeholder agents, each with its own objectives, priorities, constraints, information, resources and behavioural tendencies. Agents make decisions, interact, respond to events and adapt over simulated time. The system explores different circumstances, identifies significant outcomes, and reveals unintended adaptations, conflicting interests and operational consequences. It helps decision-makers investigate plausible consequences before implementation.

**Core capabilities:** (1) AI-driven stakeholder modelling, (2) adaptive behavioural simulation, (3) emergent consequence discovery, (4) AI-guided scenario exploration, (5) inspectable policy outcomes, (6) comparative policy testing, (7) human-controlled policy evaluation.

**Priority levels:** MUST HAVE (MVP) = everything needed to demonstrate the complete concept in one educational environment, limited scale but full functionality. NICE TO HAVE (extended) = scale, sophistication, validation, automation and domain coverage.

### Key design rules
- The policy interpretation is converted into a structured representation before execution. An LLM must not enforce the policy during simulation.
- Agents must make decisions, not merely generate opinions about the policy.
- The environment is deterministic for formal rules and calculations; agent behaviour stays flexible.
- Agents must show an observable change in strategy, and that change must affect later decisions.
- Student agents differ because of their circumstances, not just personality prompts. They are synthetic operational profiles.
- Events should be able to interact; the engine must not assume every disruption produces a predefined outcome.
- Agents propose; the engine validates and executes. Agents cannot directly modify authoritative state.
- An agent's generated reason is kept as its stated rationale, not as a verified explanation of its internal reasoning.

### MVP scope ("RuleStorm Education Stress Tester")
| Dimension | MVP scope |
|---|---|
| Institution | One synthetic institution |
| Courses | One |
| Agents | Eight stakeholder agents |
| Students | Four archetypes |
| Simulated period | Ten weeks |
| Class schedule | Two sessions per week; 20 planned sessions |
| Policy alternatives | Three |
| Scenario families | Four |
| Canonical model | One validated education CSR configuration |
| Definition validation | Four stages: schema, references, semantics, execution dry-run |
| Discovery mechanisms | Three: objective failures, operational bottlenecks, behavioural patterns |
| Counterfactual | At least one finding investigated through a controlled matched rerun |
| Reproducibility | Run manifest, recorded decisions and replay |
| Runtime limits | Explicit per-experiment run and LLM-call budgets |

### Student agents
| Agent | Goals | Constraints | Relevant behaviour |
|---|---|---|---|
| A — Long-distance commuter | Maintain attendance and eligibility | Long commute | Can change departure times and travel strategies |
| B — Campus resident | Maintain academic progress | Academic workload | More flexibility in travelling to class |
| C — Working student | Maintain eligibility and employment | Fixed working hours | Cannot freely change the schedule |
| D — Family commitments | Complete academic requirements | Limited schedule flexibility | Balances family and academic responsibilities |

### Institutional agents
| Agent | Goals | Constraints |
|---|---|---|
| Faculty member | Maintain participation and academic progress | Limited rescheduling capability |
| Academic advisor | Help students address attendance difficulties | Limited appointment capacity |
| Attendance administrator | Process attendance corrections and exceptions | Limited processing capacity |
| Examination officer | Apply eligibility rules correctly | Must follow approved policy |

Agent choices vs environmental facts: students decide whether to attend, modify schedules, request assistance or seek exceptions; faculty decides whether to offer alternative sessions; advisors decide whether and how to intervene; administrators process exception requests according to policy and capacity; examination officers evaluate eligibility from authoritative records, and the final eligibility decision is computed by the engine from approved rules.

### Policy alternatives
- **A — Strict:** 80% per-course attendance, with formally approved exceptions.
- **B — Flexible:** 80%, with defined provisions for institutional disruptions and verified exceptional circumstances.
- **C — Progressive support:** 80%, with early warnings and advisor interventions before eligibility is determined.

### Disruption catalogue
| Scenario | Environmental change | What it tests |
|---|---|---|
| Transport disruption | Unexpected commute delays | Different stakeholder flexibility |
| Academic workload spike | Increased academic workload | Conflicting commitments |
| Timetable conflict / class cancellation | Schedule or class availability changes | Institutional adaptability |
| Administrative capacity crunch | More requests, processing constraints | Operational bottlenecks |

### Education model (minimal CSR)
- **Entities:** student, course, class session, faculty member, advisor, attendance administrator, examination officer, exception request.
- **State variables:** attendance records, timetable, request status, staff capacity, agent resources, current strategy.
- **Actions:** attend class, modify schedule, request assistance, request exception, offer alternative session, process request, intervene, evaluate eligibility.
- **Events:** class scheduled, class cancelled, transport disruption, workload spike, request submitted, evidence requested, request approved/rejected, queue capacity reached, eligibility assessed.
- **Constraints/permissions:** e.g. students cannot modify attendance records or approve their own exceptions.
- **Calculations/metrics:** attendance %, eligibility, request queue length, processing delay, stakeholder outcomes.
- **Attendance formula:** Attendance % = sessions attended ÷ countable completed sessions × 100. Approved exceptional sessions and cancelled institutional sessions are excluded from the denominator. Pending or rejected exceptions count as absences until resolved.

### Canonical Simulation Representation (CSR)
The internal, domain-independent contract between generated environment definitions and the engine. The LLM does not create a new engine or executable code per domain; it generates a validated declarative model that conforms to the CSR. Minimum contents: entities, typed state variables (initial values, units, valid ranges), relationships, actions (actors, targets, parameters), events, constraints and role permissions, state transitions, deterministic calculations, metrics. Stable internal IDs and canonical types; the presentation layer maps them to domain terms. Every generated definition is versioned. Every state-changing action has an execution contract (preconditions, permissions, resource requirements, effects). Build it for reuse, but only the education configuration is implemented and validated in the MVP.

### Generated-definition validation (four stages)
1. **Schema:** required fields, types, structures, unique IDs, schema versions.
2. **References:** referenced agents, entities, variables, events, actions and metrics exist.
3. **Semantics:** units, valid ranges, dependencies, role permissions, action preconditions, constraints, calculation compatibility.
4. **Execution:** a dry-run/test episode checks transitions and calculations run without violating invariants.

Structurally valid JSON is not enough. Invalid definitions go back for correction, never to the engine.

### Governed execution cycle (per decision phase)
1. Capture a consistent snapshot of the environment.
2. Identify only the agents affected by the event; give them the relevant snapshot and information.
3. Get structured action proposals; all decisions in one phase use the same snapshot.
4. Validate permissions, preconditions, constraints and resources.
5. Resolve conflicts with explicit, recorded rules (e.g. FIFO queue by submission timestamp with a stable ID tie-break; role/policy priority for resource allocation), never by agent-loop order.
6. Commit accepted actions to authoritative state.
7. Record state changes and events; update affected agents' memory.

Routine state updates and calculations need no LLM calls.

### Discovery engine
A distinct subsystem that consumes recorded outcomes. It does not rely only on an LLM reading logs or on a predefined list of failure stories.
- **Objective-failure discovery:** intended objectives not achieved or stakeholder outcomes deteriorate.
- **Operational-bottleneck discovery:** overloaded queues, resource shortages, delays, process constraints.
- **Behavioural-pattern discovery:** unusual or recurring strategies, action sequences and interactions not prescribed as findings.

MVP implementation: deterministic metrics, queue analysis, event-sequence analysis, basic novelty comparison. LLMs may label or explain candidates; evidence comes from the recorded simulation. Discovery loop: (1) generate baseline and varied scenarios, (2) run, (3) measure objectives, (4) detect shortfalls and disparities, (5) detect bottlenecks, (6) detect unusual/recurring sequences vs earlier runs, (7) generate targeted variations around findings, (8) rerun to see if the mechanism persists. Start at 60% targeted / 40% random; this is an engineering starting point, not a proven optimum or trained model. Keep random exploration so the system does not only find risks it already recognises.

### Facts, interpretations and counterfactuals
Every finding separates: recorded events; environment changes (accepted transitions); calculated outcomes; observed patterns; AI interpretations; further hypotheses. Every finding links to supporting event IDs, agent decisions, validation results, state changes and calculations. A counterfactual changes one condition while matching other starting conditions and external events (e.g. more admin capacity: does the exception queue still cause eligibility risk?). Repeat matched runs where practical; compare as distributions or episode-level traces. It tests a mechanism within the model, not causality in a real institution.

### Reproducibility, provenance, replay
Run manifest (minimum): run ID and timestamp; model provider/version and generation parameters; prompt and agent-definition versions; policy, CSR/environment and engine versions; initial agent/environment state; external event schedule; configuration and exploration settings; agent proposals, validation outcomes and committed actions. Two modes: **experiment** (fresh decisions) and **replay** (recorded decisions/events replayed for inspection and debugging). Do not rely on temperature for reproducibility.

### Runtime efficiency and API controls (MVP engineering requirements)
Invoke agents at meaningful decision events, not every time step; involve only affected agents; compact memory summaries and structured context; bounded concurrency with timeouts/retries; cache repeated policy/environment interpretation; explicit max runs and LLM calls per user-triggered experiment; deterministic code for calculations, validation and transitions. The UI shows run progress and any failed or incomplete run.

### Technical architecture
| Component | Responsibility | Suggested implementation |
|---|---|---|
| Policy modeller | Interpret policy, generate structured policy definitions | LLM API + Pydantic |
| Environment modeller | Generate education CSR config and assumptions | LLM-assisted generation + Python config |
| CSR validator | Validate schemas, references, units, dependencies, permissions, calculations | Pydantic + custom Python validators |
| Stakeholder framework | Agent goals, memory, observations, decisions | LLM + structured agent state |
| Simulation engine | Schedule events, validate actions, resolve conflicts, commit transitions | Custom Python event engine |
| Discovery engine | Detect failures, bottlenecks, patterns; guide exploration | Python metrics/event analysis + LLM-assisted variation/explanation |
| Analysis engine | Outcomes, run comparison, evidence-grounded explanations | Python + Pandas + LLM |
| Frontend | Policy input, blueprint review, simulation, results dashboard | ~~Streamlit~~ → not Streamlit; framework chosen in /build-plan, served from the EC2 instance |
| Persistence | Policies, CSR versions, agents, events, manifests, outcomes | SQLite on the EC2 instance's EBS disk, one storage interface, same backend in tests (~~S3~~ dropped 24 Nov: uses credits; ~~DynamoDB~~ dropped 24 Nov: free capacity and key-value model restrict evidence chains and run comparison) |

Stack (spec, updated 24 Nov): Python, Pydantic, Amazon Bedrock, SQLite, Pandas, Plotly; SQS if nice-to-have 14 ships. Streamlit and DynamoDB removed.

```python
Agent:         id, role, goals, constraints, resources, knowledge,
               behavioural_tendencies, memory, current_strategy, available_actions
AgentDecision: action, target, parameters, reason, required_information, strategy_update
ActionContract: action_id, allowed_roles, preconditions, required_resources, effects, conflict_rule
```

Architecture requirements (spec: MUST): modular separation of policy, environment, agent, simulation and analysis; education rules kept separate from the reusable engine; common schemas for agent state, observations, decisions, actions; reusable simulation core independent of one policy; versioned contracts; model and prompt provenance; runtime controls.

### Results dashboard
| Section | Content |
|---|---|
| Policy comparison | Attendance, eligibility, admin workload and other outcomes, with repeated-run variation |
| Stakeholder impact | Individual agent outcomes and behavioural adaptations |
| Consequence findings | Objective failures, operational bottlenecks, unexpected behavioural patterns |
| Evidence and explanation | Linked event IDs, state changes, calculations, interpretations, counterfactual results |
| Simulation timeline | Events, decisions, validation outcomes, conflict resolution, institutional responses, state changes |
| Run details | Run manifest, model/config versions, replay access |

### MVP completion criteria (from our spec)
- [ ] Natural-language policy + education environment produce a versioned CSR definition.
- [ ] User-provided facts and AI assumptions are visibly distinguished.
- [ ] Generated definitions pass schema, reference, semantic and execution validation before use.
- [ ] Eight agents have distinct goals, constraints, resources, information and memory.
- [ ] Agents make structured, event-triggered decisions that adapt based on previous events.
- [ ] Simultaneous decisions use consistent snapshots; conflicts resolved by explicit rules.
- [ ] Agents cannot directly modify authoritative state.
- [ ] Attendance, exceptions, queues and eligibility are calculated by the engine.
- [ ] Discovery separately identifies objective failures, operational bottlenecks and behavioural patterns.
- [ ] At least one finding is linked to actual event records, state changes and calculations.
- [ ] At least one controlled counterfactual is completed and labelled within-model evidence.
- [ ] Run manifests capture what is needed to inspect and replay an episode.
- [ ] Runtime controls enforce bounded concurrency and run/LLM-call limits.
- [ ] The three policies can be compared under matched conditions and repeated runs.

**MVP success criterion:** show that an ordinary-language policy and environment description becomes a validated, versioned simulation model; AI stakeholders make constrained, adaptive decisions in a governed environment; interactions produce inspectable outcomes; separate discovery mechanisms find a noteworthy consequence; and RuleStorm can investigate it with a controlled within-model counterfactual and compare alternative policies under matched conditions.

### Sample MVP run (illustrative, not measured data or a prediction about a real university)
**Policy:** "Students must maintain at least 80% attendance in each course to be eligible for examinations. Exceptional circumstances may be considered through formally approved exceptions." **Purpose:** improve class participation, encourage consistent attendance, maintain academic standards. **Environment:** one institution, one course, four student archetypes, four institutional agents. **Priority outcomes:** attendance, eligibility, stakeholder impact, administrative workload.

**Blueprint:** minimum 80%, per course; formally approved exceptions; eligibility from authoritative records; 8 stakeholders; 2 sessions/week, 20 sessions, 10 weeks; outcomes = attendance, eligibility, exception requests, processing delays, stakeholder differences, behavioural adaptations. User approves.

**Initialisation:** Student A plans to leave 30 minutes before class; Student C has fixed work hours; the administrator has limited exception-processing capacity.

| Period | Event | Decisions and consequences |
|---|---|---|
| Weeks 1–2 | Normal operation | Students attend per initial strategies |
| Week 3 | Transport disruption | A leaves earlier; C cannot easily adapt due to work |
| Week 4 | Behavioural adaptation | A changes travel buffer; C requests advisor help |
| Week 5 | Further disruption | C submits a documented exception request |
| Week 6 | Capacity constraint | Administrator gets more requests than capacity; request stays pending |
| Weeks 7–8 | Further interactions | Advisor supports C; A keeps attendance via revised strategy |
| Weeks 9–10 | Eligibility assessment | Examination officer evaluates using policy and current records |

| Student | Attended | Approved exceptions | Final attendance |
|---|---:|---:|---:|
| A — Commuter | 18 | 0 | 90% |
| B — Resident | 19 | 0 | 95% |
| C — Working | 15 | 2 | 83.3% (15/18); 75% (15/20) before approval |
| D — Family | 16 | 1 | 84.2% |

**Finding:** exception-processing bottleneck creates an eligibility risk. Sequence: transport disruption → absence → exception request → admin queue → delayed decision → temporary eligibility risk. Contributing conditions: different schedule constraints, repeated disruptions, limited admin capacity, 80% threshold, exceptions required before eligibility. Implication: formal exceptions can still cause operational difficulty if the process cannot resolve requests before eligibility decisions.

**Guided exploration:** more frequent transport disruptions (does the bottleneck worsen?); more admin capacity (do delays fall?); less advisor availability (fewer ways to resolve difficulties?); different exception provisions (different outcomes?). Random exploration continues alongside. Counterfactual: raise admin capacity with policy, profiles and disruption schedule matched; if the bottleneck disappears, capacity is a contributing mechanism *within this model*.

**Policy comparison:**
| Dimension | Strict | Flexible | Progressive |
|---|---|---|---|
| Attendance enforcement | Direct threshold | Threshold with defined exceptions | Early warnings and support |
| Transport-related hardship | Formal exception process | Verified disruption provisions | Early intervention |
| Advisor involvement | As requested | As requested | Proactive |
| Administrative burden | Formal exception processing | Exception processing under defined provisions | Early support and intervention workload |
| Eligibility risk | From delayed approvals | Depends on exception processing | Depends on intervention timing and effectiveness |
| Primary trade-off | Consistency vs flexibility | Flexibility vs admin complexity | Proactive support vs resource capacity |

**Final output:** objective outcomes; attendance and eligibility distributions; stakeholder outcomes; adaptation records; workloads and delays; emergent findings with event sequences; three-policy comparison; further scenarios to explore. The policymaker decides. The run does not show the same sequence will happen at a real university.

### Demo user journey (8 screens)
1. **Landing:** "Create new policy simulation"; explains RuleStorm explores possible responses and consequences.
2. **Policy input:** 80% policy, purpose, environment. No manual agent creation.
3. **Blueprint + approval:** interpretation, stakeholder profiles, goals and constraints, environment rules, scenario types, outcomes to monitor, facts vs assumptions, validation status. Approve/edit only after validation passes.
4. **Launch:** current week, environment state, active agents, run progress, run ID and configuration.
5. **Live simulation:** disruptions, decisions, strategy changes, requests and responses, attendance/eligibility changes; click an agent for goals, constraints, memory, recent decisions.
6. **Discovery:** findings and the conditions that produced them; why variations were tested; links to events, state changes, calculations; counterfactual and replay.
7. **Comparison:** strict vs flexible vs progressive, matched conditions, repeated runs; stakeholder and operational trade-offs.
8. **Final assessment:** findings, stakeholder impact, trade-offs, event histories, open questions. The policymaker keeps authority.

### Research and positioning notes
- Research has moved from traditional ABM to LLM + ABM. Good for feasibility; RuleStorm must not position itself as the first platform using AI agents to simulate stakeholders.
- *Generative Agents* limitation: does not show simulated agents represent real stakeholders or give validated predictions.
- *1,000 People* limitation: uses substantial interview data per person; does not show generic agents can predict a whole university's response. Supports a future direction of grounding agents in real information.
- *LLM-ABM survey* challenges: environmental perception, behavioural alignment, action generation, evaluation, efficiency, scaling. Supports the hybrid LLM-agent + deterministic-environment design.
- *MDPI policy modelling*: compares Systems Thinking, System Dynamics and ABM. RuleStorm adds generative AI decisions and natural-language interaction.
- *PolicySim*: SFT/DPO-trained user agents, contextual bandits with message passing, social network interactions. Same aim (stress-test policies before deployment), different scope (social media vs. heterogeneous institutional stakeholders, structured enforcement, operational processes, discovery, inspectable consequences).
- *MASS*: methodological reference for event logging, action validation, matched runs, reproducibility.
- *Validation review*: problems with grounding, calibration, reproducibility, consistency, black-box decisions, cultural bias, stochastic outputs. Supports separating (1) what happened, (2) why agents acted, (3) observed patterns, (4) implications, (5) what needs real-world investigation.

**PolicySim reuse decision**
| Area | Decision |
|---|---|
| LLM stakeholder reasoning | Adapt the methodology; implement institutional reasoning independently |
| Agent decision loops | Implement independently with our observations and action contracts |
| Memory | Build memory for institutional stakeholders and event histories |
| Multi-agent communication | Adapt to requests, approvals, referrals and institutional workflows |
| Contextual bandits | Future scenario selection / intervention optimisation; not in MVP |
| SFT/DPO | Not in MVP; only with empirical data and a clear calibration need |
| Twitter/Weibo environment and prompts | Replace with education CSR, policies and institutional processes |
| Public repository code | Do not copy, modify or incorporate without a confirmed licence or explicit permission |

Licensing caution (checked 23 Nov 2026): the paper's CC BY 4.0 licence covers the paper, not the repository. The repo showed no `LICENSE` file and the README stated no licence; default copyright applies. Re-check and ask the maintainers before any reuse. Sources: https://arxiv.org/abs/2603.19649 · https://doi.org/10.1145/3774904.3792555 · https://github.com/renH2/PolicySim · https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository

**Research support by capability:** AI stakeholder agents: established direction. Memory and adaptation: demonstrated. Multi-agent interaction: established. LLM + ABM: active area. Policy impact exploration: established and developing. Proactive policy testing: directly related existing work (PolicySim). Deterministic enforcement alongside AI decisions: technically sound. Guided exploration: feasible, implementation-dependent. Emergent consequence discovery: demonstrable, not exhaustive. Evidence-backed explanations: achievable and important. Empirically valid real-world behaviour: needs further grounding.

**Validation levels:** internal validity (executable model, correct logic) → behavioural validity (plausible, consistent with profiles) → mechanism robustness (persists under controlled variation) → external validity (matches real systems via expert feedback and real evidence). The MVP targets internal validity, inspectable plausibility, provenance and basic robustness checks. Longer term, a university could help calibrate with anonymised attendance patterns, exception processing times and capacity, to check aggregate mechanisms, not to reproduce identifiable students.

**Final assessment (ours):** logical consistency strong if interpretation, CSR, agent decisions and enforcement stay separate and connected by validated contracts. Technical feasibility high for the bounded education MVP; a universal dynamic environment generator is a larger extended goal. Main engineering challenges: reliable generated definitions, governed execution order, meaningful discovery, provenance, reproducibility, API cost/latency. Main research challenge: showing simulated behaviour is representative enough for real policy decisions.

**Remaining concerns we committed to fix:** CRITICAL: dynamic environment generation (CSR); generated-definition reliability (4-stage validation + dry-run); execution order (snapshots, scheduling, validation, conflict resolution, controlled commits); consequence discovery ≠ scenario generation (separate mechanisms, novelty vs prior runs); evidence-backed findings (link to records, counterfactuals labelled within-model). HIGH: reproducibility (matched conditions, manifests, replay); API latency and cost (event-triggered, affected agents, bounded concurrency, compact memory, caching, budgets). LONG-TERM: real-world validity (expert feedback, calibration, behavioural validation).

### AWS plan (from our spec, section 12) — superseded
> **Superseded on 24 Nov 2026** by **Technical decisions** above: no Streamlit; only EC2 (one instance, disk, IP) + Bedrock spend credits; CloudFront, CloudWatch, SNS, Systems Manager, Budgets, IAM (and SQS if used) kept because they are always free; S3, ECR, Lambda, API Gateway, Cognito and DynamoDB dropped; the store is SQLite on the instance, so "the live demo must not depend on the EC2 local filesystem" below no longer applies; 2–3 accounts (one live, the rest dev); Region is now ap-southeast-2 (Sydney), so every Mumbai / ap-south-1 mention below is out of date; any plan whose usage is covered by free credits is acceptable. Kept below only as the record of the original plan.
AWS provides runtime, managed inference, storage, async jobs, monitoring and access control. The Python CSR, engine, discovery and agent contracts stay as application code running on AWS.

| Component | AWS service | Spec priority |
|---|---|---|
| Live app + Streamlit UI | Amazon EC2 | MUST |
| Container image | Amazon ECR | Recommended if Docker |
| Policy interpretation, CSR drafting, stakeholder suggestions, blueprint explanations | Amazon Bedrock | MUST |
| Event-triggered agent decisions and strategy updates | Amazon Bedrock | MUST |
| Scenario variations and finding explanations | Amazon Bedrock | MUST, bounded calls |
| Run status, snapshots, queue/request status, finding indexes | Amazon DynamoDB | MUST for deployed persistence |
| CSR JSON, manifests, event logs, scenario configs, results, reports | Amazon S3 | MUST |
| Async simulation jobs | Amazon SQS | MUST if async |
| Simulation worker | Python worker on EC2 (Lambda optional later) | EC2 MUST; Lambda NICE |
| Logs and monitoring | CloudWatch / CloudWatch Logs | MUST |
| Least-privilege access, no hard-coded keys | IAM | MUST |
| Cost alerts | AWS Budgets, Billing / Cost Management | MUST |
| Multi-user sign-in | Amazon Cognito | NICE |
| Separate serverless API | API Gateway + Lambda | NICE |

**Architecture:** browser → public URL → one small EC2 instance in **ap-south-1 (Mumbai)** running Streamlit UI, Python app, validators, engine and an SQS-consuming worker → Bedrock (inference), SQS (run/batch queue), CloudWatch (logs/metrics); worker checkpoints to DynamoDB and writes artefacts to S3; ECR holds the image; IAM roles; Budgets. Keep worker concurrency low. If batches later move to Lambda, split into checkpointed tasks (900 s limit); never put a whole simulation or comparison in one invocation.

**Region and model:** Bedrock Runtime has a Mumbai endpoint, but model availability varies by model and inference mode. Pick a model with **in-Region** support in ap-south-1, enabled on the account, and good enough at structured output. AWS's table lists GPT-OSS 20B with in-Region Mumbai support (an example to evaluate, not a requirement). The new Free Tier experience does not support multi-/cross-Region features, so avoid cross-Region inference. Recheck in the console before deploying. Refs: https://docs.aws.amazon.com/bedrock/latest/userguide/models-region-compatibility.html · https://docs.aws.amazon.com/in_en/accounts/latest/reference/supported-services-sign-up-new.html

**Data placement:** run status/progress and current snapshots → DynamoDB; CSR and policy versions → S3 (IDs referenced in DynamoDB); manifests → S3 + run metadata in DynamoDB; event/action history → S3 JSON/JSONL + index in DynamoDB; scenarios and results → S3; finding evidence links → DynamoDB; logs → CloudWatch. The engine stays the source of truth; Bedrock text is never authoritative; the LLM gets only the context it needs; structured output is validated before commit. SQLite stays for local dev and tests; the live demo must not depend on the EC2 local filesystem. Call Bedrock via the AWS SDK rather than a separate model API key.

**Free Tier and cost guardrails:** choose EC2 size/storage/Region allowed by the Free Tier plan (check console indicators); one EC2 instance, one low-concurrency worker; no EKS, fleets or provisioned throughput; set Budgets and billing alerts before Bedrock experiments; app-level limits on calls, tokens, batches and repeats; cache approved interpretations; monitor Bedrock invocations/tokens/latency, EC2 hours, EBS, S3, DynamoDB, data transfer; keep the live demo running through Demo Day and stop only non-essential test resources; don't claim it is free at any scale; record actual services and usage in the Build Summary. Free Tier service inclusion is not unlimited free use. Refs: https://aws.amazon.com/free/ · https://aws.amazon.com/free/free-tier-faqs/

**Workflow on AWS:** open demo (EC2) → submit policy (Python modeller) → Bedrock generates, validator checks, versioned CSR to S3 → agents initialised, metadata to DynamoDB → start run: run record in DynamoDB + message on SQS → worker runs snapshot decisions and deterministic transitions, Bedrock only for affected agents, checkpoints → traces and manifests to S3, indexes to DynamoDB → discovery analyses metrics/sequences, Bedrock helps label/explain from evidence → counterfactual and comparison jobs on SQS under new run IDs → UI reads findings and evidence from DynamoDB/S3 → CloudWatch + Budgets monitor.

**Build Summary table (only list services actually deployed):** EC2 (app + engine/worker); Bedrock (policy/CSR generation, agent decisions); DynamoDB (run metadata, state, snapshots, finding indexes); S3 (CSR versions, manifests, traces, results); SQS (decouple UI from runs); ECR (image, if Docker); CloudWatch (logs, metrics); IAM (least privilege); Budgets (spend alerts). Don't list Lambda, API Gateway or Cognito unless deployed.

### Bharat Impact framing and pilot measures (from our spec)
Present the problem narrowly: Indian institutions create and enforce policies affecting students with different real-life constraints, without a practical way to examine how rules interact with behaviour and capacity before implementation. Do not present simulated outcomes as measured improvements. Where feasible, validate with students, faculty or an academic administrator and track:
- Time for a policymaker to create and review a blueprint.
- Number of stakeholder constraints represented and confirmed by a domain reviewer.
- Number of distinct, evidence-linked risks or bottlenecks surfaced in a controlled test set.
- Share of findings a domain reviewer considers relevant.
- Time to compare policy alternatives under the same scenario conditions.
- Whether the review leads to a clause, exception process or workflow being reconsidered before implementation.

Report the method and actual results. Without a real pilot, label impact as a potential benefit shown through a synthetic simulation.

### Submission mapping (from our spec)
Live URL: EC2-hosted app, verified available through Demo Day. Idea Brief: Indian institutional policy-testing problem, users, workflow, potential impact. Build Summary: services actually deployed. Repo: setup/deploy instructions, no committed secrets. Demo video (<3 min): policy input, generated/validated CSR, adaptive decisions, an evidence-linked finding, policy comparison. Drive folder with all items; team leader submits. Finals: 3-minute live demo + 2-minute Q&A. The AWS deployment must be visible in the live prototype and explained in the Build Summary, not only in slides.

## Gaps
- `[MISSING: India-specific evidence of the problem]`: numbers or reports on attendance-based exam eligibility in Indian institutions, exception/condonation backlogs, students affected. Bharat Impact is 30% and we have no problem evidence yet. Also confirm whether 80% (our spec) matches the threshold at the institutions we will cite; we have no source either way.
- `[MISSING: a real persona]`: a named policymaker role at a real institution we have spoken to, and a quote from them.
- `[MISSING: today's workaround]`: how institutions draft, review and adjust attendance rules today (committee review? precedent? nothing?).
- `[MISSING: user validation]`: any of the pilot measures above, even one domain reviewer rating our findings.
- **Technical, to confirm in the console on day 1** (see Technical decisions): which teammates own the live and Dev accounts (each never held an AWS account, own card); Sydney hourly prices for t3.small / t4g.small and the live account's credit runway; day-0 smoke test (each model called through the profile and then the instance's IAM role); that the chosen model needs no extra Marketplace subscription; bake-off result for the model; measured run duration; frontend framework (decide in /build-plan).
- **Prior work and third-party code** (to discuss as we go): the starter-kit code pulled from GitHub into our repo and its licence; PolicySim cited, no code reused. Rule 7 wants original work not protected by publications, so we will list both in the README and Build Summary.
- `[MISSING: "why should the majority care" line for the video]`: the rules ask for it; needs a sourced scale number (e.g. how many Indian students are under attendance-based eligibility rules).
- From the rules: prize amounts, submission form field limits, and the pre-existing-code rule are not stated.
- **Scope check:** today is 24 Nov 2026 and the deadline is 30 Nov, 11:59 PM IST, so roughly 3 days is "half the event". All ten must-haves are needed. The most expensive is **must-have 4, the eight Bedrock-driven agents**. Simpler version that still runs: call Bedrock only for the six agents who make real choices (four students, faculty, advisor) and run the attendance administrator and examination officer as rule-following agents in code, which our spec already allows ("administrators process exception requests according to policy and capacity"; eligibility "is determined by the simulation engine using approved rules"). Keep all eight agents in the simulation.
