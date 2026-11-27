# Demo flow: the policy, one term, then the stress-test results

For the Round 2 live demo (3 min + 2 min Q&A) and as the shot list for the Round 1 video (under 3 min). Rewritten 26 Nov for the engine on the live server now (tag `live-20261126c`, checked: the live comparison already shows "requests decided" and "requests rejected"). Built from docs/SLICES.md (both 26 Nov demo fixes), docs/USER_JOURNEY.md, docs/RULES.md and the UI in `web/src`.

Link: https://d2emiyaz9dq4bi.cloudfront.net (every screen has a `#/...` address, so each one below can be bookmarked).

**Nothing recorded before today's fixes can be used.** `demo`, `L-a3af1d12`, `S-261e90f7`, `S-b4501248`, `R-f9db0944`, `L-01465ef0`, `L-df9ce433` and `C-61168412` show behaviour the engine no longer allows: students weren't told the check is final, faculty marked absent students present, and a skip by choice could be excused. The two live blueprints `B-a49b586e` and `B-da347452` were filled before personal clashes existed (checked on live: neither has a work shift clash or a family emergency), so new blueprints are built first. Getting the old recordings off the live site is a tech task: see "Old recordings off the live site" below.

## The final demo (approved 27 Nov, after M10 and M11; supersedes Parts 1 and 2 below)
Checked against the idea doc (docs/ideation/RuleStorm_Consolidated_Product_and_MVP_Specification (2).md): its 7 core capabilities, the 8-step demo journey (§6), the central demonstration interaction and the five differentiators (§9). No AWS scene (team decision). **Record the video with `/brag:brag`** (team decision, 27 Nov), from the live link, under 3 minutes.

`demo` replays **L-4aa53453** (M10 v1 attendance repeat R-57070615, blueprint B-c2db9ddc): its hero `demo-F1` is the working student failing exam eligibility, `trade_off` (8 work-shift clashes the policy doesn't excuse). Old recordings are hidden (`RULESTORM_RETIRED_BEFORE=2026-11-27T06:46:46+00:00`).

| # | Time | Screen | What it shows (idea doc) | Status |
|---|---|---|---|---|
| 1 | 0:00–0:14 | Home | §12.7 India framing: an 80% rule against a long-distance commuter, a working student and a student with family duties; shown as a potential benefit, not a measured one. Two rule types | have |
| 2 | 0:14–0:32 | Policy input → `#/blueprint/B-c2db9ddc` | Journey 2–3, differentiator 1: plain-language policy, purpose and environment; interpretation and stakeholder profiles; stated vs assumed; validation status; editing before approval; "How RuleStorm reads this rule" (a regular shift is routine, so not exceptional) | have |
| 3 | 0:32–0:40 | **Run this term** → progress | Journey 4, simulation launch: week, run ID, progress (cut after a few seconds) | live, uses 1 run |
| 4 | 0:40–1:02 | `#/run/demo`, 8× | Journey 5, capabilities 1–2: disruptions, decisions, requests and responses; the working student's goals, constraints, memory, state ("misses left", the job limit) and plans; one strategy change ("How people adapted"); one refused action (the governed environment) | have |
| 5 | 1:02–1:20 | `#/run/demo/analysis/evidence/demo-F1` + Summary + run details | The central interaction, capability 5: event IDs, state changes, the calculation, labelled recorded / calculated / AI; "Why: trade-off"; who carried the rule; run details | have |
| 6 | 1:20–1:32 | `#/blueprint/B-c2db9ddc/repeat/R-57070615` | §G repeated runs: working failed 5 of 5; why each harm happened | have |
| 7 | 1:32–1:48 | `#/blueprint/B-c2db9ddc/search/S-bcce1ecb` | Capabilities 3–4, differentiators 3–4: targeted plus random scenarios; "Recurring family emergency and work clash" fails 3 students, confirmed by its rerun (L-df9aa884, L-e4d8b7ed) | have |
| 8 | 1:48–2:02 | What-if on L-4aa53453: `exceptional_causes` → `any_documented` | §4.9 controlled counterfactual on how the rule reads, labelled within-model | **to record** (1 run) |
| 9 | 2:02–2:18 | Compare policies on B-c2db9ddc | Capability 6, journey 7: strict / flexible / progressive under matched conditions; who fails against requests decided | **to record** (3 runs) |
| 10 | 2:18–2:44 | Curfew: evidence in L-cfc402c9 (search S-993c9533, "Warden away during peak disruptions"), then a what-if on `warden_capacity_per_night` ×2 | The idea doc's central chain (disruption → request → over capacity → still pending at the check) on a second rule; the bottleneck detector (`pending_at_check`, `process`); jobs lost (`trade_off`); the doc's own counterfactual (more processing capacity) | evidence have; what-if **to record** (1 curfew run) |
| 11 | 2:44–2:58 | "You decide" panel | Journey 8, capability 7: trade-offs, no single score. One line from M10: about 2,000 AI decisions checked, 0 false claims (docs/EVALUATION.md) | have |

**To record (5 runs, about 310 calls, about USD 0.60):** scenes 8, 9 and 10's what-if, after the 05:30 IST daily reset (10 runs and 1,500 calls a day on live) or on 30 Nov (runs aren't deploys). Write each new ID into this table. If a what-if changes nothing, say so on screen.

**Before recording, check on screen:** L-cfc402c9's evidence reads as the central chain; scene 4 has a refused action to point at.

**Not built, so not claimed:** a behavioural-pattern detector with novelty comparison (§4.8; "How people adapted" finds strategy changes and first-time actions from the records, not a comparison with earlier runs), four-stage validation (§4.6; we have schema and template checks), a full run manifest (§4.9).

**Q&A, not in the video:** the no-harm ledger `L-0a075c5e` (M10 v2 attendance: the working student carries the rule with nobody failing); proposing harsher conditions; a harm a search doesn't count because outside disruptions alone caused it (`L-1fe8c324`, `forced`); a fresh run live; the EVALUATION.md protocol.

## The idea in one line
A policymaker writes a rule in plain words; RuleStorm turns it into a simulated term with AI people, shows *how* the rule hurts one person, then *how often, under which conditions and for whom* it breaks, and what each fix changes, so the policymaker can decide before rollout.

**What the audience should leave with**, filled in only from the new recordings:
> "Your 80% rule holds in a normal term **[#1: lowest person and %]**. But **[#2: who, N of 5 runs]** fail it, because **[from the hero's evidence, in the evidence's own terms]**. It breaks when **[#7 or #6: the breaking conditions, confirmed by a rerun]**. **[#3: does checking later change it, said as one run]**. **[#4: does more staff change it]**. The strict, flexible and progressive versions **[#5: who fails under each, requests decided and rejected]**. RuleStorm doesn't pick a winner. You decide."

**What changed for the story (live since this morning).** Watch for these when picking the hero, and say them correctly on stage:
- The policy says only "Exceptional circumstances may be considered through formally approved exceptions." The engine reads "exceptional" as **not routine**: a transport delay longer than the student's travel buffer, or a family emergency, can be excused; a skip by choice, a delay within the buffer, or a **regular work shift** can't. That reading comes from our template, not from the policy text, and the blueprint doesn't show it as an assumption (docs/IDEAS.md). Say it as "as we read the rule".
- The blueprint now places personal clashes by profile: a work shift on the working student, an emergency on the family student (on the laptop, B-064adbd0).
- Every student knows the rule: the check runs once at the end of its week, is final, and a request still waiting counts as an absence. A request can't include the session in progress.
- Faculty can't fake or empty-correct marks. A buffer change applies from the next session. Advice arrives in the same session.
- Policy comparison rows: "requests decided" (the office's workload) and "requests rejected" replace "staff decisions".

## Part 1: the runs to record

### Limits and budget
- Live until 29 Nov: **25 runs and 1,500 AI calls a day**, 50 blueprint calls a day (back to 10 runs and 1,000 calls on 29 Nov, before judging). One run at a time for everyone; a second start gets "Another simulation is running right now". The day resets at 05:30 IST (midnight UTC).
- The full set is **at most 23 runs and about 4–6 blueprint calls**. At about USD 0.07 a run, that's under USD 2.
- Recording runs isn't a deploy, but finish by **28 Nov** so there's a day for the bookmarks, the video and the cleanup deploy (below).

### Two blueprints first (no runs)
| Step | What | Where | Cost | Check before approving |
|---|---|---|---|---|
| B1 | **The normal term** (call it **B-N**) | Home → **Test a new policy** → **Use the attendance example** → **Build the simulation** → **Approve** | 1 blueprint call | The people include the work shift clash on the working student and the family emergency on the family student. If not, build again rather than editing (an edit makes it the policymaker's fact, not the AI's fill). This blueprint is also scene 2 on stage |
| B2 | **The harsher version** (call it **B-H**) | B-N → **Stress test** → **Propose harsher conditions** → **Approve** one variant | 1 blueprint call | Pick a variant with an **early check (week 6 or earlier)** and a disruption in the check week or the week before. Write its title down: say "the harsher version the stress test proposed", never "the policy" |

### The scenario runs
| # | Question it answers for the policymaker | Where to start it | Runs | Recorded ID | What to write down |
|---|---|---|---|---|---|
| 1 | Does the rule hold in a normal term? | B-N → **Run this term** | 1 | **L-cb3d7872** live ✓: no findings, everyone eligible, lowest working 94.7% (the shift clash, 1 absence); 13 AI calls, 0 errors | findings (expected: none); the lowest person and their %; **the AI error count** in the run summary |
| 2 | How often does the harsher term hurt someone, and whom? | B-H → **Repeat runs** tab → **5 runs** | 5 | **R-9bcb3466** live ✓ (L-f26102ea, L-6531e3f3, L-483c2985, L-468e8131, L-0d7c6458): **nobody failed in 5 of 5**; lowest family 81.2% (once), working 93.8% in 4 of 5 (the shift), 0 AI errors | "How often each person failed the check": each person N of 5; requests filed, decided, rejected |
| 0 | What does one bad term look like, step by step? (**the core replay**) | no new run: chosen from #2's 5 runs after they finish (below) | 0 | L-___, finding ___-F1 | the hero's absences and their causes, their request(s) and what happened to each, their % at the check |
| 3 | Does checking later change it? | hero run → **What if?** → the week the check happens **+2** (for example 6 → 8) → **Run the what-if** | 1 | L-___ | the hero's row in Compare (✕ → ✓?), who else changed |
| 4 | Would more staff change it? | hero run → **What if?** → office capacity per week **×2** (for example 5 → 10) | 1 | L-___ | the hero's row; if it doesn't flip, why (the request was rejected on the rule, or was never filed) |
| 5 | Would a stricter or more flexible rule be better? | B-H → **Compare policies** → **Compare policies** | 3 | C-___ | per version: who failed a check, requests filed, decided, rejected |
| 6 | Under which conditions does the policy as written break? | B-N → **Search for breaks** → **Up to 6** → **Search for breaking conditions** | ≤ 6 | S-___ | broke (conditions, who, confirmed by a rerun) or "held in N runs" plus the closest call |
| 7 | Does the harsher version break under search, and is it repeatable? | B-H → **Search for breaks** → **Up to 6** | ≤ 6 | **S-600878c4** live ✓: **broken in 5 runs**. Round 1 held (3 scenarios); round 2 pushed the closest call and "Extended Transport Disruption on Commuter" (B-913f7c80: road closure weeks 1–4 hitting the commuter, delay 30 min over a 15-min buffer, office 1 a week and closed in week 5, check week 8) broke twice: L-028efe0c commuter 62.5% (5 / 8), rerun L-304d4e11 37.5% (6 / 16). **Not yet usable as the replay: see "Live recording, 26 Nov" below** | same; this is the one shown on stage unless #6 broke and #7 didn't |

**Total: at most 23 runs** (1 + 5 + 1 + 1 + 3 + 6 + 6), plus the 2 blueprint calls and 1 call per search round.

**Picking the hero (scenario 0): run first, then decide.** We don't know in advance which failures the 5 runs will show, so nothing here fixes the hero's story. After #2 finishes:
- List every finding in the 5 runs, and for each one read the evidence: what caused each absence, what happened to each request, the % at the check.
- Pick the one a policymaker would find most useful to see: the clearest chain from the term's events to the result, where every step reads correctly. Don't decide what the failure "should" be; describe it in the evidence's own words.
- If none of the 5 runs has a finding, there's no hero on B-H: say so in the team chat before recording #3–#5, and replay the run with the closest call instead ("working: 1 absence to spare").
- Whatever is picked, the stage line is "this is one of 5 runs; [person] failed in N of 5".

### Live recording, 26 Nov (10:34–10:43 IST)
- **B-N = `B-11134255`** (policy P-a0e5f5a7, the attendance example), approved: check week 10, office 5 a week; rail outage week 3 (commuter, resident), work shift clash week 5 (working, routine), family emergency week 7 (family), office short-staffed week 8, a cancelled session week 9.
- **B-H = `B-95214fb0`, "Early checkpoint with backlog"**, approved. None of the 3 proposals had a check at week 6 or earlier, so this one was taken: check week 8, office 1 a week and closed in week 5, family emergency week 2, transport week 3 (commuter, resident, 30 min), shift clash week 4.
- **No hero yet.** #2 failed nobody in 5 runs. #7's break is real in the records, but both breaking runs rest on AI behaviour, not the rule: from week 5 the commuter kept skipping "because the road closure continues" after it ended in week 4 (sessions 9–11 recorded as "their own choice: not a valid reason"), and in the rerun the commuter planned to file "next session" for 8 sessions and never filed. A judge opening the person panel would see the AI misreading its own situation. Team decision pending: use L-028efe0c and say so, or first tell each person when nothing is in their way that session (a prompt fix, docs/IDEAS.md) and search again. #3–#5, the export and the cleanup deploy wait for the hero. Runs used on 26 Nov (UTC): 18 of 25.

### Order to record
- **Day 1 (26 or 27 Nov), 11 runs:** B1 → B2 → #1 → **stop and check #1's AI error count**: if any calls failed, look at docs/SLICES.md's timeout notes before going on → #2 → pick the hero → #3 → #4 → #5.
- **Day 2 (the next day), up to 12 runs:** #6 → #7. If either search used all its runs, it's done: never re-run to get a break.
- **By 28 Nov:** write every ID into the table above, fill in "What the audience should leave with", set the bookmarks, hand the hero's ID to the cleanup (below).
- If a scenario's result is weak (the what-if changes nothing, the comparison has no failures), it still answers its question. Keep it for Q&A if it doesn't fit the 3 minutes. Report what happened; never re-run for the "right" answer.

### Old recordings off the live site (tech task, one deploy before 29 Nov)
- **What happened:** the live store still holds every run, blueprint, search, repeat and comparison made on the old engines. The UI has no list of runs, so a judge reaches them only through Home's **Open the demo run** (`demo`, restored on every deploy from `rulestorm/fixtures/demo_run.json`, recorded in slice 10), the links from `demo` (its blueprint's stress test), and the IDs written in our docs.
- **Why it matters:** Round 1 judges click **Open the demo run** first, and the old recordings show behaviour the engine no longer allows.
- **The fix: hide, don't delete (team choice, 26 Nov).** Built and tested on the laptop, not deployed yet: the setting `RULESTORM_RETIRED_BEFORE` (an ISO time) makes everything stored before it read as not found: blueprints, runs, findings and their evidence, comparisons, repeats and searches. Nothing is deleted; removing the setting brings it all back. The old example ID `L-960f5653` is gone from Home and Compare.
- **Still to do, after recording, in one deploy with the limits back to 10 runs:**
  1. On the server, `python -m rulestorm.cli run export <hero L-id> --out /tmp/demo_run.json --hero <finding>`; bring it to the laptop through Session Manager (compressed, checksum on both ends), commit it as `rulestorm/fixtures/demo_run.json` (tests/test_fixture.py checks it; update its expected hero title).
  2. Back up `/var/lib/rulestorm/rulestorm.db`, then add `RULESTORM_RETIRED_BEFORE=<B-N's created_at>` to `/etc/rulestorm.env` and set the limits back to 10 runs and 1,000 calls.
  3. Deploy (it restores the new `demo`). Check: `demo` and `demo-F1` open; the 8 old IDs above, the old demo's blueprint and `L-960f5653` are not found; every new recording and bookmark opens.
  4. The README and submission cite only new IDs.
- After it, `demo` is the hero and its finding is `demo-F1`. The what-ifs #3 and #4 were started from the hero's own run, so they stay under the hero's L-ID.

### Bookmarks for the demo laptop (one folder, in this order; fill in after recording)
`#/` · `#/blueprint/B-N` · `#/run/demo` · `#/run/demo/analysis/evidence/demo-F1` · `#/blueprint/B-H/repeat/R-___` (#2) · `#/blueprint/B-H/search/S-___` (#7) · `#/run/<hero L-id>/analysis/compare/L-___` (#3) · `#/blueprint/B-H/compare/C-___` (#5). For Q&A: `#/run/L-___/analysis` (#1), `#/blueprint/B-N/search/S-___` (#6), `#/run/<hero L-id>/analysis/compare/L-___` (#4).
The "what-ifs from this run" list is kept per browser, so on a different laptop only the bookmarks work. Open each bookmark once before going on stage.

## Part 2: the 3-minute click-through
One sentence to say and one thing to point at per scene. The prep notes after the script cover what to say if a result came out differently. Between scenes, say the jump out loud ("here's the stress test we ran earlier"), so the bookmarks don't look like hidden setup.

### A. The problem and the policy (0:00–0:38)
**1. Home (0:00–0:18)**
- **Say:** "Colleges roll out rules untested on the people who live with them. An 80% attendance rule can bar a commuter from exams over trains they couldn't control; a 10 pm hostel curfew can push a student whose lab runs late toward disciplinary action. RuleStorm lets the policymaker test a rule before it goes live."
- **Point at:** **What it can model**: attendance and hostel curfew, two different rule types on one engine.

**2. Policy → simulation (0:18–0:38)**
- **Click:** **Test a new policy** (the 80% example is filled in). Then the bookmark `#/blueprint/B-N`: "the blueprint the AI built from that text".
- **Say:** "The policymaker writes the rule in plain words. The AI turns it into a simulation, and keeps what you stated apart from what it assumed."
- **Point at:** blue facts against orange assumptions, and the clashes the AI gave each person from their profile (the working student's shift, the family student's emergency).

### B. One term, one person (0:38–1:18)
**3. Map, `#/run/demo` (0:38–1:00)**
- **Click:** speed **8×**, then **Play**. Then the hero on the map.
- **Say:** "Eight people live through a 10-week term: AI students, faculty and an advisor with their own goals, and an office and exam officer that follow the college's rules." Then one line from the hero's panel, in the evidence's own words.
- **Point at:** the hero's panel: each absence with its cause, and what happened to their request.
- **Close** the panel (Esc). **Click:** **See what went wrong**.

**4. Evidence (1:00–1:18)**
- **Click:** **Show the evidence**.
- **Say:** "Every step is a recorded event, and the result is calculated from the records, not written by the AI."
- **Point at:** the calculation at the check: **___ / ___ = ___% (needs ≥ 80) → not eligible**, with each absence's cause and whether it counts as a valid reason.

### C. The stress test: how often, where, what changes it (1:18–2:30)
**5. Repeat runs, #2 `R-___` (1:18–1:36)**
- **Say:** "One run is a story, not an insight. Is it luck? Same conditions, five runs."
- **Point at:** "How often each person failed the check": **hero, N of 5**.

**6. Search for breaks, #7 `S-___` (1:36–1:54)**
- **Say:** "Then RuleStorm hunts for the conditions that break the rule, aiming each round at where the last runs came closest."
- **Point at:** the result line, and its confirming rerun.

**7. What-if, #3 `L-___` (1:54–2:10)**
- **Say:** "When you check is a lever you control. Same people, same disruptions, the check two weeks later."
- **Point at:** "What changed: week ___ → ___" and the hero's row, "in this what-if run".

**8. Compare policies, #5 `C-___` (2:10–2:30)**
- **Say:** "Or change the rule itself: a strict, a flexible and a progressive version, under the same conditions."
- **Point at:** the **who failed a check** row against the **requests decided** row (the office's workload).

### D. The decision (2:30–3:00)
- On the comparison's **You decide** panel, say the filled-in insight line from the top of this file.
- **Close:** "Before a single real student is affected, the policymaker sees who a rule hurts, how often, and what each option costs. RuleStorm doesn't decide. You do."

### Prep notes per scene (read before going on stage, not said as written)
- **Scene 3:** the hero's line comes from their evidence only. If the cause is a regular shift, say "a regular shift isn't an exceptional circumstance, as we read the rule". If the cause was a valid reason the office couldn't decide in time, say that.
- **Scene 6:** if it broke and the rerun repeated it: "The policy breaks under …", and who reached "not eligible". If it broke once and the rerun didn't: "One run broke, the rerun didn't, so RuleStorm doesn't count it. A lucky failure isn't a finding." If it held: "Not broken in N runs", and the closest call.
- **Scene 7:** the early check is the stress test's own harsher assumption, so moving it back isn't "a fix". Present it as the timing choice the policymaker owns. If it changed nothing, say so: "even a later check didn't help them". If #4 (more staff) changed nothing either and the request was rejected on the rule, add: "more office staff didn't help: the rule refused the request, not the queue".
- **Scene 8:** read the trade-off off the real table only; don't say "costs the office more work" unless the "requests decided" row shows it.

**For the Round 1 video:** the same order. Put each Part C scene under a title card naming the question it answers (the "Question" column), and end on the insight line as a full-screen card. Scenes can be cut tighter than live because nothing has to load.

## If time remains, or for Q&A
| What | Where | Time | Why |
|---|---|---|---|
| Edit an assumption | Editing works only on an unapproved blueprint (**Test a new policy** → **Build the simulation** → **Edit**) | 45 s live | The policymaker stays in control of what the simulation assumes |
| How people adapted | `demo` → Summary → "How people adapted" | 15 s | Agents change strategy, measured from records |
| The normal term | #1 `#/run/L-___/analysis` | 10 s | The "before" picture |
| The policy as written under search | #6 `S-___` | 15 s | Where the unmodified rule comes closest to breaking |
| More staff | #4 compare | 10 s | Separates a rule problem from a capacity problem |
| A second policy type | Setup → **Use the hostel curfew example** | 10 s | The engine isn't hard-coded to attendance |
| Live AI on stage | Blueprint → **Stress test** → **Propose harsher conditions** (~20 s) | 20 s | Only if a judge asks to see the AI working live |
| AWS | One EC2 server and Amazon Bedrock in Sydney, behind CloudFront; CloudWatch namespace `RuleStorm` (LLMCalls, Tokens, RunDurationSeconds) | 10 s | Working AWS Build (25%), if a judge asks |

**Q&A answers:**
- **"Is this real?"** Every run, finding and event has an ID that opens on the live link. Click any AI decision and read the person's own reason.
- **"Can the AI just make up a failure?"** No. Findings come from rules over the records, an absence is excused only for a non-routine cause, a break counts only when a rerun repeats it, and the search says "not broken" when it isn't.
- **"Why wasn't a regular shift excused?"** The policy says "exceptional circumstances". Our template reads a regular shift as not exceptional, and an unforeseen disruption as exceptional. That reading is ours, not the policy's words; the comparison shows what a more flexible reading would change.
- **"Does this predict my college?"** No: see the within-model banner. It shows how the rule *can* break, so you know where to look before rollout.
- **If a judge starts a run while one is going:** "Another simulation is running right now" is expected; there's one run at a time for everyone.

## Rough spots to know before you're on stage
- **Selection:** the replay is one of #2's five runs, picked for clarity. Always say "N of 5" with it; never present it as the typical term unless N says so.
- **One what-if flip is not proof.** A what-if is one run, and the AI people can choose differently in it. Say "in this what-if run"; let the repeat carry "how often". A flip that the change can't explain (more staff flipping a rule rejection) is Q&A material, not stage material.
- **The check week:** the policy only says "checked at a set point in the term". An early check in B-H is the stress test's harsher assumption, listed under assumptions, not the policy as written.
- **A request filed in the same session as the absence is refused ("not recorded yet")**, and the person files again next session (docs/IDEAS.md). It shows in the person panel: read it as "too early", not as a rejection.
- **A garbled last character** ("…secure it.�") can end a person's reply in the panel (docs/IDEAS.md). Read past it.
- **AI timeouts:** the laptop's calls stalled on 26 Nov; the live server had none. A degraded run (failed AI calls) is marked in its summary: don't use one as the hero.
- **The daily limit:** recording takes most of a day's runs. Don't record on the day of a live demo, and after 29 Nov there are only 10 runs a day.
