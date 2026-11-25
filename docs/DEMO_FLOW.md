# Demo flow: the exact click-through

For the Round 2 live demo (3 min + 2 min Q&A) and as the shot list for the Round 1 video (under 3 min). Built from docs/USER_JOURNEY.md, docs/BRIEF.md, docs/RULES.md and the UI as it is in `web/src` (25 Nov). Every ID below was checked on the live server on 25 Nov unless marked **to record**.

Link: https://d2emiyaz9dq4bi.cloudfront.net (the app uses `#/...` addresses, so every screen below can be bookmarked).

## What the demo must prove (from the judging weights)
| Criterion | Weight | Where it lands in the demo |
|---|---|---|
| Bharat Impact | 30% | 0:00 opening line + the working student who loses exam eligibility because of a train disruption and storms |
| Working AWS Build | 25% | Everything is the live link; the run is real Bedrock output; closing line names EC2, Bedrock (Sydney), CloudFront, CloudWatch |
| Innovation | 25% | The evidence chain (hero): every step a recorded event with an ID, labelled fact / calculation / AI interpretation. "Not a chatbot listing downsides." |
| Demo & Storytelling | 20% | One person's story (the working student) carried from map → finding → evidence → what-if |

## Before going on stage (do once, the day before)
1. **Record the what-if on the live server. It doesn't exist yet.** L-960f5653 (the what-if in the docs) was a laptop run: `/api/runs/demo/compare/L-960f5653` answers "run not found" on the live server. Open `#/run/demo/analysis/whatif` on the live link and run both:
   - **Checkpoint week 6 → 8** (recommended for the story: the finding is that the early check left no time to file an exception, so moving the check is the obvious fix to test);
   - **Office capacity per week 5 → 1** (the backup; the docs' earlier story).
   Each takes 30–60 s and uses 1 of the day's 10 runs. Write both run IDs here, and keep the one whose comparison reads more clearly (an outcome flip for the working student is the best case; the AI people choose afresh, so it isn't guaranteed).
   - What-if A (checkpoint 6 → 8): `L-________` **to record**
   - What-if B (capacity 5 → 1): `L-________` **to record**
2. **Bookmark these on the demo laptop** (the "What-ifs from this run" list is stored per browser, so a different laptop won't show it):
   - `#/` · `#/run/demo` · `#/run/demo/analysis` · `#/run/demo/analysis/evidence/demo-F1` · `#/run/demo/analysis/compare/<what-if ID>` · `#/blueprint/B-da347452`
3. Open each bookmark once and check it loads. Browser at 100% zoom, laptop width, no other tabs.
4. Recording a run is not a deploy, so this is allowed during the 30 Nov–5 Dec freeze, but keep it to these two runs.

## Main path: 2 min 40 s, no waiting, no live AI calls
The demo run is a real recorded run (DeepSeek V3.2 on Bedrock, 28 AI decisions, 170 events), restored on every deploy.

### 1. Home (0:00–0:20)
- **Say:** "At Indian colleges, rules like 80% attendance for exam eligibility go live untested. A commuter, a working student and a student with family duties live with the same rule very differently, and staff carry the load. RuleStorm lets the policymaker see that before rollout."
- **Point at:** the honest line under the title ("It explores possible responses in a simulation; it does not predict what a real college will do.").
- **Click:** **Open the demo run**.

### 2. Simulation map, `#/run/demo` (0:20–0:55)
- **Click:** speed **4×**, then **Play**. Let the map run while you talk.
- **Say:** "Eight people live through a 10-week term. Four students are AI people with their own goals and constraints; the attendance office and the exam officer are run by rules. Every decision is the AI's; every record and calculation is the rule engine's."
- **Point at:** the time ruler: the disruption marks in **week 5** (train line, 45 min delay) and **week 6** (storms), and the **check at week 6**.
- **Click:** the **working** student on the map (or in People). The timeline filters to their events. Click their week-6 decision: they planned to skip the class, with their own stated reason.
- **Point at** the finished summary row: **28 AI decisions · 28 model calls · 4 refused actions · 0 errors**. "Refused" = the engine blocked actions the rules don't allow.
- **Click:** **See what went wrong**.

### 3. Analysis → Summary (0:55–1:10)
- **Point at:** the hero finding card (working student, week 6, **8 / 11 = 72.7%, needs 80%, not eligible**) and the misses-by-week chart next to it.
- **Say:** "Nobody wrote this finding. Rules found it in the records."
- **Click:** **Show the evidence**.

### 4. Evidence, `demo-F1` (1:10–1:50): the hero
- **Point at:** the three-label legend: **recorded fact** (blue) · **calculated** (black) · **AI interpretation** (orange).
- **Scroll the chain top to bottom** (15 events), naming four:
  1. `E-0035` week 5: train line disruption, recorded fact;
  2. `E-0048`: working student marked absent, because the delay was over their travel buffer;
  3. `E-0077` week 6: the working student decided to skip the class, in their own words (AI interpretation);
  4. `E-0111`: the check: **attendance 8 / 11 = 72.7% (needs ≥ 80) → not eligible**, with "recomputed from this run's records".
- **Say:** "This is the difference from asking a chatbot. Every step has an event ID, the state it changed, and the calculation. The early check in week 6 came before they could get an exception in."
- **Click:** **What if?**

### 5. What if? (1:50–2:05)
- **Point at:** the form: **condition = the week the check happens, 6**. Type **8**. Read the line under the title: "Same people, same disruptions, same policy. Only this one condition changes."
- **Say:** "This takes about 40 seconds of real Bedrock calls, so we ran it earlier." Do **not** press **Run the what-if** on stage.
- **Click:** the **Compare** tab, then the bookmarked what-if run (or type its ID and press **Compare**).

### 6. Compare and decide (2:05–2:40)
- **Point at, in order:**
  - the banner: **within-model evidence, not real-world causality**;
  - **What changed:** checkpoint week 6 → 8;
  - the **check results table**: the working student's row, ✕ → ✓ if it flipped (rows that flip are highlighted);
  - the **"Read this before deciding"** note: the AI people decide afresh each run, so not every difference is caused by the change.
- **Say:** "RuleStorm gives no score and no verdict. The policymaker decides." Point at the **You decide** panel.
- **Close (10 s):** "Live on AWS: one EC2 server and Amazon Bedrock in Sydney, served over CloudFront, with CloudWatch watching every run. A rule tested on synthetic students before it touches real ones."

## If time remains (in this order)
| # | What | Where / click | Time | Why it earns the time |
|---|---|---|---|---|
| 1 | **Facts vs AI assumptions** on the blueprint | `#/blueprint/B-da347452`: blue facts vs orange dashed assumptions, **Approved and frozen**, the disruptions on the time ruler, people cards ("Wants… / Limited by…"), the "Run by rules, not AI" row | 20–25 s | Covers journey step 2, the second half of the USP ("validated simulation"); no waiting |
| 2 | **It isn't hard-coded to attendance** | Home → **What it can model** (two templates), or **Test a new policy** → chip **Use the hostel curfew example** (fills the fields; don't build) | 10 s | Innovation: the engine is general, templates are data |
| 3 | **Plain words in, simulation out** (only if a judge asks, or in the video) | **Test a new policy** → **Build the simulation** | 15–30 s wait | Shows the Bedrock blueprint step live; costs 1 of 50 daily blueprint requests; risky on stage |
| 4 | **Stress test** | Blueprint → **Stress test** tab → **Propose harsher conditions** | ~20 s wait | The AI hunts for weak points; works only on an approved blueprint |
| 5 | **AWS proof** (video, or Q&A on a laptop) | CloudWatch console: namespace `RuleStorm` (LLMCalls, Tokens, RunDurationSeconds) | 10 s | Working AWS Build 25% |

**Don't show:** the strict / flexible / progressive policy comparison (slice 15). It works through the API only; the UI has no screen for it, and no comparison exists on the live server yet. Mention it in Q&A as built, not shown.

## Q&A backups (2 min)
- **"Is this real or scripted?"** Open `#/run/demo` → the timeline: every AI decision shows its stated reason; IDs are copyable. The run took 27 s and 28 model calls.
- **"Can it be wrong?"** Point at the honest line on Home and the within-model banner. The AI only proposes actions; the engine checks permissions and does every calculation.
- **"Why did the student fail?"** The evidence screen, read in one breath: disruption → absent → storm → chose to skip → 8 / 11 at week 6.
- **If a judge starts a run themselves and another is going:** "Another simulation is running right now" (one run at a time for everyone). That's expected, not a bug.

## Rough spots to know before you're on stage
- **The hero is a failure from the early check, not the exception backlog.** BRIEF's hero section describes the backlog chain; the demo run shows the working student filing no exception in time before an early week-6 check. Say it the second way.
- **Evidence wording:** "a delay of 45 on 'attend class'" has no unit (minutes), and a faculty decision reads "correct a recorded attendance mark" three times. Two faculty "corrections" change absent → absent. Read past them; don't hide them (IDEAS has a 15-minute fix in `evidence.py`, which is a core change: team decision).
- **Blueprint shown is the stress variant** ("Early checkpoint with many disruptions", B-da347452), not the plain example (B-ff06a1d1 is not on the live server). Call it "the harsher version the stress test proposed".
