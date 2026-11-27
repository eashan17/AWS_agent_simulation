# RuleStorm evaluation (slice M10)

Written and committed before any evaluation run. Nothing here changes after the first run; the
results go in the last section only.

## What is tested
Both example policies (attendance and hostel curfew), on the live link, on the model the app ships
with (`deepseek.v3.2`, ap-southeast-2), with real AI people. The question is integrity and burden:
does the simulation run cleanly, and does it show who carries each rule. Whether a failure appears
is not the question. **A run with no harm is a valid result.**

## What is fixed
- **Code:** the live tag `live-20261127a` (commit 9a0f07f), deployed 27 Nov (Run Command 903a8cc7).
  No code, prompt or template change between the first fill and the last search run. A fix of any
  kind restarts the protocol from step 1, with new fills.
- **Settings:** `/etc/rulestorm.env` as deployed (cutoff unset). Not edited during the protocol.
- **The report command** (`eval report`, slice M10) only reads stored records. It is deployed
  after the last protocol run ends, never while one is running.

## Steps
1. **Fresh fills.** For each template, save its pre-filled example policy (`POST /api/policies`
   with the template's example text) and fill it (`POST /api/blueprints`), timed with curl's
   `time_total`. Approve the blueprint as it came back, with no edits. A fill that comes back not
   valid is reported, and one new fill of the same policy is allowed; both are reported.
2. **Repeats.** `POST /api/blueprints/<each>/repeats` with `{"times":5}`: 5 runs per example.
3. **Report.** `eval report <repeat_id>` for each repeat, through Run Command with the server's
   settings loaded (command in docs/SLICES.md, M10).
4. **Searches.** One per example, reported with cause classes:
   - attendance: `{"max_runs":6}`, the same day as the repeats;
   - curfew: `{"max_runs":5}`, after the next daily reset (it doesn't fit the same day's calls).
     Runs are not deploys, so this may run on 30 Nov.

Budget (measured 27 Nov on M7d runs: about 38 calls an attendance run, 134 a curfew run): the 10
repeat runs (about 860 calls) and the attendance search (about 250) are 16 of the day's 25 runs and
about 1,110 of its 1,500 calls.

## What each report prints
- the **AI-mistake rate**: false claims (claims of a cause that didn't affect the person, and untrue
  corrections, both refused by the engine) per decision, and, apart from it, no-reply decisions (the
  model call failed or timed out);
- **unmet intentions**: plans for a later step that the person didn't carry out;
- **one ledger line per run**: per person, the lowest margin, misses excused / pending / unexcused,
  obligations missed and lost;
- **every harm** with its cause class (no_reply, ai_mistake, forced, process, trade_off, chosen) and
  its misses by cause;
- **calls per run** and each run's status;
- **15 sampled decisions** to read: drawn from the AI people's decisions across the repeat's runs
  with a fixed seed (the repeat ID), each with who, when, the action and the reason they gave;
- **pass or fail** on each pass line below.

## Pass lines (set beforehand)
Counted per example, over its 5 repeat runs, unless a line says every run.

| Line | Pass when |
|---|---|
| Integrity | false claims plus no-reply decisions are at most 10% of all decisions |
| Calls | every run, repeats and search runs, uses at most 150 model calls |
| Failed runs | no run ends `failed` or `degraded` (a call-cap hit is degraded) |
| Fill time | every fill (step 1) is under 40 s |

A miss on any line, for either example, is a **no-go for M11**: the 27 Nov checkpoint stays live,
with the cutoff unset and its current demo. The go/no-go is at 29 Nov 12:00 IST.

Not pass lines: whether any harm appears, how many people fail, or which cause class wins. These
are results, reported as they come.

## Results

### v1 (27 Nov, from 12:15 IST): no-go on curfew
Counts read from the live API, before `eval report` was deployed.
- **Fills:** attendance P-72f97b42 → B-c2db9ddc, valid, 24.76 s; curfew P-3d04d792 → B-b865620c,
  valid, 33.04 s. Both under 40 s.
- **Attendance repeat R-57070615:** 5 of 5 `completed`; 32, 24, 32, 32, 33 calls (L-4aa53453,
  L-79e47355, L-fb5d68e5, L-a897ba21, L-ec65235c); 0 false claims, 0 no-reply decisions.
- **Curfew repeat R-c756dee5:** 4 of 5 `degraded`: L-eaf1b1bb, L-8077066b, L-6bd9e671 and
  L-02919fc0 each hit the 150-call cap (151–160 decisions asked for); L-156cd3dc `completed`
  with 128 calls. 0 false claims, 0 no-reply decisions. **Miss on "Failed runs".**
  Why: this fill set the evening job shift on 3 nights a week for both the intern and the
  volunteer (24 clash nights each), against 2 nights each in the fill the budget was measured on
  (B-0cc342b2, about 134 calls a run). Every clash brings the person's decision, the guardian's
  consent and the warden's ruling. The AI people made no mistake; the cap was too low for the
  term the fill described.
- **Attendance search S-bcce1ecb:** `broken` in 3 of 6 runs. "Recurring family emergency and work
  clash" (B-8d25512a) failed exam eligibility for the resident, the working student and the
  family carer in L-df9aa884, and again in its rerun L-e4d8b7ed: every harm `trade_off`.
- **Curfew search:** not run (v1 stopped at the miss).

### v2 (27 Nov, written after v1 and before any v2 run)
Everything above stands, with these changes only:
- **Calls per run:** the cap (`MAX_LLM_CALLS_PER_RUN` in `/etc/rulestorm.env`) goes from 150 to
  **300**, and the "Calls" pass line becomes **at most 300 calls per run**. Set from v1's
  heaviest asked-for run (160 decisions) with room for a heavier fill; at about USD 0.28 per 150
  calls, a 300-call run costs about USD 0.56.
- **Daily limits for the protocol:** 50 runs and 5,000 model calls (`MAX_RUNS_PER_DAY`,
  `MAX_LLM_CALLS_PER_DAY`), so v2 can't stop on a daily limit. Worst case at the cap: 10 curfew
  runs × 300 + 11 attendance runs × 40, about 3,500 calls, about USD 6.50.
- **Order:** both searches run the same day, after the repeats (attendance `{"max_runs":6}`,
  curfew `{"max_runs":5}`).
- These are settings, not code: the code stays at `live-20261127a`. The service restarts once,
  before the first v2 fill, with no run going. After v2's last run the daily limits go back to
  25 runs and 1,500 calls; the per-run cap stays 300 (at 150, a judge's curfew run could end
  degraded the same way). M11 sets the final limits.
- New fills of both examples, as in step 1; v1's blueprints and runs are not reused.

### v2 results (27 Nov, afternoon IST): **GO** — every pass line met on both examples
Printed by `eval report <id>` on the live server through Run Command (tag `live-20261127c`; the
report reads stored records only and was deployed after the last v2 run). Settings for the runs:
300 calls a run, 50 runs and 5,000 calls a day; the daily limits went back to 25 and 1,500 after.

| Job | Runs | Calls | Decisions | False claims | No reply | Integrity | Calls | Failed runs | Fill | Result |
|---|---|---|---|---|---|---|---|---|---|---|
| Attendance repeat R-17d0d900 (B-0255b6af) | 5 of 5 completed | 23–28 (127) | 127 | 0 | 0 | 0.0% | 28 ≤ 300 | none | 16.09 s | **PASS** |
| Curfew repeat R-781e8d15 (B-dac2e01a) | 5 of 5 completed | 131–170 (811) | 811 | 0 | 0 | 0.0% | 170 ≤ 300 | none | 21.32 s | **PASS** |
| Attendance search S-bbeea730 | 3 of 6 used, `broken` | 30–100 (161) | 160 | 0 | 0 | 0.0% | 100 ≤ 300 | none | — | **PASS** |
| Curfew search S-993c9533 | 5 of 5 used, `broken` | 51–207 (780) | 780 | 0 | 0 | 0.0% | 207 ≤ 300 | none | — | **PASS** |

About 1,880 calls in all (about USD 3.50). Intentions: attendance 21 stated, 7 unmet; curfew 12
stated, 1 unmet. The 15 sampled decisions of each repeat were read: every reason cites the
person's own state or profile (a shift clash, the misses they have left, a delay over their
slack), and the deciders' reasons cite the requests in front of them.

**What the runs show (results, not pass lines):**
- **Attendance, as approved: no harm in 5 runs; the ledger is the headline.** The working student
  carries the rule: 3–4 unexcused absences in every run (the shift clashes, which the policy
  doesn't excuse), 1–2 misses to spare, a work shift missed in 4 of 5 runs. Everyone else has 3–4
  to spare.
- **Curfew, as approved: harm in 1 of 5 runs.** L-19f9acfc: the intern fails the late-return
  penalties (12 misses for clashes the policy doesn't excuse, `trade_off`) and the volunteer loses
  the evening job (`trade_off`). In the other 4 runs both file a late-entry request for every
  shift night and the guardian and warden approve them: the burden is a request a night.
- **Attendance search: broken.** "Early checkpoint amid cascading personal crises" (B-251ae299)
  failed the working student's exam eligibility in L-756b2a86 and again in its rerun L-f4036e8c,
  3 unexcused clash misses each, `trade_off`. The first scenario, "Mass transport failure hits all
  commuters for weeks" (L-1fe8c324), harmed 4 students but every harm was `forced` (the strikes
  alone), so it isn't counted as the rule breaking.
- **Curfew search: broken.** "Warden away during peak disruptions" (B-514e3869), in L-cfc402c9 and
  its rerun L-5719bddf: late-entry requests from 4 residents still waiting at the check
  (`process`), the intern failing the penalties, and in L-cfc402c9 both the intern and the
  volunteer losing their evening jobs (`trade_off`).
- **A label to check (outside M10, in docs/IDEAS.md):** L-cfc402c9-F6 and L-5719bddf-F6/F7 say
  `forced` while their misses by cause say `8 process`.

**v1 by the same command** (`--max-calls 150`, v1's line): attendance R-57070615 PASS (24–33
calls, 0 false claims, a `trade_off` harm for the working student in all 5 runs, a job lost in
L-79e47355); curfew R-c756dee5 FAIL on failed runs (L-eaf1b1bb, L-8077066b, L-6bd9e671,
L-02919fc0 degraded).
