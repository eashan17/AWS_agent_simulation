# Demo flow: one core replay, then the stress-test results

For the Round 2 live demo (3 min + 2 min Q&A) and as the shot list for the Round 1 video (under 3 min). Built from docs/USER_JOURNEY.md, docs/BRIEF.md, docs/SLICES.md (slices up to 21), docs/RULES.md and the UI in `web/src` (26 Nov). IDs marked **live ✓** were checked on the live server on 26 Nov. All scenarios #0–#7 are recorded (the last three on 26 Nov, 05:33–05:36 IST).

Link: https://d2emiyaz9dq4bi.cloudfront.net (every screen has a `#/...` address, so each one below can be bookmarked).

## The idea in one line
The replay is the hook; the stress-test results are the product. One recorded term shows *how* a rule hurts one student. Then several pre-run scenarios show *where, how often and for whom* the same rule breaks, and what each fix changes, so the policymaker can decide.

**What the audience should leave with (numbers from the live recordings):**
> "Your 80% attendance rule holds in a normal term. Two searches found no confirmed break, but it came close: with **three weeks of transport trouble, a short-staffed office and the check at week 7**, the commuter reached "not eligible" in one run (the rerun had 2 absences to spare). The people it hurts are the **working** and **resident** students, because **the eligibility check comes before they can get an exception in**. It isn't one unlucky run: the working student failed in **2 of 3** runs of the same conditions. In the what-if that moved the check to week 8, **nobody failed (working 72.7% → 92.3%)**. Under the strict, flexible and progressive versions nobody failed in their run; **flexible drew 7 requests (strict 2), 3 refused actions and 6 staff decisions (strict 4), while progressive had no refused actions at the same 4 staff decisions**. RuleStorm doesn't pick a winner. You decide."

## Part 1: the scenario set (record before the demo)
Everything new since 25 Nov (searches, policy comparisons, repeated runs) was recorded on a laptop only. On the live server `S-2d62ad10`, `S-187da29f`, `C-f379c698`, `C-108c10ba` and `R-b97baf8d` all answer 404. So each scenario below has to be run once on the live link. Every one is a real run, and none is hand-made.

Two blueprints on the live server, both built from the attendance example policy (80% per course, formally approved exceptions):
- **B-a49b586e**, live ✓: the policy as the AI first read it. Check at week 9, office handles 5 requests a week, a train delay in week 3 hitting the commuter and resident. Two runs exist (`L-a3af1d12`, `L-2237d170`), with **no findings: everyone eligible** (lowest: commuter 94.1%). This is "a normal term".
- **B-da347452**, live ✓: "Early checkpoint with many disruptions", a harsher version the stress test proposed. Check at week 6, train line in week 5 and storms in week 6 hitting all four students, office short-staffed in week 5. The demo run `demo` is one term of it.

| # | Question it answers for the policymaker | Where to start it | Runs | Recorded ID | What to read off it |
|---|---|---|---|---|---|
| 0 | What does one bad term look like, step by step? (**core replay**) | already there | 0 | `demo` live ✓, finding `demo-F1` | working: 8 / 11 = 72.7% at week 6, not eligible; 15-event evidence chain |
| 1 | Does the rule hold in a normal term? | already there | 0 | `L-a3af1d12` live ✓ | no findings; everyone ≥ 94% |
| 2 | **Under which conditions does it break, and who is hurt?** | `#/blueprint/B-a49b586e/search` → **Up to 6 runs** → **Search for breaking conditions** | ≤ 6 | `S-261e90f7` live ✓ (5 asked, 4 ran: the day's limit) | the breaking scenario and who reached "not eligible", confirmed by a rerun; or "held in 6 runs" plus the closest call ("working: 2 absences to spare") |
| 3 | Is the demo's failure luck, or how often does it happen? | `#/run/demo/analysis` → **Run it again** (starts 2 more runs of the same conditions, demo included) | 2 | `R-f9db0944` live ✓ | "working: not eligible in N of 3"; who else fails and how often |
| 4 | Does a later check fix it? | `#/run/demo/analysis/whatif` → the week the check happens **6 → 8** → **Run the what-if** | 1 | `L-01465ef0` live ✓ | the working student's row in Compare: ✕ → ✓? |
| 5 | What if the office has fewer staff? | same form → office capacity per week **5 → 1** | 1 | `L-df9ce433` live ✓ (Q&A only, see below) | longest queue and wait; does anyone fail because a request is still waiting? |
| 6 | Would a stricter or more flexible version of the rule be better? | `#/blueprint/B-da347452/compare` → **Compare policies** | 3 | `C-61168412` live ✓ | per version: who failed the check, requests filed, refused actions, staff decisions |
| 7 | Backup if #2 holds: does the harsher setting break under search? | `#/blueprint/B-da347452/search` → **Up to 3 runs** | ≤ 3 | `S-b4501248` live ✓ | on the laptop this broke in round 1 (working not eligible at week 3); live it broke once, not repeated |

### Recorded on the live server, 26 Nov (IST; still 25 Nov in UTC)
- **#4 what-if, check week 6 → 8: `L-01465ef0`.** Compare `#/run/demo/analysis/compare/L-01465ef0`: matched (one environment value). working 72.7% ✕ → **92.3% ✓**; resident 80.0 → 100, family 88.9 → 100, commuter 100 → 100. Failed: [working] → **none**.
- **#3 repeat: `R-f9db0944`** (`demo` + L-8b9a84e2 + L-909293d2). **working not eligible in 2 of 3** (72.7, 72.7, 80.0); resident 1 of 3 (80.0, 80.0, 72.7); commuter 0 of 3 (100 each); family 0 of 3 (88.9, 87.5, 80.0); check_failed in all 3 runs; requests filed 4 · 4 · 4, refused 4 · 3 · 0, staff decisions 6 · 8 · 7. (The laptop's earlier repeat R-b97baf8d gave working 1 of 3: say "2 of 3" from the live one.)
- **#2 search on B-a49b586e: `S-261e90f7`, held: "not broken in 4 runs"** (5 asked; the 5th hit the day's limit). Round 1: closest "resident: 2 absences to spare (week 9)"; round 2 pushed that and got closer: **"commuter: 1 absences to spare before 'not eligible' (week 7)"** ("Severe backlog and early cutoff", B-e6ff8845). The screen says "1 absences": read it as "one absence". So #7 (the backup search on B-da347452) is needed.

### Recorded on the live server, 26 Nov after the limit reset (05:33–05:35 IST)
- **#6 comparison: `C-61168412`** (strict `L-c703430b`, flexible `L-fbbcc2d4`, progressive `L-853147bf`, all completed). Kept in every version: 80%, per course. Strict: exceptions only for unforeseeable, documented cases; the office can't approve part of a request. Flexible: requests in advance, partial requests keep valid sessions, approve if filed before the absence. Progressive: early warning and support, partial requests keep valid sessions.
  - **Nobody failed a check in any version** (working 90.0 · 88.9 · 80.0; family 81.8 · 88.9 · 80.0; resident 81.8 · 88.9 · 100; commuter 100 each).
  - The trade-off is office work: requests filed **2 · 7 · 3**, refused actions **2 · 3 · 0**, longest queue 0 · 1 · 0, weeks over capacity 0 · 1 · 0, average wait 0 · 0.14 · 0, staff decisions **4 · 6 · 4**, staff messages 2 · 3 · 2.
  - Say it as it is: "under all three versions everyone passed in this run; flexible costs the office most, progressive refused nothing at the same staff work as strict". Don't claim a version "saved" the working student: even the strict version passed them (90.0), and the repeat shows they fail in 2 of 3 runs of the original rule.
- **#5 what-if, office capacity 5 → 1: `L-df9ce433`.** Compare `#/run/demo/analysis/compare/L-df9ce433`: matched (one environment value). The queue got worse as expected: longest queue 0 → 1, weeks over capacity 0 → 2, average wait 0 → 0.4 weeks, **1 request still waiting at the check** (0 before), exceptions filed 4 → 5. But **working flipped ✕ 72.7% → ✓ 90.9%**, and nobody failed. A smaller office can't help a student, so that flip is the AI people choosing differently, not the capacity. **Keep #5 out of the 3 minutes**; for Q&A, point only at the queue rows.

- **#7 search on B-da347452: `S-b4501248`, held: "not broken in 3 runs"** (3 asked, 3 ran; round 1 only). Targeted "Cascading Transport Delays & Low Office Capacity" (B-fce4a421: office 5 → 3 a week, check week 6 → 7, heavy traffic week 2, bus strike week 3, road closure week 4, office short-staffed weeks 5 and 6): **broke once, not repeated**: `L-056e8e68` commuter reached "not eligible" (week 7, finding `L-056e8e68-F1`); rerun `L-87e045bf` commuter 2 absences to spare. Targeted "Late Checkpoint with Early Session Cancellations" (check week 8, three cancelled sessions): `L-5ebf7db4` no finding, working 2 absences to spare. The random scenario didn't run (runs used up).
  - **For the demo, use this search at step 4 rather than S-261e90f7.** "Broke once, not repeated" is the proof that RuleStorm doesn't count a lucky failure, and it answers "Can the AI just make up a failure?" on screen.
  - Not re-run to get a break: the script's rule is to report what happened. A bigger search (6 or 9 runs) would be a new question, not a retry. If wanted, it needs a day's runs and should be started before 29 Nov.
- Runs used on the live server on 26 Nov (UTC): 7 of 10 (3 comparison, 1 what-if, 3 search).

### Recording schedule (the live server allows 10 runs a day, one at a time)
- **26 Nov (9 runs):** #4 (1 run, about 1 min) → #3 (2 runs, about 2 min) → #2 (up to 6 runs, several minutes). Start each only after the last has finished; a second start gets "Another simulation is running right now".
- **27 Nov (4–7 runs):** #6 (3 runs) → #5 (1 run) → #7 only if #2 held.
- Model cost is under USD 1 in total (about 30 calls a run). Recording runs isn't a deploy, so it's allowed during the 30 Nov–5 Dec freeze, but finish by 29 Nov so the IDs are in this file and in the video.
- **Write each ID into the table above as soon as it exists**, and fill in the blanks in "What the audience should leave with". If a scenario's result is weak (for example, the what-if changes nothing), keep it for Q&A and drop it from the 3 minutes. Never re-run until it gives the "right" answer; report what happened.

### Bookmarks for the demo laptop (one folder, in this order)
`#/` · `#/run/demo` · `#/run/demo/analysis/evidence/demo-F1` · `#/blueprint/B-da347452/search/S-b4501248` · `#/blueprint/B-da347452/repeat/R-f9db0944` · `#/run/demo/analysis/compare/L-01465ef0` · `#/blueprint/B-da347452/compare/C-61168412`. For Q&A: `#/blueprint/B-a49b586e/search/S-261e90f7` (the normal-term search) and `#/run/demo/analysis/compare/L-df9ce433` (capacity 5 → 1).
The "what-ifs from this run" list is kept per browser, so on a different laptop only the bookmarks work. Open each one once before going on stage.

## Part 2: the 3-minute click-through

### A. Core replay: one term, one person (0:00–1:05)
**1. Home (0:00–0:12)**
- **Say:** "At Indian colleges, a rule like 80% attendance for exam eligibility goes live untested. A commuter, a working student and a student with family duties live with it very differently. RuleStorm shows that before rollout."
- **Click:** **Open the demo run**.

**2. Map, `#/run/demo` (0:12–0:40)**
- **Click:** speed **8×**, then **Play**.
- **Say:** "Eight people live through a 10-week term. The students are AI people with their own goals and limits; the office and the exam officer run on rules. The AI decides; the rule engine records and calculates."
- **Point at:** the week-5 and week-6 disruption marks and the check at week 6 on the time ruler.
- **Click:** the **working** student on the map. The person panel opens: 3 absences (sessions 9, 11, 12), exception request R4 **filed in week 7, after the week-6 check**, and 72.7% not eligible. "They asked for an exception. One week too late."
- **Close** the panel (Esc). **Click:** **See what went wrong**.

**3. Evidence (0:40–1:05)**
- On Summary, **click:** **Show the evidence**.
- **Point at:** the three labels (recorded fact · calculated · AI interpretation), then scroll from `E-0035` (train line, week 5) to `E-0111`: **8 / 11 = 72.7% (needs ≥ 80) → not eligible**, recomputed from the run's records.
- **Say:** "Every step is a recorded event with an ID. That's one term. One run is a story, not an insight. Here is the stress test of this policy."

### B. Stress-test results: where, how often, what fixes it (1:05–2:40)
**4. Search for breaks, `#/blueprint/B-da347452/search/S-b4501248` (1:05–1:35)**
- **Say:** "This is the same 80% policy as the AI first read it. In a normal term everyone is eligible. So we let RuleStorm hunt: each round the AI aims at the weak point the last runs came closest to breaking, and random scenarios look where it wouldn't."
- **Point at:** round 1's cards (targeted / random, what changed, the closeness bars), round 2 naming the weak point it pushes, then the result: **"The policy breaks under …"** with who reached "not eligible", and the confirming rerun. A break counts only once a rerun repeats it.
- If the search held: point at "The policy held: not broken in N runs" and the closest call ("working: 2 absences to spare"). That is the insight: the working student is always the first to go. Then bookmark #7 if it was recorded.

**5. Repeat runs, `#/blueprint/B-da347452/repeat/R-f9db0944` (1:35–1:55)**
- **Say:** "Is the demo's failure just luck? Same conditions, three runs."
- **Point at:** the bar "How often each person failed the check": **working, N of 3**, and each run's figure. Then "The spread of each measure" (requests filed, queue, staff decisions).

**6. What-if, `#/run/demo/analysis/compare/L-01465ef0` (1:55–2:15)**
- **Say:** "The failure came from an early check. What if the college checks at week 8 instead? Same people, same disruptions, only that changes."
- **Point at:** the within-model banner, "What changed: week 6 → 8", and the working student's row (✕ → ✓ if it flipped, highlighted).

**7. Compare policies, `#/blueprint/B-da347452/compare/C-61168412` (2:15–2:40)**
- **Say:** "Or change the rule itself. RuleStorm writes a strict, a flexible and a progressive version, keeping what you stated (80%, per course), and runs each under the same conditions."
- **Point at:** "Kept the same in every version", the three version cards (what each changed), then the trade-off rows: **who failed a check** under each version, requests filed, refused actions and staff decisions. "Flexible helps students but costs the office more work" (read it off the real table).

### C. Insight and decision (2:40–3:00)
- On the comparison's **You decide** panel, say the insight line from the top of this file with the recorded numbers filled in (15 s).
- **Close (5 s):** "Live on AWS: one EC2 server and Amazon Bedrock in Sydney, behind CloudFront, with CloudWatch on every run."

**For the Round 1 video:** the same order. Put each Part B scene under a title card naming the question it answers (the "Question" column), and end on the insight line as a full-screen card. Parts A and B can be cut tighter than live because nothing has to load.

## If time remains, or for Q&A
| What | Where | Time | Why |
|---|---|---|---|
| Facts vs AI assumptions, and correcting one | `#/blueprint/B-a49b586e` (approved, so read-only): blue facts vs orange assumptions, frozen. Editing works only on an unapproved blueprint (**Test a new policy** → **Build the simulation** → **Edit** on an assumption) | 20 s read-only / 45 s live | The policymaker stays in control of what the simulation assumes |
| How people adapted | Analysis of `demo` → Summary → "How people adapted" (10 in the demo: first requests, strategy shifts in their own words) | 15 s | Agents change strategy, and it's measured from records |
| Run 1, the normal term | `#/run/L-a3af1d12/analysis` | 10 s | The "before" picture: no findings |
| A second policy type | Home → What it can model, or Setup → **Use the hostel curfew example** | 10 s | The engine isn't hard-coded to attendance |
| Live AI on stage | Blueprint → **Stress test** → **Propose harsher conditions** (~20 s) | 20 s | Only if a judge asks to see the AI working live |
| AWS proof | CloudWatch, namespace `RuleStorm` (LLMCalls, Tokens, RunDurationSeconds) | 10 s | Working AWS Build (25%) |

**Q&A answers:**
- **"Is this real?"** Every run, finding and event has an ID that opens on the live link. Click any AI decision and read the person's own reason.
- **"Can the AI just make up a failure?"** No: findings come from rules over the records, a break counts only when a rerun repeats it, and the search says "not broken" when it isn't.
- **"Does this predict my college?"** No: the within-model banner. It shows how the rule *can* break, so you know where to look before rollout.
- **If a judge starts a run while one is going:** "Another simulation is running right now" is expected; there's one run at a time for everyone.

## Rough spots to know before you're on stage
- **26 Nov, after the recordings: the people's prompt changed (tag `live-20261126b`).** The AI students had been told only "eligibility is checked in week 6", not that it runs once at the end of the week, is final and counts waiting requests as absences. Every person now gets the full rule, generated from the template. **All the IDs above (`demo`, R-f9db0944, L-01465ef0, L-df9ce433, C-61168412, S-b4501248, S-261e90f7) were recorded with the old prompt; re-record them before using them.** On the laptop (L-4d797840) the working student, now knowing the rule, tried to file in week 6, was refused whole on the "already recorded" rule, and still failed at 72.7%.
- **The demo failure happened in 1 of 3 runs on the laptop** (R-b97baf8d). Say "in this run", and let scenario #3 answer "how often" with the live numbers.
- **One what-if flip is not proof.** #5 (fewer staff) flipped the working student to eligible too, which the change can't have caused. So #4's week-8 flip is one run as well: say "in this what-if run, nobody failed", and let the repeat (2 of 3) carry "how often".
- **The hero is the early check, not the exception backlog** that BRIEF's hero section describes: the working student filed in week 7, after the week-6 check.
- **The two blueprints differ in more than difficulty.** The AI gave the students different travel buffers in each (working: 15 min in B-a49b586e, 30 min in B-da347452). Call B-da347452 "the harsher version the stress test proposed", not "the same blueprint with harder weather".
- **Evidence wording:** "a delay of 45" has no unit (minutes); "correct a recorded attendance mark" repeats three times; two faculty corrections change absent → absent. Read past them (fix is in IDEAS, a core change).
- **The daily limit:** recording takes most of a day's 10 runs. Don't record on the day of a live demo.
