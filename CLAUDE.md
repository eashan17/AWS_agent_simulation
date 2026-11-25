# RuleStorm

Read first: docs/RULES.md (deadline, demo format, required tech) · docs/BRIEF.md (what and why) · docs/ARCHITECTURE.md (how) · docs/SLICES.md (order, proofs, status)
Set up by /kickoff. All sharing happens through this repo: pull before you start, push when you finish.
If a file is missing, say which one and use a placeholder; never wait for it.

## Session start
Only one skill may run at session start: task-observer, if it is installed on this machine.
If it is installed, invoke it before the first tool call and run its Session Start Protocol; if its pinned workspace path does not exist on this machine, use `~/.claude/skill-observations/` and say so in one line.
If it is not installed, skip this and start the task. No other skill runs until the task calls for it.

## Stack (ask before changing)
Python 3.12 · FastAPI (API) · Pydantic · Amazon Bedrock via boto3 (ap-southeast-2 Sydney, in-Region models only; Region fixed by the account) · SQLite on the EC2 disk (one storage interface) · Pandas
UI framework: not chosen yet; decided in /build-plan. No Streamlit. No Vercel, no Supabase.
Hosting: one EC2 instance in the live AWS account, behind CloudFront (see docs/BRIEF.md, Technical decisions). Only EC2 and Bedrock may spend credits; anything else must stay inside an always-free allowance.
Terminal proofs: `python -m rulestorm.cli <command>` (the CLI calls the same core code the API and UI will use)

## Two phases
1. Build: every slice is core logic plus an API route, proved in the terminal (a CLI command or curl). Write no UI code in this phase.
2. UI: only when every slice is done and the Claude Design handoff is in the repo. Use /ui. The UI sits on top of the finished core and never changes it.

## Our skills (account-wide: claude.ai → Customize → Skills)
| Command | When |
|---|---|
| `/build-plan` | Once docs/BRIEF.md exists: writes ARCHITECTURE.md + SLICES.md |
| `/slice N` | Build and prove one slice in the terminal |
| `/ui` | After every slice is done and the design handoff is in the repo |
| `/ship 1`, `/ship 2`, `/ship 3` | Harden + freeze · demo autopilot · README + submission |
| `/demo-video 2:30` | B, after the freeze: the full demo video with brag at the demo's length, real app footage in every product scene |

Use these for hackathon work. Don't use the general engineering skills (engineer, planner, react-developer and others) here unless a teammate types one by name.
Skills are account skills: never edit their synced files. When one gets a step wrong, tell me what to change; the fix goes into its folder in the starter repo's `hackathon-skills/` on GitHub, and everyone pulls and re-uploads it.

## Scope
- Build only what docs/SLICES.md says. Nothing extra.
- New ideas go to docs/IDEAS.md, not into code.
- Ask before adding a feature, page, dependency or outside service.
- Keep the main flow working; revert anything that breaks it.

## Evidence
- Show real output (the command and what it printed) instead of describing it. "It works" without output is not a proof.
- A zero or empty result (no rows, no matches) is checked against something known to exist before it is reported as a finding.
- Same action fails twice: stop, give 3 likely reasons, try a different approach. Stuck 20 minutes: say so and suggest a cut.

## Talking to me
- Plain words. If a technical word is unavoidable, explain it in brackets.
- Report problems as four lines: What happened · Why it matters for the demo · Options (with time) · Your recommendation.
- Keep status updates to 3 lines.

## Safety
No AWS keys in code, .env or the repo. On EC2 the instance IAM role gives access; locally each teammate signs in with `aws login` to a named AWS profile (`AWS_PROFILE`, e.g. `rulestorm-dev`), which gives temporary credentials and no access keys. .env holds settings only. Never call Bedrock from the browser. Never deploy to the live account from 30 Nov to 5 Dec (Round 1 judging).

## Commands
Setup (once): `python -m venv .venv` then `.venv\Scripts\python -m pip install -e ".[dev]"` (Windows) or `.venv/bin/python -m pip install -e ".[dev]"`
dev: `python -m uvicorn rulestorm.api:app --reload --port 8000`
test: `python -m pytest`
cli: `python -m rulestorm.cli <command>`
reset-demo: `python -m rulestorm.cli reset-demo` (restores the seeded real run as run `demo`; no Bedrock)
demo: (added by /ship 2)
deploy: in a Session Manager shell on the instance, `sudo git -C /opt/rulestorm/src fetch --tags && sudo git -C /opt/rulestorm/src checkout <tag> && bash /opt/rulestorm/src/deploy/deploy.sh <tag>` (one-time console setup and first deploy: docs/DEPLOY.md)
