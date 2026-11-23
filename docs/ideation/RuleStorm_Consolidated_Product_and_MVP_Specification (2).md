# RuleStorm — Consolidated Product and MVP Specification

**AI-Powered Policy Simulation and Stress Testing**  
*Discover what happens when policies meet real people.*

## 1. Product definition

RuleStorm is a general-purpose, AI-powered policy-testing platform that simulates how policies affect stakeholders, how stakeholders react and adapt, and how their interactions may produce unintended consequences.

A policymaker submits a proposed policy, its intended purpose and information about the environment in which it will operate.

RuleStorm constructs a simulated environment populated by AI-powered stakeholder agents. Each agent has its own objectives, priorities, constraints, information, resources and behavioural tendencies.

As the policy operates, agents make decisions, interact with other stakeholders, respond to events and adapt their strategies over simulated time.

The system explores different circumstances, identifies potentially significant outcomes and reveals unintended behavioural adaptations, conflicting interests and operational consequences.

RuleStorm does not claim to predict exactly what real people will do or automatically determine whether a policy is good or bad. It helps decision-makers investigate plausible consequences before implementation.

### Core product capabilities

1. AI-driven stakeholder modelling.
2. Adaptive behavioural simulation.
3. Emergent consequence discovery.
4. AI-guided scenario exploration.
5. Inspectable policy outcomes.
6. Comparative policy testing.
7. Human-controlled policy evaluation.

## 2. Scope and priority definitions

The complete product is divided into two priority levels.

- **MUST HAVE — MVP:** Capabilities needed to demonstrate the complete RuleStorm concept in one educational environment. The scale is limited, but the underlying functionality is preserved.
- **NICE TO HAVE — Extended product:** Capabilities that extend scale, sophistication, validation, automation and domain coverage beyond the MVP.

## 3. Complete functional scope — priority ranked

### A. User interaction and policy modelling

| Priority | Feature | Functional requirement |
|---|---|---|
| MUST HAVE | Natural-language policy submission | User enters a policy without configuring technical simulation rules. |
| MUST HAVE | Intended purpose | User defines what the policy is intended to achieve and important constraints. |
| MUST HAVE | Environment selection | User selects an education environment for the MVP. |
| MUST HAVE | AI policy interpretation | Extract thresholds, obligations, rules, exceptions and enforcement mechanisms. |
| MUST HAVE | Simulation blueprint | Generate proposed stakeholder groups, objectives, constraints, environment rules and outcomes to monitor. |
| MUST HAVE | Human review | User reviews and approves the generated blueprint before simulation. |
| MUST HAVE | Assumption disclosure | Clearly distinguish user-provided facts, AI-generated assumptions, fixed rules and variable scenario conditions. |
| MUST HAVE | Generated-definition validation | Validate the generated policy and environment definitions before they can execute. |
| NICE TO HAVE | Domain templates | Ready-made templates for education, transportation, public services, organisations and urban resource allocation. |
| NICE TO HAVE | Advanced ambiguity resolution | Identify important ambiguities and ask targeted questions. |
| NICE TO HAVE | Advanced policy editing | Modify individual policy clauses through a visual editor. |

**MVP implementation:** Natural-language policy entry, purpose and environment input, AI-generated structured policy, suggested stakeholders and a review screen.

The policy interpretation must be converted into a structured representation before execution. An LLM must not independently enforce the policy during simulation.

### B. Stakeholder-agent modelling

| Priority | Feature | Functional requirement |
|---|---|---|
| MUST HAVE | AI stakeholder generation | Generate relevant stakeholder profiles from the approved blueprint. |
| MUST HAVE | Individual objectives | Each agent has goals and priorities. |
| MUST HAVE | Constraints | Each agent has restrictions that influence its available choices. |
| MUST HAVE | Resources | Each agent has limited resources and capabilities. |
| MUST HAVE | Information | Agents have relevant knowledge and information limitations. |
| MUST HAVE | Behavioural tendencies | Agents have individual preferences and behavioural characteristics. |
| MUST HAVE | Memory | Agents retain relevant past experiences. |
| MUST HAVE | Decision-making | Agents choose actions according to their objectives and circumstances. |
| MUST HAVE | Communication and interaction | Agents interact through actionable requests, responses and institutional processes. |
| MUST HAVE | Structured decision records | Preserve each agent's observation context, proposed action, reason, validation result and strategy update. |
| NICE TO HAVE | Larger agent populations | Multiple agent instances within each stakeholder archetype. |
| NICE TO HAVE | Advanced long-term memory | Richer episodic memory, reflection and retrieval across longer simulations. |
| NICE TO HAVE | Sophisticated behavioural profiles | More detailed preferences, changing priorities and heterogeneous behavioural tendencies. |
| NICE TO HAVE | Advanced multi-agent coordination | More complex social relationships and multi-party communication. |

**MVP implementation:** Four student agents, one faculty member, one academic advisor, one attendance administrator and one examination-office representative.

Eight agents, each with different goals, resources, information and constraints.

The agents must make decisions, not merely generate opinions about the policy.

### C. Dynamic environment and simulation engine

| Priority | Feature | Functional requirement |
|---|---|---|
| MUST HAVE | Shared environment state | Maintain one authoritative simulation state. |
| MUST HAVE | Policy enforcement | Apply approved policy rules consistently. |
| MUST HAVE | Time progression | Advance simulated time and process relevant events. |
| MUST HAVE | Agent action validation | Validate actions against permissions and environmental rules. |
| MUST HAVE | State transitions | Update the environment when valid actions occur. |
| MUST HAVE | Event recording | Record environmental events, decisions, interactions and consequences. |
| MUST HAVE | Resource constraints | Represent limits such as administrative processing capacity. |
| MUST HAVE | External disruptions | Introduce environmental events that affect stakeholder decisions. |
| MUST HAVE | Deterministic calculations | Calculate attendance, eligibility and institutional outcomes through code. |
| MUST HAVE | Canonical simulation representation | Represent entities, state variables, units, actions, events, relationships, constraints, transitions, calculations and metrics through a common typed model. |
| MUST HAVE | Definition validation | Check schemas, identifiers, references, types, units, dependencies, permissions and calculations before execution. |
| MUST HAVE | Governed execution order | Use consistent state snapshots, action validation, conflict resolution and controlled state commits. |
| NICE TO HAVE | More sophisticated environments | Multiple courses, departments, institutions and interconnected systems. |
| NICE TO HAVE | Complex resource networks | Interdependent resources, service queues and institutional workflows. |
| NICE TO HAVE | Larger event catalogues | More external disruptions and interactions between environmental variables. |
| NICE TO HAVE | Domain-specific environment modules | Pluggable environment configurations for other industries. |

**MVP implementation:** One synthetic educational institution, one course, two weekly sessions and a ten-week simulated period.

The environment must be deterministic where formal rules and calculations are concerned. Agent behaviour remains flexible.

### D. Dynamic stakeholder behaviour and adaptation

| Priority | Feature | Functional requirement |
|---|---|---|
| MUST HAVE | Context-dependent decisions | Agents select actions based on circumstances. |
| MUST HAVE | Event-driven planning | Agents make decisions when meaningful events affect them. |
| MUST HAVE | Behavioural adaptation | Agents change strategies in response to previous events. |
| MUST HAVE | Memory-informed decisions | Previous experiences influence subsequent actions. |
| MUST HAVE | Agent-to-agent influence | One stakeholder's action can change another stakeholder's circumstances. |
| MUST HAVE | Institutional workflows | Requests, approvals, rejections, delays and interventions affect the environment. |
| MUST HAVE | Replayable decision history | Preserve accepted and rejected actions and event sequences so a recorded episode can be inspected and replayed. |
| NICE TO HAVE | Deeper behavioural adaptation | More sophisticated strategy refinement over longer time horizons. |
| NICE TO HAVE | Advanced social interactions | Complex coordination, negotiation, group behaviour and network effects. |
| NICE TO HAVE | Behavioural calibration | Calibrate agent behaviour using real-world observations or expert feedback. |

**MVP implementation:** Agents must have an observable change in strategy during the simulation, and that change must affect subsequent decisions.

### E. Scenario exploration and consequence discovery

| Priority | Feature | Functional requirement |
|---|---|---|
| MUST HAVE | Scenario generation | Generate different combinations of environmental conditions. |
| MUST HAVE | Random exploration | Test scenarios without relying only on previously discovered risks. |
| MUST HAVE | Goal-oriented exploration | Investigate circumstances that threaten policy objectives. |
| MUST HAVE | Emergent-behaviour exploration | Identify unexpected behavioural strategies and interaction patterns. |
| MUST HAVE | Outcome-based prioritisation | Identify scenarios that produce noteworthy consequences. |
| MUST HAVE | Guided exploration | Use observed results to suggest further scenario variations. |
| MUST HAVE | Multiple discovery dimensions | Examine stakeholder disparity, operational bottlenecks, objective shortfalls and unusual behaviour separately. |
| MUST HAVE | Separate discovery mechanisms | Detect objective failures, operational bottlenecks and unexpected behavioural patterns as distinct categories. |
| MUST HAVE | Novelty comparison | Compare observed patterns against prior runs to identify unusual or recurring sequences. |
| MUST HAVE | Controlled follow-up experiments | Vary one relevant condition to investigate whether a discovered mechanism persists or changes. |
| NICE TO HAVE | TPE or evolutionary search | More sophisticated scenario optimisation. |
| NICE TO HAVE | Automated pattern clustering | Discover recurring patterns across larger collections of runs. |
| NICE TO HAVE | Advanced novelty detection | Identify previously unseen patterns using richer similarity and novelty techniques. |
| NICE TO HAVE | Learned exploration strategies | Train or adapt search strategies using accumulated simulation results. |

**MVP implementation:** A feedback-driven search mechanism with an initial 60% targeted exploration and 40% random exploration split as an engineering starting point. Retain both goal-oriented and emergent-behaviour discovery.

### F. Outcome analysis and explainability

| Priority | Feature | Functional requirement |
|---|---|---|
| MUST HAVE | Policy objective assessment | Show how the policy performed against its intended objective. |
| MUST HAVE | Stakeholder-level outcomes | Show different consequences across stakeholder types. |
| MUST HAVE | Behavioural adaptation analysis | Show how agents responded and changed strategies. |
| MUST HAVE | Operational impact analysis | Show workloads, requests, delays and capacity constraints. |
| MUST HAVE | Trade-off analysis | Show competing outcomes rather than a single universal score. |
| MUST HAVE | Event sequence inspection | Trace how an outcome emerged. |
| MUST HAVE | Evidence-backed explanations | Separate recorded events from AI interpretations. |
| MUST HAVE | Evidence provenance | Link each finding to source event IDs, state changes, calculations and run configuration. |
| MUST HAVE | Observation/interpretation separation | Distinguish recorded facts, calculated outcomes, model-based interpretations and hypotheses for further investigation. |
| MUST HAVE | Counterfactual investigation | Support at least one controlled within-model rerun that changes a relevant condition while matching other conditions. |
| MUST HAVE | Human judgement | Let the policymaker decide whether consequences are acceptable. |
| NICE TO HAVE | Advanced visualisations | Interactive network graphs, detailed distributions and richer scenario timelines. |
| NICE TO HAVE | Automated pattern clustering | Group similar outcomes and recurring mechanisms. |
| NICE TO HAVE | Exportable reports | Generate downloadable policy assessment reports. |
| NICE TO HAVE | Advanced uncertainty analysis | Sensitivity analysis and more extensive uncertainty reporting. |

### G. Policy comparison and experimentation

| Priority | Feature | Functional requirement |
|---|---|---|
| MUST HAVE | Alternative policy definitions | Test multiple policy alternatives. |
| MUST HAVE | Matched starting conditions | Use comparable initial stakeholder profiles and environmental states. |
| MUST HAVE | Repeated runs | Account for stochastic agent decisions. |
| MUST HAVE | Comparative outcomes | Compare objectives, stakeholder impacts and operational consequences. |
| MUST HAVE | Behavioural comparison | Show how different policies produce different adaptations and interactions. |
| MUST HAVE | Run manifest | Record model, prompt, policy, environment, engine versions, initial state, scenario schedule and execution parameters. |
| MUST HAVE | Repeated-run provenance | Retain run identifiers and agent action records for every comparison run. |
| NICE TO HAVE | Larger experiment batches | Run extensive comparisons across many initial conditions. |
| NICE TO HAVE | Automated policy variation | Generate policy alternatives for further testing. |
| NICE TO HAVE | Advanced statistical analysis | Confidence intervals, variance analysis and sensitivity testing. |

### H. Platform architecture and extensibility

| Priority | Feature | Functional requirement |
|---|---|---|
| MUST HAVE | Modular architecture | Separate policy, environment, agent, simulation and analysis components. |
| MUST HAVE | Configurable environment | Keep education-specific rules separate from the reusable engine. |
| MUST HAVE | Structured agent interface | Common schemas for agent state, observations, decisions and actions. |
| MUST HAVE | Reusable simulation core | Keep event processing, state management and validation independent of one policy. |
| MUST HAVE | Versioned simulation contracts | Version canonical definitions and define preconditions, permissions and effects for state-changing actions. |
| MUST HAVE | Model and prompt provenance | Record which model and prompt versions generated the policy, environment and agent definitions. |
| MUST HAVE | Runtime controls | Use event-triggered LLM decisions, bounded concurrency, compact agent context and an explicit call/run budget. |
| NICE TO HAVE | Additional policy domains | Transportation, public services, organisations and urban resource allocation. |
| NICE TO HAVE | Custom environment builder | Configure new environments without rebuilding the engine. |
| NICE TO HAVE | Scalable execution | Support larger simulations, multiple concurrent runs and more agents. |
| NICE TO HAVE | Advanced deployment | Distributed execution and institutional integrations. |

## 3.1 Genuine remaining concerns and architectural requirements

The following concerns are part of the engineering specification. They do not change RuleStorm's product vision; they make the proposed capabilities executable, consistent and inspectable.

| Priority | Remaining concern | Required fix |
|---|---|---|
| CRITICAL | Dynamic environment generation: different domains use different entities, variables and relationships. | Introduce a Canonical Simulation Representation (CSR) covering entities, state, variables, units, actions, events, relationships, constraints, calculations, state transitions and metrics. |
| CRITICAL | Generated-definition reliability: an LLM can produce structurally valid but logically incompatible definitions. | Validate schemas, identifiers, types, units, references, dependencies, permissions, constraints and calculations before execution. Include a dry-run or test episode. |
| CRITICAL | Simulation execution order: decisions made against changing state can conflict or produce order-dependent results. | Use snapshot-based decisions, event scheduling, action validation, conflict resolution and controlled state commits. |
| CRITICAL | Consequence discovery: generating scenarios is not the same as discovering unexpected consequences. | Separate objective-failure detection, operational-bottleneck discovery and behavioural-pattern discovery. Compare novelty against prior runs. |
| CRITICAL | Evidence-backed findings: an LLM explanation can invent causal relationships. | Link findings to event records, state changes and deterministic calculations. Use controlled counterfactual runs to investigate mechanisms, while labelling them as within-model evidence. |
| HIGH | Reproducibility: LLM decisions may differ across apparently identical runs. | Match initial conditions and scenario schedules; record model, prompt, policy, environment and engine versions, sampling parameters and action records. Support replay of recorded decisions. |
| HIGH | API latency and cost: multiple agents and repeated runs can create excessive calls. | Use event-triggered decisions, affected-agent selection, bounded concurrency, compact memory context, appropriate caching and an explicit run/call budget. |
| LONG-TERM | Real-world validity: synthetic agents do not automatically represent real populations. | Introduce expert feedback, empirical calibration and behavioural validation using suitable real-world evidence. |

### A. Canonical Simulation Representation (CSR)

The CSR is the internal, domain-independent contract between generated environment definitions and the simulation engine. The LLM-generated environment must not create a new simulation engine or executable code for each domain. It generates a validated, declarative model that conforms to the CSR.

The minimum representation includes:

- **Entities:** the domain's actors and objects, such as students, courses, administrators, passengers or vehicles.
- **State variables:** typed properties with explicit initial values and, where applicable, units and valid ranges.
- **Relationships:** connections between entities, such as student-to-course enrolment or passenger-to-route assignment.
- **Actions:** permitted operations, their actors, targets and parameters.
- **Events:** occurrences that trigger decisions or state transitions.
- **Constraints and permissions:** what entities can and cannot do, including role-based restrictions.
- **State transitions:** the approved changes that actions and events can cause.
- **Calculations:** deterministic formulas and derived values.
- **Metrics:** outcomes used for monitoring and discovery.

Use stable internal identifiers and canonical types. The presentation layer maps these internal concepts to domain-specific terminology. This allows a common engine to support different domains without forcing users to see generic technical labels.

Every generated definition must be versioned. Every state-changing action must have an execution contract defining its preconditions, permissions, resource requirements and effects. The CSR should be built for reuse, but only the education configuration needs to be implemented and validated in the MVP.

### B. Generated-definition validation

A generated definition passes through four validation stages before execution:

1. **Schema validation:** required fields, types, structures and unique identifiers.
2. **Reference validation:** referenced entities, variables, events, actions and metrics must exist.
3. **Semantic validation:** units, valid ranges, dependencies, permissions, constraints and calculation compatibility must be coherent.
4. **Execution validation:** a dry-run or test episode checks that transitions and calculations can execute without violating invariants.

Structurally valid JSON is not sufficient evidence that a model is logically executable. Invalid definitions must be returned for correction rather than passed to the simulation engine.

### C. Governed simulation execution

Use an explicit execution cycle:

1. Capture a consistent snapshot of the current environment state.
2. Identify agents affected by the event and give them the relevant snapshot and information.
3. Generate structured action proposals. Decisions made in the same decision phase use the same snapshot.
4. Validate permissions, preconditions, constraints and resource availability.
5. Resolve conflicting actions using explicit ordering, priority, queue or resource-allocation rules.
6. Commit accepted actions to the authoritative environment state.
7. Record state changes and resulting events, then update affected agents' memory.

Agents cannot directly modify authoritative simulation state. The engine remains the source of truth for policy enforcement, calculations, permissions and state changes.

### D. Separate discovery mechanisms

The discovery engine is a distinct subsystem that consumes recorded simulation outcomes. It must not rely solely on an LLM reading logs or on a predefined list of failure stories.

- **Objective-failure discovery:** identifies cases where intended policy objectives are not achieved or important stakeholder outcomes deteriorate.
- **Operational-bottleneck discovery:** identifies overloaded queues, resource shortages, delays and process constraints.
- **Behavioural-pattern discovery:** identifies unusual or recurring strategies, action sequences and interactions that were not explicitly prescribed as findings.

The MVP can implement these with deterministic metrics, queue analysis, event-sequence analysis and basic novelty comparison. LLMs may help label or explain candidate patterns, but the supporting evidence must come from the recorded simulation. Random exploration must remain alongside guided exploration.

### E. Facts, interpretations and counterfactual evidence

Every finding must distinguish:

- **Recorded events:** what the event log says occurred.
- **Environment changes:** the actual accepted state transitions.
- **Calculated outcomes:** metrics produced by deterministic calculations.
- **Observed patterns:** patterns identified by the discovery subsystem.
- **AI interpretations:** explanations of what the recorded evidence may mean.
- **Further hypotheses:** questions that require additional investigation.

A counterfactual run changes a selected condition while matching the other relevant starting conditions and external events. For example, increase administrative processing capacity and investigate whether the exception queue still causes eligibility risk. This can test a causal mechanism within the simulation model; it does not establish causality in a real institution.

### F. Reproducibility, provenance and replay

Every run must have a run manifest containing, at minimum:

- Model provider and model version.
- Prompt and agent-definition versions.
- Sampling and generation parameters where available.
- Policy and CSR/environment versions.
- Simulation-engine version.
- Initial agent and environment states.
- External scenario/event schedule.
- Run identifier and execution parameters.
- Agent action proposals, validation results and committed actions.

Provide two modes:

- **Experiment mode:** agents make fresh decisions and the simulation explores behavioural variation.
- **Replay mode:** recorded decisions and events are replayed to inspect an existing episode and reproduce its state transitions as closely as the stored records permit.

Do not rely on temperature settings alone to guarantee reproducibility. Recorded decisions and state transitions are the basis for replay.

### G. Runtime efficiency and API controls

API latency and cost are MVP engineering requirements. Invoke an LLM only when a meaningful agent or modelling decision is required. Select only affected agents, use compact structured memory, bound concurrency, cache appropriate repeated interpretation/configuration work and define an explicit budget for calls and simulation runs. Routine calculations, validation and predictable state transitions should be handled deterministically.

## 4. MVP implementation specification

### RuleStorm Education Stress Tester

| Dimension | MVP scope |
|---|---|
| Institution | One synthetic institution |
| Courses | One course |
| Agents | Eight stakeholder agents |
| Students | Four archetypes |
| Simulated period | Ten weeks |
| Class schedule | Two sessions per week; 20 planned sessions |
| Policy alternatives | Three |
| Scenario families | Four |
| Canonical model | One validated education CSR configuration |
| Definition validation | Four stages: schema, references, semantics and execution dry-run |
| Discovery mechanisms | Three: objective failures, operational bottlenecks and behavioural patterns |
| Counterfactual investigation | At least one finding investigated through a controlled matched rerun |
| Reproducibility | Run manifest, recorded decisions and replay |
| Runtime limits | Explicit per-experiment run and LLM-call budgets |

### 4.1 Student agents

| Agent | Goals | Constraints | Relevant behaviour |
|---|---|---|---|
| Student A — Long-distance commuter | Maintain attendance and eligibility | Long commute | Can change departure times and travel strategies |
| Student B — Campus resident | Maintain academic progress | Academic workload | More flexibility in travelling to class |
| Student C — Working student | Maintain eligibility and employment | Fixed working hours | Cannot freely change the schedule |
| Student D — Family commitments | Complete academic requirements | Limited schedule flexibility | Balances family and academic responsibilities |

These are synthetic operational profiles. The agents should differ because of their circumstances, not simply because they have different personalities in prompts.

### 4.2 Institutional agents

| Agent | Goals | Constraints |
|---|---|---|
| Faculty member | Maintain participation and academic progress | Limited rescheduling capability |
| Academic advisor | Help students address attendance difficulties | Limited appointment capacity |
| Attendance administrator | Process attendance corrections and exceptions | Limited processing capacity |
| Examination officer | Apply eligibility rules correctly | Must follow approved policy |

### 4.3 Policy alternatives

**Policy A — Strict attendance threshold**

80% per-course attendance, with formally approved exceptions.

**Policy B — Flexible attendance threshold**

80% attendance requirement, with defined provisions for institutional disruptions and verified exceptional circumstances.

**Policy C — Progressive attendance support**

80% attendance requirement, with early warnings and advisor interventions so students can address difficulties before examination eligibility is determined.

### 4.4 Environment and disruption catalogue

| Scenario | Environmental change | What it tests |
|---|---|---|
| Transport disruption | Unexpected commute delays | Different stakeholder flexibility |
| Academic workload spike | Increased academic workload | Conflicting commitments |
| Timetable conflict or class cancellation | Schedule or class availability changes | Institutional adaptability |
| Administrative capacity crunch | Increased request volume and processing constraints | Operational bottlenecks |

Events should be capable of interacting. The engine must not assume every disruption produces a predefined outcome.

### 4.5 Simulation rules and the Canonical Simulation Representation

The MVP uses a minimal CSR implementation for the education domain. The representation should already use reusable concepts and stable identifiers, but it only needs to model one synthetic institution and one course.

The minimum education model represents:

- Entities: student, course, class session, faculty member, advisor, attendance administrator, examination officer and exception request.
- State variables: attendance records, timetable, request status, staff capacity, agent resources and current strategy.
- Actions: attend class, modify schedule, request assistance, request exception, offer alternative session, process request, intervene and evaluate eligibility.
- Events: class scheduled, class cancelled, transport disruption, workload spike, request submitted, evidence requested, request approved/rejected, queue capacity reached and eligibility assessed.
- Constraints and permissions: for example, students cannot modify attendance records or approve their own exceptions.
- Calculations and metrics: attendance percentage, eligibility, request queue length, processing delay and stakeholder outcomes.

The CSR is declarative. Do not execute arbitrary Python or other code generated by an LLM. Use approved operators, schema validation and versioned action contracts.

The MVP must distinguish between agent choices and environmental facts:

- Students decide whether to attend, modify schedules, request assistance or seek exceptions.
- Faculty decides whether to offer alternative sessions within available options.
- Advisors decide whether and how to intervene.
- Administrators process exception requests according to policy and capacity.
- Examination officers evaluate eligibility using authoritative attendance records.

Attendance calculation:

\[
\text{Attendance Percentage} =
\frac{\text{Sessions attended}}
{\text{Countable completed sessions}}
\times 100
\]

Approved exceptional sessions are excluded from the countable-session denominator. Cancelled institutional sessions are also excluded. Pending or rejected exceptions remain countable absences until resolved.

The examination officer's final decision is determined by the simulation engine using approved rules.

### 4.6 Generated-definition validation

Before execution, validate the generated policy and education environment:

1. Check required fields, types, unique identifiers and schema versions.
2. Check that all referenced agents, entities, actions, events, variables and metrics exist.
3. Check units, valid ranges, dependencies, role permissions and action preconditions.
4. Check that calculations reference valid variables and produce compatible values.
5. Run a small dry-run/test episode and reject definitions that violate invariants or fail to execute.

The blueprint review screen must show user-provided facts separately from AI-generated assumptions. The user can review and correct material assumptions before approving the simulation.

### 4.7 Governed event-driven execution

Use this execution cycle for each meaningful decision phase:

1. Capture the current environment snapshot.
2. Identify only the agents affected by the current event.
3. Ask those agents for structured action proposals based on the same snapshot.
4. Validate proposals against permissions, preconditions, constraints and available resources.
5. Resolve conflicting actions through explicit priority, queue or resource rules.
6. Commit accepted actions to the authoritative state.
7. Record events and state changes, then update relevant agent memories.

Actions that conflict must not be resolved by arbitrary agent-loop order. The conflict-resolution rule must be explicit and recorded. For example, administrative requests can enter a FIFO queue ordered by submission timestamp, with a stable identifier used to break ties; resource allocation must follow an explicit role or policy priority. Routine state updates and calculations do not require LLM calls.

### 4.8 Scenario exploration and consequence discovery

The MVP uses a feedback-driven discovery loop:

1. Generate baseline and varied scenarios.
2. Run the stakeholder simulation.
3. Measure policy objective outcomes.
4. Detect objective shortfalls and stakeholder disparities.
5. Detect operational bottlenecks, queues and resource shortages.
6. Detect unusual or recurring behavioural action sequences and compare them with patterns from earlier runs.
7. Generate targeted variations around noteworthy findings.
8. Run additional experiments and determine whether the observed mechanism persists or changes.

The MVP must implement three distinct discovery mechanisms:

- Objective-failure detection.
- Operational-bottleneck detection.
- Behavioural-pattern discovery.

Start with a 60% targeted exploration and 40% random exploration split. This is an engineering starting point, not a scientifically established optimum or a trained ML model. Retain random exploration so the system does not only search for risks it already knows how to recognise.

LLMs may propose scenario variations or help describe candidate patterns, but discovery evidence and metrics must be computed from simulation records.

### 4.9 Evidence, counterfactual investigation and run provenance

Every MVP finding must link to the supporting event IDs, agent decisions, validation results, state changes and deterministic calculations. Its report must separate recorded facts, calculated outcomes, observed patterns, AI interpretations and hypotheses requiring further investigation.

For at least one significant finding, the MVP must support a controlled counterfactual investigation. Change one relevant condition, such as administrative processing capacity, while matching the policy, initial state and external event schedule as closely as possible. Repeat matched runs where practical because fresh LLM decisions may differ even under the same nominal conditions. Compare the resulting queue and eligibility outcomes as distributions or episode-level traces rather than assuming every decision will be identical. Label the result as evidence about the simulation model, not proof of a real-world causal relationship.

Each run must store a compact manifest containing:

- Run ID and timestamp.
- Model provider/version and generation parameters where available.
- Prompt and agent-definition versions.
- Policy, CSR/environment and simulation-engine versions.
- Initial agent/environment state and external event schedule.
- Relevant configuration and exploration settings.
- Agent action proposals, validation outcomes and committed actions.

Support replay of a recorded episode from stored decisions and events. Replay is for inspection and debugging; new experiments still use fresh agent decisions. Do not claim that a model setting such as temperature zero guarantees identical fresh runs.

### 4.10 Runtime efficiency and API controls

The MVP must:

- Invoke agents at meaningful decision events rather than every time step.
- Involve only agents affected by the current event.
- Use compact memory summaries and structured context.
- Apply bounded concurrency and sensible timeouts/retries.
- Cache suitable repeated policy/environment interpretation operations.
- Set an explicit maximum number of runs and LLM calls for a user-triggered experiment.
- Use deterministic code for routine calculations, validation and state transitions.

The interface should show run progress and any failed or incomplete run rather than leaving the user without feedback.

### 4.11 AI and technical architecture

| Component | Responsibility | Suggested implementation |
|---|---|---|
| Policy modeller | Interpret policy language and generate structured policy definitions | LLM API + Pydantic |
| Environment modeller | Generate the education CSR configuration and assumptions | LLM-assisted generation + Python configuration |
| CSR validator | Validate schemas, references, units, dependencies, permissions and calculations | Pydantic + custom Python validators |
| Stakeholder framework | Manage agent goals, memory, observations and decisions | LLM + structured agent state |
| Simulation engine | Schedule events, validate actions, resolve conflicts and commit state transitions | Custom Python event engine |
| Discovery engine | Detect objective failures, bottlenecks and behavioural patterns; guide exploration | Python metrics/event analysis + LLM-assisted variation/explanation |
| Analysis engine | Calculate outcomes, compare runs and generate evidence-grounded explanations | Python + Pandas + LLM |
| Frontend | Policy input, blueprint review, simulation and results dashboard | Streamlit |
| Persistence | Store policies, CSR versions, agents, events, run manifests and outcomes | SQLite |

Suggested stack: Python, Streamlit, Pydantic, an existing LLM API, SQLite, Pandas and Plotly.

Common agent interface:

```python
Agent:
    id
    role
    goals
    constraints
    resources
    knowledge
    behavioural_tendencies
    memory
    current_strategy
    available_actions
```

Common decision interface:

```python
AgentDecision:
    action
    target
    parameters
    reason
    required_information
    strategy_update
```

Every state-changing action also needs a versioned execution contract:

```python
ActionContract:
    action_id
    allowed_roles
    preconditions
    required_resources
    effects
    conflict_rule
```

Agents propose actions; the engine validates and executes them. Agents cannot directly modify authoritative environment state.

### 4.12 Results dashboard

| Dashboard section | Content |
|---|---|
| Policy comparison | Attendance, eligibility, administrative workload and other outcomes, with repeated-run variation where available |
| Stakeholder impact | Individual agent outcomes and behavioural adaptations |
| Consequence findings | Objective failures, operational bottlenecks and unexpected behavioural patterns |
| Evidence and explanation | Linked event IDs, state changes, calculations, interpretations and counterfactual results |
| Simulation timeline | Environmental events, agent decisions, validation outcomes, conflict resolution, institutional responses and resulting state changes |
| Run details | Run manifest, model/configuration versions and replay access |

There should be no single universal policy score. Policymakers inspect trade-offs.

### 4.13 MVP completion criteria

The MVP is functionally complete when all of the following can be demonstrated end to end:

- [ ] A natural-language policy and education environment description produce a versioned CSR definition.
- [ ] User-provided facts and AI-generated assumptions are visibly distinguished.
- [ ] Generated definitions pass schema, reference, semantic and execution validation before use.
- [ ] Eight agents have distinct goals, constraints, resources, information and memory.
- [ ] Agents make structured, event-triggered decisions that can adapt based on previous events.
- [ ] Simultaneous decisions use consistent snapshots, and conflicting actions are resolved by explicit rules.
- [ ] Agents cannot directly modify authoritative environment state.
- [ ] Attendance, exceptions, queues and eligibility are calculated and updated by the simulation engine.
- [ ] The discovery subsystem separately identifies objective failures, operational bottlenecks and behavioural patterns.
- [ ] At least one noteworthy finding is linked to actual event records, state changes and calculations.
- [ ] At least one controlled counterfactual investigation is completed and labelled as within-model evidence.
- [ ] Run manifests capture the configuration and action records needed to inspect and replay an episode.
- [ ] Runtime controls enforce bounded concurrency and explicit run/LLM-call limits.
- [ ] The three policies can be compared under matched initial conditions and repeated runs.

## 5. Sample MVP run

The following is an illustrative simulation, not measured data or a prediction about a real university.

### Scenario: Does an 80% attendance policy produce unintended institutional consequences?

**Step 1 — Policy submission**

Proposed policy:

> Students must maintain at least 80% attendance in each course to be eligible for examinations. Exceptional circumstances may be considered through formally approved exceptions.

Intended purpose: Improve class participation, encourage consistent attendance and maintain academic standards.

Environment: One educational institution, one course, four student archetypes and four institutional agents.

Priority outcomes: Attendance, examination eligibility, stakeholder impact and administrative workload.

**Step 2 — AI generates the simulation blueprint**

- Minimum attendance: 80%.
- Scope: Per course.
- Exceptions: Formally approved exceptional circumstances.
- Eligibility: Determined using authoritative attendance records.
- Stakeholders: Four students, faculty, advisor, attendance administrator and examination officer.
- Environment: Two sessions per week, twenty planned sessions, ten simulated weeks.
- Outcomes: Attendance, eligibility, exception requests, processing delays, stakeholder differences and behavioural adaptations.

The user reviews and approves the blueprint.

**Step 3 — Agent initialisation**

- Student A initially plans to leave home 30 minutes before class.
- Student C has fixed employment hours and limited scheduling flexibility.
- The administrator has limited exception-processing capacity.
- Each other agent receives its own goals, resources, information and constraints.

**Step 4 — Simulation**

| Period | Event | Agent decisions and consequences |
|---|---|---|
| Weeks 1–2 | Normal operation | Students attend according to initial strategies. |
| Week 3 | Transport disruption | Student A decides to leave earlier; Student C cannot easily adapt due to work. |
| Week 4 | Behavioural adaptation | Student A changes travel buffer; Student C requests advisor assistance. |
| Week 5 | Further disruption | Student C submits a documented exception request. |
| Week 6 | Capacity constraint | Administrator receives more requests than available processing capacity. The request remains pending. |
| Weeks 7–8 | Further interactions | Advisor attempts to support Student C; Student A maintains attendance through the revised strategy. |
| Weeks 9–10 | Eligibility assessment | Examination officer evaluates students using the approved policy and current records. |

**Step 5 — Illustrative student outcomes**

| Student | Attended | Approved exceptions | Final attendance |
|---|---:|---:|---:|
| A — Commuter | 18 | 0 | 90% |
| B — Resident | 19 | 0 | 95% |
| C — Working | 15 | 2 | 83.3% |
| D — Family commitments | 16 | 1 | 84.2% |

For Student C:

\[
\frac{15}{20-2}\times100=83.3\%
\]

Before the two exceptions are approved:

\[
\frac{15}{20}\times100=75\%
\]

This illustrates an operational risk: delayed exception processing can leave an otherwise eligible student temporarily classified as ineligible or at risk at the eligibility checkpoint.

**Step 6 — Consequence discovery**

Finding: **Exception-processing bottleneck creates an eligibility risk.**

Observed sequence:

Transport disruption → Student absence → Exception request → Administrative queue → Delayed decision → Temporary eligibility risk.

Contributing conditions:

- Different student schedule constraints.
- Repeated external disruptions.
- Limited administrative capacity.
- An 80% attendance threshold.
- Exception decisions required before eligibility assessment.

Potential implication: A policy that provides formal exceptions may still produce operational difficulties when the exception process cannot resolve requests before eligibility decisions.

The finding must be supported by the actual agent decisions, environmental events, request records, queue state and eligibility calculations. An agent's generated reason is retained as its stated rationale, not treated as an independently verified explanation of its internal reasoning.

**Step 7 — Guided exploration and counterfactual investigation**

RuleStorm explores:

| Scenario variation | Investigation |
|---|---|
| More frequent transport disruptions | Whether the bottleneck becomes worse |
| Greater administrative capacity | Whether processing delays reduce |
| Reduced advisor availability | Whether students have fewer ways to resolve difficulties |
| Different exception provisions | Whether the policy produces different institutional outcomes |

Random exploration continues alongside targeted exploration.

For the discovered administrative bottleneck, RuleStorm also performs a controlled counterfactual run. It increases administrative processing capacity while keeping the policy, initial agent profiles and external disruption schedule matched. It then compares queue length, processing delay and eligibility outcomes. If the bottleneck disappears in the rerun, this supports the conclusion that capacity is a contributing mechanism within this simulation model. It does not prove that increasing capacity would have the same effect in a real institution.

The run manifest records the model and prompt versions, policy and environment definitions, engine version, initial state, event schedule, configuration and action records. The user can replay the recorded episode to inspect the exact sequence that produced the finding. A fresh experiment may still produce different agent decisions.

**Step 8 — Policy comparison**

The same initial profiles and external conditions are used for strict, flexible and progressive policies. Multiple repetitions account for varied LLM decisions.

| Dimension | Strict | Flexible | Progressive |
|---|---|---|---|
| Attendance enforcement | Direct threshold | Direct threshold with defined exceptions | Early warnings and support |
| Transport-related hardship | Formal exception process | Verified disruption provisions | Early intervention |
| Advisor involvement | As requested | As requested | Proactive |
| Administrative burden | Formal exception processing | Exception processing under defined provisions | Early support and intervention workload |
| Eligibility risk | Can arise from delayed approvals | Depends on defined exception processing | Depends on intervention timing and effectiveness |
| Primary trade-off | Consistency vs flexibility | Flexibility vs administrative complexity | Proactive support vs resource capacity |

**Step 9 — Final output**

RuleStorm presents:

- Policy objective outcomes.
- Attendance and eligibility distributions.
- Individual stakeholder outcomes.
- Behavioural adaptation records.
- Administrative workloads and processing delays.
- Emergent findings and supporting event sequences.
- Comparative results under all three policies.
- Further scenarios worth exploring.

The policymaker decides whether the observed trade-offs are acceptable.

**What the run demonstrates:** Policy interpretation, stakeholder construction, adaptive decisions, institutional interactions, consequence discovery, guided exploration and policy comparison. It does not establish that the same sequence will happen at a real university.

## 6. User journey for the hackathon demonstration

### 1. Landing page

User selects **Create new policy simulation**.

The interface introduces policy testing and explains that RuleStorm explores possible stakeholder responses and consequences.

### 2. Policy input

User enters the 80% attendance policy, intended purpose and educational environment.

The user does not create AI agents manually.

### 3. Blueprint generation and approval

RuleStorm displays:

- Policy interpretation.
- Proposed stakeholder profiles.
- Agent goals and constraints.
- Environmental rules.
- Scenario types.
- Outcomes to monitor.
- User-provided facts versus AI-generated assumptions.
- Validation status for the generated definition.

User approves or edits the blueprint only after the generated definition passes validation.

### 4. Simulation launch

User starts the simulation.

The interface shows the current simulated week, environmental state, active agents and run progress. It also exposes the run ID and configuration details.

### 5. Live simulation and agent interactions

User observes:

- Disruptions.
- Agent decisions.
- Strategy changes.
- Requests and institutional responses.
- Changes to attendance and eligibility.

Clicking an agent reveals its goals, constraints, memory and recent decisions.

### 6. Scenario exploration and discovery

RuleStorm presents noteworthy findings and the scenario conditions that produced them.

User can inspect a discovery and see why additional variations were tested. Each finding links to event records, state changes and calculations. Where appropriate, the user can inspect the matched counterfactual run and replay the recorded episode.

### 7. Policy comparison

User compares strict, flexible and progressive policies using matched conditions and repeated experiments.

The dashboard displays stakeholder and operational trade-offs.

### 8. Final policy assessment

User reviews findings, stakeholder impact, policy trade-offs, event histories and areas requiring further investigation.

The policymaker retains decision-making authority.

### Central demonstration interaction

The strongest moment is when the user clicks a discovered consequence and RuleStorm opens the actual chain of events.

**Question:** Why did the student become ineligible at the eligibility checkpoint?

1. Transport disruption caused missed attendance.
2. Student submitted an exception request.
3. Administrator received more requests than available processing capacity.
4. The student's request remained pending.
5. The examination officer evaluated the current attendance record.

**Root mechanism:** The interaction between an external disruption, student constraints, administrative capacity and eligibility timing.

This demonstrates a functioning simulation rather than a chatbot that simply lists possible policy disadvantages.

## 7. Existing research and related work

There is substantial research around the underlying ideas behind RuleStorm. Research has moved beyond traditional agent-based modelling into combining LLMs with agent-based simulations.

This is encouraging for technical feasibility. It also means RuleStorm should not position itself as the first platform to use AI agents to simulate stakeholder behaviour.

### 7.1 Generative Agents: Interactive Simulacra of Human Behavior (2023)

**Park et al. — ACM UIST 2023**

Paper: https://arxiv.org/abs/2304.03442

One of the foundational works behind LLM-driven generative agents.

The researchers built agents capable of:
- Maintaining memories of previous experiences.
- Reflecting on accumulated memories.
- Planning future actions.
- Interacting with other agents.
- Producing emergent social interactions.

They demonstrated a simulated environment containing 25 agents.

**Relevance to RuleStorm:** Supports the feasibility of stakeholder agents with memory, planning and emergent interactions.

**Limitation:** Does not establish that simulated agents accurately represent real stakeholders or provide validated policy predictions.

### 7.2 Large Language Models Empowered Agent-Based Modeling and Simulation (2024)

**Gao et al. — Humanities and Social Sciences Communications, September 2024**

Paper: https://www.nature.com/articles/s41599-024-03611-3

This paper surveys the integration of LLMs with traditional agent-based modelling.

It examines applications across social, physical, cyber and hybrid systems.

It discusses autonomy, social interaction, perception, reasoning, decision-making and adaptation.

It also identifies challenges involving environmental perception, human behavioural alignment, action generation, simulation evaluation, computational efficiency and scaling.

**Relevance to RuleStorm:** Supports the hybrid LLM-agent and deterministic-environment architecture.

### 7.3 Generative Agent Simulations of 1,000 People (2024)

**Park et al. — Research paper submitted November 2024; Stanford HAI brief, May 2025**

Paper: https://arxiv.org/abs/2411.10109

Stanford brief: https://hai.stanford.edu/news/ai-agents-replicate-human-survey-responses

Researchers created generative agents representing 1,052 real individuals using qualitative interview transcripts.

They evaluated how well agents replicated responses of the individuals they represented across social-science surveys and experiments.

The reported result was that agents replicated individuals' General Social Survey responses 85% as accurately as those individuals replicated their own answers across surveys conducted two weeks apart.

**Relevance to RuleStorm:** Supports a future direction for grounding stakeholder agents in real-world information rather than relying exclusively on generic personas.

**Limitation:** The study uses substantial individual interview data. It does not demonstrate that generic LLM agents can predict how an entire university population responds to arbitrary policies.

### 7.4 Complex System Policy Modelling Approaches for Policy Advice (2024)

Research: https://www.mdpi.com/2079-8954/12/8/302

This research compares Systems Thinking, System Dynamics and Agent-Based Modelling.

It discusses how these approaches can reveal policy side effects, complex stakeholder interactions and nonlinear system behaviour.

**Relevance to RuleStorm:** The underlying idea of simulating policy effects through interacting agents is an established research direction. RuleStorm adds generative AI for agent decisions and natural-language interaction.

### 7.5 PolicySim: An LLM-Based Agent Social Simulation Sandbox for Proactive Policy Optimization (2026)

**Huang et al. — ACM Web Conference 2026**

Research paper: https://arxiv.org/abs/2603.19649

ACM Web Conference 2026 publication: https://doi.org/10.1145/3774904.3792555

Official project repository: https://github.com/renH2/PolicySim

PolicySim is one of the closest research overlaps with RuleStorm.

It is an LLM-based multi-agent simulation framework for proactively evaluating policies before deployment.

Its application domain is social media platforms, where it investigates how recommendation, content filtering and other platform interventions affect user behaviour and ecosystem dynamics.

Its architecture includes:

- LLM-driven user agents.
- User profiles and memory.
- Behavioural simulation.
- Social network interactions.
- Adaptive policy intervention.
- Feedback-driven policy optimisation.

It uses supervised fine-tuning and direct preference optimisation for user agents, and contextual bandits with message passing for adaptive intervention policies.

**Similarity to RuleStorm:** Both approaches aim to stress-test policies through AI-driven agent interactions before real-world deployment.

**Difference in scope:** PolicySim focuses on social media ecosystems and platform interventions. RuleStorm proposes a broader policy-testing platform with heterogeneous institutional stakeholders, structured policy enforcement, operational processes, scenario discovery and inspectable consequences.

This is a meaningful product distinction, but the high-level idea of proactive policy testing through LLM-driven agents is not exclusive to RuleStorm.


#### PolicySim reuse decision

Treat the research paper and the public code repository as separate materials. The paper describes a more advanced research methodology, including SFT/DPO for platform-specific user-agent behaviour and a contextual-bandit intervention mechanism with message passing. Those methods are useful references, but they are not prerequisites for RuleStorm's education MVP.

The official public repository's README describes the released implementation as a simplified version focused on Twitter recommendation/social-network simulation. Its documented components include agent, environment/rules, LLM, evaluation and memory modules. This makes it useful for studying implementation patterns, but it is not a ready-made institutional policy simulation engine.

| Area | RuleStorm decision |
|---|---|
| LLM stakeholder reasoning | Adapt the research methodology; implement institutional stakeholder reasoning independently. |
| Agent decision loops | Independently implement using RuleStorm's structured observations and action contracts. |
| Memory mechanisms | Build memory suited to institutional stakeholders and event histories. |
| Multi-agent communication | Adapt the concept to requests, approvals, referrals and other institutional workflows. |
| Contextual bandits | Consider for future scenario-selection or intervention optimisation; exclude from MVP. |
| SFT/DPO | Exclude from MVP; consider only if later empirical data and a clear calibration need justify training. |
| Twitter/Weibo environment, recommendation logic and platform prompts | Replace with the education CSR, policies and institutional processes. |
| Public repository source code | Do not copy, modify or incorporate unless an applicable software licence or explicit permission is confirmed. |

**Licensing caution (checked 23 November 2026):** The ACM paper's stated Creative Commons Attribution 4.0 licence applies to the paper, not automatically to the separate software repository. At the time of inspection, the official repository's root file listing did not show a `LICENSE` file, and its README did not state a software licence. GitHub's licensing guidance explains that, absent a licence or other permission, default copyright rules apply; public visibility allows viewing/forking under GitHub's terms but does not itself grant general rights to reuse, modify or redistribute the code. Re-check the repository and obtain permission from the maintainers before any code reuse, because repository contents and licensing can change.

Sources: [PolicySim paper (arXiv)](https://arxiv.org/abs/2603.19649) · [ACM publication](https://doi.org/10.1145/3774904.3792555) · [Official PolicySim repository](https://github.com/renH2/PolicySim) · [GitHub guidance on repository licensing](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository).

### 7.6 Multi-Agent Social Simulation (MASS): Protocolizing LLM-Driven Agent-Based Modeling as a Quantitative Research Method (2026)

**Hu and Shen — AI journal, July 2026**

Research: https://arxiv.org/abs/2603.18003

This research proposes a protocolised method for LLM-driven agent-based simulation.

It uses:

- Structured agent roles.
- Round-based scheduling.
- Information controls.
- Background environment rules.
- Structured outputs.
- Validation checks.
- Reason-action logs.
- Replication records.

It examines examples involving minimum-wage policy changes, Brexit-era digital campaigning and tourism-related public opinion.

**Relevance to RuleStorm:** Useful methodological reference for event logging, action validation, matched runs and reproducibility.

### 7.7 Validation is the Central Challenge for Generative Social Simulation (2025/2026)

**Larooij and Törnberg — Artificial Intelligence Review, published November 18, 2025; 2026 issue**

Research: https://link.springer.com/article/10.1007/s10462-025-11462-6

This systematic review examines how LLM-powered agent-based simulations are validated.

It identifies continuing problems with:

- Empirical grounding.
- Calibration.
- Reproducibility.
- Behavioural consistency.
- Black-box decision-making.
- Cultural biases.
- Stochastic outputs.

The researchers argue that plausible-sounding agent behaviour is not sufficient evidence of operational validity.

**Relevance to RuleStorm:** Directly supports distinguishing between:
1. What happened in the simulation.
2. Why agents took particular actions.
3. What patterns the simulation observed.
4. What the results might imply.
5. What still requires real-world investigation.

This is essential for product credibility.

## 8. What the research means for RuleStorm

| RuleStorm capability | Research support | Assessment |
|---|---|---|
| AI stakeholder agents | Generative Agents, 1,000 People | Established research direction |
| Agent memory and adaptation | Generative Agents | Demonstrated mechanism |
| Multi-agent interactions | Generative Agents, MASS | Established research direction |
| LLM + agent-based simulation | 2024 LLM-ABM survey | Active research area |
| Policy impact exploration | Traditional ABM research, PolicySim | Established and developing |
| Proactive policy testing | PolicySim | Directly related existing work |
| Deterministic policy enforcement alongside AI decisions | Hybrid modelling literature and simulation practice | Technically sound architecture |
| Guided exploration | PolicySim and other adaptive simulation approaches | Feasible, implementation-dependent |
| Emergent consequence discovery | Generative Agents and ABM research | Demonstrable, but not exhaustive |
| Evidence-backed policy explanations | MASS and validation literature | Technically achievable and methodologically important |
| Empirically valid real-world behaviour | Stanford research and validation reviews | Requires further grounding and testing |

## 9. Where RuleStorm can differentiate itself

The differentiation should not be based on simply having multiple AI agents.

Define the RuleStorm differentiator as the combination of five mechanisms:

1. **Policy-to-simulation translation:** A non-technical policymaker submits a natural-language policy and environment description. RuleStorm converts them into a versioned, validated Canonical Simulation Representation.
2. **Stakeholder behaviour inside a governed environment:** Agents make flexible decisions, but versioned action contracts and a deterministic environment govern what can actually happen.
3. **Consequence discovery rather than simple scenario execution:** Separate discovery mechanisms investigate objective failures, operational bottlenecks and unexpected behavioural patterns arising from stakeholder interactions and external conditions.
4. **Dual-purpose exploration:** It investigates both policy objective failures and unexpected behavioural patterns, retaining random exploration alongside guided search.
5. **Inspectable policy comparison:** Findings link to recorded events, state changes and calculations; controlled counterfactuals investigate mechanisms within the model; alternative policies can be tested under matched conditions and repeated runs.

These five elements together form the product proposition.

Do not claim that this combination has never been researched or implemented elsewhere without a dedicated competitor, patent and literature review. PolicySim is particularly relevant prior work, so RuleStorm should be positioned around the broader institutional and cross-domain workflow rather than claiming invention of pre-deployment LLM policy simulation.

## 10. Research and validation requirements

RuleStorm's credibility should be developed alongside its functionality.

| Validation level | What is checked | What RuleStorm should establish |
|---|---|---|
| Internal validity | Is the generated model executable and the simulation logically correct? | CSR schemas, references, units, dependencies, permissions, calculations, event ordering, conflict resolution and state transitions are validated and tested |
| Behavioural validity | Are agent responses plausible under defined assumptions? | Agents respond consistently with profiles, constraints and available information; repeated runs reveal behavioural variation |
| Mechanism robustness | Does a discovered mechanism persist under controlled variations? | Matched scenario variations and within-model counterfactual runs test whether the outcome changes when a proposed contributing condition changes |
| External validity | Do simulated patterns correspond to actual systems? | Expert feedback, institutional observations and suitable real-world evidence support the model |

For the educational MVP, the immediate objectives are internal validity, inspectable behavioural plausibility, run provenance and basic mechanism-robustness checks through controlled counterfactuals. These checks establish properties of the simulation model, not real-world causality.

The longer-term product must develop external validation through appropriate empirical research.

For example, a university could eventually help calibrate RuleStorm using anonymised information about attendance patterns, exception processing times and institutional capacity.

The purpose would not be to reproduce identifiable students. It would be to evaluate whether simulated mechanisms and aggregate outcomes are consistent with the institution's observed system.

## 11. Final consolidated product positioning

### RuleStorm — AI-Powered Policy Simulation and Stress Testing

*Discover what happens when policies meet real people.*

RuleStorm combines natural-language policy understanding, generative stakeholder agents, adaptive behavioural simulation, deterministic environmental rules, scenario exploration and evidence-backed consequence analysis.

Its purpose is to uncover plausible behavioural adaptations, unintended consequences, stakeholder conflicts and operational bottlenecks that may otherwise be overlooked during policy design.

### MUST HAVE — MVP

A complete educational simulation with:

- Policy interpretation and blueprint generation with visible assumptions.
- Minimal reusable Canonical Simulation Representation for the education environment.
- Schema, reference, semantic and dry-run validation of generated definitions.
- Eight AI stakeholder agents with individual goals, constraints, resources and memory.
- Adaptive decisions and agent interactions.
- Governed event-driven execution with snapshots, action validation, conflict resolution and state commits.
- Deterministic institutional environment, calculations and workflows.
- External disruptions and interacting environmental events.
- Three distinct discovery mechanisms: objective failures, operational bottlenecks and behavioural patterns.
- Random plus guided scenario exploration and novelty comparison.
- Evidence-backed findings linked to event records, state changes and calculations.
- At least one controlled within-model counterfactual investigation.
- Run manifests, version/provenance records and replay of recorded episodes.
- Runtime controls for event-triggered calls, affected-agent selection, bounded concurrency and run/call budgets.
- Three-policy comparison under matched conditions and repeated runs.
- Outcome, trade-off, evidence and run-details dashboard.

### NICE TO HAVE — Extended product

- Larger populations and more advanced agent memory.
- Sophisticated ML-guided exploration, including TPE, evolutionary search or contextual bandits where appropriate.
- Advanced behavioural pattern detection and large-scale pattern clustering.
- More sophisticated cross-domain environment generation and custom environment builder.
- Rich visualisations and exportable reports.
- Extensive statistical and uncertainty analysis across larger experiment batches.
- Real-world behavioural validation and calibration with expert feedback and institutional data.
- Education expansion and additional policy domains.
- Model training approaches such as SFT/DPO where justified by validated data and a clear need.
- Distributed and scalable simulation infrastructure.

### Final assessment

**Logical consistency:** Strong, provided policy interpretation, the canonical simulation model, agent decisions and environmental enforcement remain separate and are connected through validated contracts.

**Technical feasibility:** High for the bounded educational MVP. Existing LLMs, structured outputs and conventional simulation engineering are sufficient. A universal dynamic environment generator remains a larger extended-product objective.

**Research support:** Strong and growing. There is established research in agent-based policy modelling, generative agents, LLM-driven simulation and proactive policy testing.

**Main engineering challenges:** Reliable generated definitions, governed execution order, meaningful consequence discovery, evidence provenance, reproducibility and API cost/latency.

**Main research challenge:** Demonstrating that simulated behaviours are sufficiently representative of real stakeholders for meaningful policy decisions.

**MVP success criterion:** Demonstrate that an ordinary-language policy and environment description can be translated into a validated, versioned simulation model; that AI stakeholders make constrained and adaptive decisions within a governed environment; that their interactions produce inspectable outcomes; that separate discovery mechanisms identify a noteworthy consequence; and that RuleStorm can investigate that mechanism through a controlled within-model counterfactual and compare alternative policies under matched conditions.

The MVP should establish the complete mechanism and its internal reliability. The extended product should establish external validity, scale and applicability across domains.

## 12. AWS implementation and Techfest Campus to Cloud Hackathon alignment

This section maps the existing RuleStorm architecture and MVP to AWS services for the Techfest 2026-27 Campus to Cloud Hackathon sponsored by AWS. It adds a deployment and infrastructure plan; it does not change RuleStorm's product vision, stakeholder capabilities, simulation scope or discovery requirements.

The supplied problem statement requires a working prototype deployed on AWS Free Tier, a live project URL that remains accessible through Demo Day, an idea brief, a build summary naming the AWS services used and why, a code repository (public repository encouraged), and a demo video under three minutes. The submission deliverables must be placed together in one Google Drive folder and submitted through the Techfest portal by the team leader. The Finals demo is three minutes followed by two minutes of Q&A. The evaluation weights are Bharat Impact (30%), Working AWS Build (25%), Innovation (25%), and Demo and Storytelling (20%). See the supplied *Techfest 2026-27 — Campus to Cloud Hackathon sponsored by AWS* problem statement, pages 1-4.

### 12.1 Where AWS fits into RuleStorm

AWS should provide the deployed application runtime, managed model inference, persistent storage, asynchronous job handling, monitoring and access control. The existing Python simulation logic, Canonical Simulation Representation (CSR), event engine, discovery mechanisms and agent contracts remain application-level components; they run on AWS rather than being replaced by AWS services.

| RuleStorm component | AWS service | How it is used in RuleStorm | MVP priority |
|---|---|---|---|
| Live application and Streamlit UI | Amazon EC2 | Hosts the existing Streamlit application and Python application services so the prototype has a public endpoint available through Demo Day. | MUST HAVE |
| Container image (if using Docker) | Amazon Elastic Container Registry (ECR) | Stores the versioned RuleStorm container image used to deploy the same tested build to EC2. | Recommended for deployment |
| Policy interpretation and CSR generation | Amazon Bedrock | Provides managed foundation-model inference for policy interpretation, environment/CSR drafting, stakeholder-profile suggestions and blueprint explanations. | MUST HAVE for AWS-hosted LLM inference |
| Agent reasoning and adaptive decisions | Amazon Bedrock | Invoked for meaningful, event-triggered agent decisions and strategy updates; not called for routine state updates or deterministic calculations. | MUST HAVE |
| Scenario variation and finding explanations | Amazon Bedrock | Helps propose structured scenario variations and explain candidate findings, while the discovery engine and evidence records remain authoritative. | MUST HAVE, bounded calls |
| Run status and structured simulation state | Amazon DynamoDB | Stores run metadata, run status, current agent/environment snapshots, queue/request status and indexes for findings. | MUST HAVE for deployed persistence |
| CSR definitions and simulation artefacts | Amazon S3 | Stores versioned CSR JSON, run manifests, event-log files, scenario configurations, result snapshots and generated reports. | MUST HAVE |
| Asynchronous simulation jobs | Amazon SQS | Queues user-submitted simulation runs or bounded scenario batches so the web request does not have to wait for the complete experiment. | MUST HAVE if runs execute asynchronously |
| Simulation worker | Python worker on EC2; optionally AWS Lambda for bounded tasks | The MVP worker consumes SQS jobs, runs deterministic simulation steps and event-triggered agent calls, then persists progress. A Lambda worker is an optional later deployment pattern for independent, bounded chunks. | EC2 worker: MUST HAVE; Lambda worker: NICE TO HAVE |
| Logs and operational monitoring | Amazon CloudWatch and CloudWatch Logs | Captures application errors, simulation failures, run duration, LLM-call counts, token usage where available, worker health and resource utilisation. | MUST HAVE |
| Identity and permissions | AWS Identity and Access Management (IAM) | Gives the application and worker scoped roles to access only the required Bedrock, S3, DynamoDB, SQS and monitoring resources. Avoid hard-coded AWS access keys. | MUST HAVE |
| Cost monitoring | AWS Budgets and AWS Billing / Cost Management | Sets budget alerts and monitors credit use, Bedrock inference, compute, storage and data transfer. | MUST HAVE |
| Multi-user institutional sign-in | Amazon Cognito | Can provide user authentication when the prototype expands beyond a controlled public demo. | NICE TO HAVE |
| Separate serverless API architecture | Amazon API Gateway and AWS Lambda | Can expose application APIs and execute short, independently checkpointed tasks if the UI and backend are later separated. | NICE TO HAVE for this Streamlit MVP |

**Keep the current development stack intact:** Streamlit, Python, Pydantic, Pandas and Plotly remain the application technologies. SQLite can remain useful for local development and tests. For the AWS-hosted deployment, use DynamoDB for operational state and S3 for durable simulation artefacts so the live demo is not dependent on the EC2 instance's local filesystem. The deployed application should call Amazon Bedrock through its AWS SDK integration instead of requiring a separately managed model API key.

### 12.2 Recommended AWS architecture for the hackathon MVP

Use a deliberately small, understandable AWS deployment rather than introducing a large microservices architecture.

```text
                         User browser
                              |
                              v
              Public RuleStorm application URL
                              |
                              v
              Amazon EC2 - ap-south-1 (Mumbai)
          +----------------------------------------+
          | Streamlit UI                           |
          | Python application / API               |
          | CSR and policy validators              |
          | Governed event-driven simulation engine|
          | SQS-consuming Python simulation worker |
          +----------------------------------------+
                 |             |             |
                 |             |             +------------------+
                 |             |                                |
                 v             v                                v
          Amazon Bedrock   Amazon SQS                    Amazon CloudWatch
          (LLM inference)  (run/batch queue)              (logs/metrics)
                                |
                                v
                     Worker processes queued
                     simulation/scenario batches
                                |
                    +-----------+-----------+
                    |                       |
                    v                       v
             Amazon DynamoDB            Amazon S3
             Run status, state,         CSR versions, manifests,
             agent snapshots,           event traces, results,
             request/finding indexes    report artefacts

          Amazon ECR stores the versioned Docker image.
          IAM roles grant least-privilege service access.
          AWS Budgets monitors the planned spend.
```

For the MVP, the Streamlit app and a separate Python worker process can run on one small EC2 instance. SQS still decouples a submitted simulation from the interactive UI and allows the worker to process bounded jobs. Keep worker concurrency low for the eight-agent prototype. The simulation engine checkpoints progress to DynamoDB and writes event/result artefacts to S3.

If a later version moves independent scenario batches to Lambda, split the work into checkpointed tasks. Standard AWS Lambda function execution has a maximum timeout of 900 seconds (15 minutes); do not place an unbounded full simulation or an entire large comparison experiment in one invocation. See the [AWS Lambda timeout documentation](https://docs.aws.amazon.com/lambda/latest/dg/configuration-timeout.html).

### 12.3 AWS region and Amazon Bedrock selection

Use **Asia Pacific (Mumbai), `ap-south-1`**, as the first-choice deployment Region for the application, database, object storage, queue and monitoring where the required services are available. This is a practical default for an Indian-user demonstration and keeps the main application components in one Region.

Amazon Bedrock Runtime has an endpoint in Mumbai, but foundation-model availability is model- and inference-mode-specific. Choose a model only after checking that its **in-Region** inference mode is supported in `ap-south-1`, that it is enabled for the AWS account, and that its output quality is sufficient for the required structured policy/agent schemas. The current AWS regional model table lists GPT-OSS 20B as one model with in-Region support in Mumbai; this is an example to evaluate, not a fixed model requirement. See [Amazon Bedrock model and Region compatibility](https://docs.aws.amazon.com/bedrock/latest/userguide/models-region-compatibility.html).

The current AWS documentation for the new Free Tier account experience states that multi-Region and cross-Region features are not supported on that plan. Therefore, for a Free Tier submission, prefer a model with in-Region support in the chosen Region rather than depending on cross-Region inference. Recheck the current service and model availability in the AWS console before deployment. See [AWS supported services for the new Free Tier experience](https://docs.aws.amazon.com/in_en/accounts/latest/reference/supported-services-sign-up-new.html).

### 12.4 Data placement and trust boundaries

| Data | Storage location | RuleStorm responsibility |
|---|---|---|
| Current run status and progress | DynamoDB | Track queued, running, completed and failed runs. |
| Current agent and environment snapshots | DynamoDB | Persist the latest authoritative state/checkpoint required to continue a run. |
| CSR and policy versions | S3, with version identifiers referenced in DynamoDB | Preserve the exact validated definitions used by each run. |
| Run manifest | S3; searchable run ID/status metadata in DynamoDB | Preserve model, prompt, policy, environment, engine and scenario configuration. |
| Event and action history | S3 as run-specific structured JSON/JSONL files; summary/index in DynamoDB | Preserve proposed actions, validation, conflict resolution, committed state changes and resulting events. |
| Scenario definitions and results | S3 | Preserve generated scenarios, metrics and result snapshots. |
| Finding evidence links | DynamoDB | Link a finding to run ID, event IDs, state changes and calculations. |
| Application and worker logs | CloudWatch Logs | Diagnose failures and monitor live demo health. |

The simulation engine remains the source of truth. Bedrock-generated text is not treated as authoritative state. The LLM receives only the context needed for its current task; the application validates its structured output before committing any action or definition.

### 12.5 AWS Free Tier and cost guardrails

The supplied Techfest brief says to build and deploy the prototype on AWS Free Tier and advertises access to up to USD 200 in AWS credits (problem statement, pages 3-4). AWS's current Free Tier information describes up to USD 200 in credits for new customers over six months, subject to the account plan and eligibility conditions. AWS also lists services including EC2, ECR, Bedrock, DynamoDB, S3, SQS, CloudWatch, IAM and AWS Budgets as supported in its new Free Tier experience. These offers and service rules are subject to AWS's current terms; service inclusion must not be interpreted as unlimited usage at no cost. See [AWS Free Tier](https://aws.amazon.com/free/), [AWS Free Tier FAQs](https://aws.amazon.com/free/free-tier-faqs/) and [the supported-service list](https://docs.aws.amazon.com/in_en/accounts/latest/reference/supported-services-sign-up-new.html).

Apply these controls:

- Select an EC2 size, storage configuration and Region that are allowed by the chosen AWS Free Tier account plan; check the console's Free Tier indicators before provisioning.
- Use one EC2 instance and one low-concurrency worker for the MVP. Do not introduce EKS, large fleets, provisioned model throughput or unnecessary managed services.
- Set an AWS Budget and billing alerts before running Bedrock experiments.
- Set application-level limits for model calls, input/output token budgets, scenario batches and repeated runs.
- Cache approved policy/CSR interpretations where appropriate; do not re-run policy interpretation for every scenario when the definition has not changed.
- Monitor Bedrock invocations, input/output tokens, latency, EC2 hours, EBS storage, S3 storage, DynamoDB usage and data transfer.
- Keep the public application running through Demo Day as required by the brief; stop nonessential test resources, not the live demo environment.
- Do not claim that the prototype is free to operate at any scale. Record actual AWS services and measured usage in the Build Summary.

### 12.6 How the AWS services support the RuleStorm workflow

| RuleStorm workflow step | AWS implementation |
|---|---|
| User opens the demo | Browser reaches the Streamlit application hosted on EC2. |
| User submits a policy | Streamlit sends the policy and purpose to the Python policy modeller. |
| Policy and CSR are generated | Python invokes Amazon Bedrock; the validator checks the structured output. The approved, versioned CSR is stored in S3. |
| Agents are initialised | Python creates structured agent state and stores run/agent metadata in DynamoDB. |
| User starts a simulation | Application creates a run record in DynamoDB and places a run or scenario-batch message on SQS. |
| Simulation progresses | Python worker consumes the queue, executes snapshot-based decisions and deterministic transitions, invokes Bedrock only for affected agents, and checkpoints state. |
| Events and evidence are recorded | Run-specific event/action traces and manifests are stored in S3; indexes and current state are updated in DynamoDB. |
| Consequence discovery runs | Python discovery mechanisms analyse stored metrics and event sequences; Bedrock can help label or explain candidates using retrieved evidence. |
| Counterfactual and policy comparisons run | New matched experiment jobs are placed on SQS; results are stored under separate run IDs and compared. |
| User inspects findings | Streamlit reads the findings and evidence links from DynamoDB/S3 and displays the timeline and comparison. |
| Team monitors the live demo | CloudWatch captures logs/metrics; AWS Budgets and billing alerts track cost. |

### 12.7 India problem and impact framing for the hackathon

For the supplied problem statement, RuleStorm's initial real-world problem should be presented narrowly and clearly:

**Indian educational institutions create and enforce policies that affect students with different real-life constraints, but policymakers may not have a practical way to examine how those rules interact with student behaviour and institutional capacity before implementation.** A strict attendance rule, for example, can affect a long-distance commuter, a student with fixed work hours and a student with family responsibilities differently. It can also create additional work for faculty, advisors and administrators.

RuleStorm gives institutional decision-makers a way to stress-test such policies before rollout. It is a decision-support tool for institutions; it does not directly replace student services or make policy decisions on behalf of a university.

To support the brief's **Bharat Impact** criterion (30%), do not present simulated outcomes as measured improvements for Indian students. Where feasible, validate the use case with students, faculty or an academic administrator and track pilot measures such as:

- Time required for a policymaker to create and review a policy simulation blueprint.
- Number of stakeholder constraints represented and confirmed by a domain reviewer.
- Number of distinct, evidence-linked risks or bottlenecks surfaced in a controlled test set.
- Share of findings that a domain reviewer considers relevant for further investigation.
- Time required to compare policy alternatives against the same scenario conditions.
- Whether the review leads to a policy clause, exception process or administrative workflow being reconsidered before implementation.

For a hackathon prototype, report the measurement method and the actual test results. If no real institutional pilot has been run, label the impact as a potential benefit demonstrated through a synthetic simulation, not as a proven improvement in student outcomes.

### 12.8 Alignment with Techfest submission and judging requirements

| Techfest requirement | RuleStorm submission evidence |
|---|---|
| Live prototype deployed on AWS and accessible through Demo Day | Public URL for the EC2-hosted RuleStorm application; verify it remains available for the required period. |
| Idea Brief | Explain the Indian institutional policy-testing problem, intended users, RuleStorm workflow and potential impact. |
| Build Summary listing AWS services and why | Include the service mapping in Sections 12.1-12.6 and report the services actually deployed, not merely planned. |
| Code repository (public encouraged) | Provide the team's repository with setup/deployment instructions and no committed credentials or secrets. |
| Demo video under three minutes | Show the policy input, generated/validated CSR, adaptive stakeholder decisions, an evidence-linked finding and policy comparison. |
| Google Drive folder submission | Place the idea brief, build summary, code repository link, demo video and live prototype URL together in one folder; the team leader submits the folder link through the Techfest portal. |
| Finals live demo | Prepare a three-minute live demonstration followed by readiness for two minutes of judge Q&A. |

The supplied brief gives these evaluation weights: Bharat Impact 30%, Working AWS Build 25%, Innovation 25%, and Demo and Storytelling 20% (problem statement, page 4). The AWS deployment therefore needs to be visible in the live prototype and explained in the Build Summary, not only mentioned in slides.

The supplied brief lists the Round 1 submission deadline as **30 November 2026, 11:59 PM IST**, results by **5 December 2026**, and the offline Demo Day as **17 December 2026** (problem statement, page 4). Check the official Techfest portal for any updates.

### 12.9 Recommended AWS build summary

For the submission's Build Summary, describe the services actually used in this concise form:

| AWS service | Why RuleStorm uses it |
|---|---|
| Amazon EC2 | Runs the live Streamlit application and Python simulation engine/worker. |
| Amazon Bedrock | Provides managed LLM inference for policy/CSR generation and event-triggered stakeholder decisions. |
| Amazon DynamoDB | Stores run metadata, current simulation state, agent snapshots and finding indexes. |
| Amazon S3 | Stores versioned CSR definitions, run manifests, event/action traces and result artefacts. |
| Amazon SQS | Decouples the UI from simulation execution by queueing run and scenario-batch jobs. |
| Amazon ECR | Stores the versioned application container image, if Docker is used. |
| Amazon CloudWatch | Collects logs and operational metrics for the deployed prototype. |
| AWS IAM | Grants least-privilege access between the application and AWS services. |
| AWS Budgets | Alerts the team to AWS spend and helps control use of credits. |

Do not list optional services such as Lambda, API Gateway or Cognito as implemented unless they are actually part of the deployed build.

### 12.10 AWS documentation references

- [Techfest 2026-27 — Campus to Cloud Hackathon sponsored by AWS](uploaded competition problem statement, pages 1-5).
- [AWS Free Tier](https://aws.amazon.com/free/).
- [AWS Free Tier FAQs](https://aws.amazon.com/free/free-tier-faqs/).
- [AWS services supported in the new Free Tier experience](https://docs.aws.amazon.com/in_en/accounts/latest/reference/supported-services-sign-up-new.html).
- [Amazon Bedrock model and Region compatibility](https://docs.aws.amazon.com/bedrock/latest/userguide/models-region-compatibility.html).
- [AWS Lambda function timeout](https://docs.aws.amazon.com/lambda/latest/dg/configuration-timeout.html).
