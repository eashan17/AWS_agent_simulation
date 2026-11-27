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
(Filled in after the runs: blueprint and repeat IDs, fill times, each report's key lines, the
searches, and pass or fail on each line. The same numbers go into docs/BRIEF.md.)
