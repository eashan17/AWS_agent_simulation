# RuleStorm frontend plan (for approval)

Written 25 Nov from docs/USER_JOURNEY.md, docs/BRIEF.md, the API's real responses (run `demo`, run `L-960f5653`, blueprint `B-da347452`, curfew run `L-d50a0a92`) and the design references. Revised the same day: **the map is a plain layout of places with no drawn route; agents' movement and trails show the way they go; time is shown as time passing** (see 3).

Two rules shape everything below:
- **Nothing is built for one scenario.** Every screen reads the template's own words (`terms`, `calendar`, `people`, `roles`, `parameters`) and the run's timeline. The attendance demo and the hostel curfew render through the same components.
- **One product, two modes.** The workspace screens (setup, review, analysis) are calm and flat. The simulation is the one place with motion. Both use the same tokens, glass surfaces and person colours, so the stage reads as part of the workspace.

## 1. Theme and visual direction

**"Glass workspace, live map."** The palette and surfaces come from the Wattbank dashboard; mono eyebrows and the dotted field come from MatrAIx.

| Token | Value | Use |
|---|---|---|
| Canvas | `#EEF1F6` with a blurred blue haze (top left) and orange haze (bottom right) | App background, like Wattbank's frosted backdrop |
| Glass | white at 72% + 18 px backdrop blur + 1 px white edge | Sidebar, cards, panels, map buildings |
| Ink | `#0D1117` | Text; the primary pill button (Wattbank's "Export PDF") |
| Blue | `#2F6BFF` / `#DCE7FF` | Selection, active nav, chart fill, "recorded fact" |
| Orange | `#FF7A1A`, gradient `#FFE7D3 → #FF8A3D` | Attention only: disruptions, the hero finding card, the check marker |
| Green / red | `#14A06B` / `#E5484D` | Status dots and ✓ / ✕ only |
| Radius | 10 / 20 / 28 px | Chips / cards / panels |
| Type | Geist (text, headings), Geist Mono (IDs, eyebrows, calculations) | One quiet family; mono marks the evidence trail |

Rules: the primary action is always the **black pill**, one per screen. Secondary is a white glass pill. Orange is never a button: it means "look here".

## 2. Component architecture

Four layers. Screens only compose; they contain no drawing code.

```
web/src
  ui/       primitives, no RuleStorm knowledge
            Button · Card · Badge · Chip · Tabs · Stepper · TextArea+counter · StatTile
            Banner · EmptyState · Progress · Spinner · IdTag (copyable) · icons · AppShell/Sidebar/PageHeader
  sim/      the simulation kit: knows worlds, not attendance
            World (SVG map) · scenery (Terrain, House, DutyBuilding, Desk, Gate, SupportCorner, Hazard)
            Pebble agent · Trail · Bubble · Clock (HUD) · TimeRuler · PlaybackBar
            layout.js  template roles → zones and posts
            director.js  timeline events → world state at a moment, plus the playback clock
  domain/   RuleStorm pieces built from ui/ + sim/
            EvidenceLabel · FactBadge · EventRow/EventFeed · PeopleStrip · PersonCard
            FindingCard · HeroFinding · EvidenceChain · CalcBlock · MissChart · ParamRow · DisruptionList
            WaitingState · ApiErrorBanner
  screens/  Home · Setup · Review (blueprint + stress test) · Simulation · Analysis (tabs) · Runs
  lib/      api.js (fetch + real error causes) · router.js (hash routes) · words.js (template terms) · session.js
```

**How a new scenario is supported:** ship a new template on the server; no screen changes. `layout.js` maps roles to map zones by the **rules they run** (`recorder` → duty zone, `queue_processor` or whoever decides requests → request desk, `checker` → check gate); the most numerous AI role becomes the travelling agents; other AI staff stand at their zone or in a support corner. `words.js` supplies every label from `terms` and `calendar`.

## 3. Agents, environment, and time

### The map is a layout of places, nothing more
The map is a top-down layout of **where people are and what they are doing at the current moment**. It has **no drawn road and no fixed route**: just places on an open dotted field, arranged by role. Nothing on it stands for a week or a session.
- **Homes** (left): one house per travelling person, in their colour.
- **Duty zone** (centre): the classroom; for the curfew, the hostel.
- **Request desk**: its capacity drawn as slots; filed requests fill the slots; overflow waits outside in orange; decisions pop up as ✓ / ✕.
- **Check gate**: people go to it when the check runs and get ✓ / ✕ (or "!" for a ladder step such as a warning).
- **Support corner**: AI staff with no zone of their own (advisor, guardian).
- **Rule-run roles** (attendance office, exam officer, gate security) are drawn as **machines with a gear** at their zone, never as people: "run by rules, not AI" is visible.
- **Disruptions** appear as a hazard marker in open ground between homes and the duty zone, while they are happening, with their delay and who they affect. People held up by them stop there.
- Ambient life, which carries no meaning: drifting cloud shadows, swaying shrubs, idle bobbing and blinking.

**The route is what the agents do.** Each agent moves straight (with a slight natural curve) from where it is to where an event puts it, leaving a fading trail in its colour. The trails, not a drawn road, show the ways people went: home → class, home → stopped at the storm, class → desk, desk → gate.

### Agents
A **"pebble" mascot**: a rounded body in the person's colour, two eyes that look where it walks, an antenna dot, a bob while walking and a fading trail behind it. States: idle · walking · thinking (their own reason in a bubble) · speaking (advice, a filing, a correction) · refused (red ✕ and the refusal in plain words) · carrying a request slip · present / absent pip · passed / failed badge. AI staff (faculty, advisor, warden, guardian) stand at their posts and talk; a dashed line shows who they are talking to.

Movement always means something: an agent walks only when an event changes where they are (recorded present → walks to the duty zone; held up by a disruption → stops at the hazard; files a request → walks to the desk; check → walks to the gate; end of week → home). There is no path to follow: it goes there directly, and its trail draws the way.

### Time is shown as time passing
- **Clock (on the map, top left, glass)**: "Week 5 of 10 · Session 9" with a ring that sweeps as the current session plays out, and a light dusk tint for night steps (curfew). At the end of a period it reads "End of week 5".
- **Time ruler (under the map)**: a flat timeline of the term with each period divided into its steps, a playhead moving left to right, disruption periods tinted orange and the check marked. Clicking it jumps in time.
- **Playback bar**: play / pause, restart, skip to end, speed 1× 2× 4× 8×, and a scrubber showing the current event ID.
- The **director** plays the recorded timeline in order (finished runs) or follows it while polling (live runs). Every change on the map comes from one `event_id`, which the feed highlights. It never invents an event.

## 4. Layout, sidebar and navigation

- **Glass sidebar** (left, 248 px): wordmark; **Overview · Setup · Simulation · Analysis · Runs**. Simulation and Analysis follow the current run (the demo by default) and show its ID. At the bottom: the "simulation, not prediction" note and a live server status dot.
- **Page header** on every screen: a mono eyebrow with the step ("STEP 3 OF 4 · SIMULATE"), the title, one sentence, IDs and status, and **the single primary action on the right**.
- **Workflow stepper** under the header: Setup → Review → Simulate → Analyse. Done steps are ticked, the current step is dark, and later steps say what they do. For a recorded run, Setup and Review read "done for this recorded run".
- Phone: the sidebar becomes a top bar with a menu, the map scales to the width, and the layout is read-only with no sideways scrolling.

## 5. Setup → Demo → Analysis

| Step | Screen | The user gives | Primary action | What happens |
|---|---|---|---|---|
| 1 Setup | Setup | Policy, purpose and environment (example chips fill them; 2,000-character counters) | **Build the simulation** | Saves the policy and builds the blueprint. A 15–30 s waiting state shows a seconds counter and the pebbles gathering |
| 2 Review | Review | Reads the facts (blue) against the assumptions (orange, dashed) | **Approve**, then **Run this term** (or **Stress-test it first**) | Freezes the values and starts the run |
| 3 Simulate | Simulation | Watches, filters, clicks a person to follow them | **See what went wrong** (when finished) | Opens Analysis |
| 4 Analyse | Analysis tabs | Picks a finding, or a condition to change | **Show the evidence** · **Run the what-if** | Shows the evidence chain, then runs the what-if and the comparison |

**Demo path:** Overview → **Open the demo run** → Simulation (finished; plays from the start, with skip-to-end) → Analysis → Evidence for `demo-F1`.

**Every error names its real cause** (from docs/USER_JOURNEY.md): a 409 with a `run_id` gives "Another simulation is running right now" and **Watch it**; a 429 gives the daily limit sentence and never retries; a 422 shows the server's sentence under the field; a timeout, a server error and no answer from the server each get their own sentence.

## 6. Post-demo analysis (tabs)

`Summary · Findings · Evidence · What if? · Compare`, one focused view each:
- **Summary:** stat tiles (decisions, model calls, refused actions, requests filed); the **orange hero card** for the first finding ("working · 72.7% · not eligible"); a **records chart** of each person's absences by week, counted from the run's own records with corrections applied, with disruption weeks shaded and a "Check" pill like Wattbank's "Optimal"; a people table (check result, decisions, last stated reason).
- **Findings:** one card per finding: kind badge, title, who and when, the figure, the "if approved" figure for bottlenecks, and its size. The empty state never invents a finding.
- **Evidence (hero):** the vertical chain from the disruption to the check. Each step shows its ID, week · session, label badge, sentence, from → to state change, the person's own quoted reason, and the highlighted calculation with "✓ recomputed from this run's records". A time ruler above marks the weeks the chain spans.
- **What if?:** one environment condition with its description and its current value, the new value inside its range, the "same people, same disruptions" sentence, and the new run's progress inline.
- **Compare:** the always-visible "within-model evidence, not real-world causality" banner, what changed, two columns of measures, the check table with flipped rows highlighted, the AI-choice note, and **You decide** (no AI verdict, no score).

## 7. Keeping the two modes one product

- Same tokens, glass and type everywhere. Map places are glass cards on the same dotted field as the workspace.
- **Person colours are assigned once per run** and reused on the map, the feed, the chart, the tables and the evidence chain.
- **One look per label, everywhere:** recorded fact (blue, solid) · calculated (ink, mono) · AI interpretation (orange, dashed, quoted). Blueprint values use fact (blue) and assumption (orange, dashed).
- The pebble appears in the workspace too (person cards, people table, evidence quotes, the waiting state). The time ruler appears in Review (where disruptions fall), Simulation (the playhead) and Evidence (where the chain falls).

## Things to confirm
1. **Serving the UI:** `rulestorm/api.py` doesn't serve `web/dist` yet, and `.gitignore` ignores `dist/`. The plan adds a small static-files mount at the end of `api.py` (no `/api` route changes) and a `!web/dist/` exception. Otherwise the UI only runs through `npm run dev`.
2. **Gate:** slices 14 (CloudWatch) and 15 (strict vs flexible comparison) are still `todo`; both are marked "after the UI".
3. **Fonts** load from Google Fonts (one `<link>`). Bundling them would add a dependency.

## Not in this build
Strict vs flexible vs progressive comparison (slice 15), repeated runs, a server-side list of recent runs (the Runs page keeps the IDs opened in this browser).
