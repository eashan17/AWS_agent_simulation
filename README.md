# RuleStorm
Lets a policymaker at an Indian educational institution see how a rule like *80% attendance for exam eligibility* plays out against students' real constraints and staff capacity, before rollout.

**Live:** https://d2emiyaz9dq4bi.cloudfront.net (try `/api/runs/demo/findings`, then `/api/findings/demo-F1/evidence`)

A plain-language policy becomes a validated simulation: a template plus values the policymaker approves, each labelled fact or AI assumption. AI stakeholders on Amazon Bedrock react to disruptions inside a deterministic rule engine, and every finding traces back to recorded events and calculations. A what-if rerun changes one condition and compares, labelled within-model evidence, not real-world causality.

- **Run locally:** `python -m venv .venv`, `.venv/Scripts/python -m pip install -e ".[dev]"`, `python -m rulestorm.cli reset-demo`, then `python -m uvicorn rulestorm.api:app --port 8000`. Commands that call Bedrock need `AWS_PROFILE` (see CLAUDE.md).
- **Tests:** `python -m pytest` (a scripted model, never Bedrock).
- **Docs:** docs/BRIEF.md (what and why), docs/ARCHITECTURE.md (how), docs/SLICES.md (what was built and proved), docs/USER_JOURNEY.md (screens), docs/DEPLOY.md (AWS setup).
- **AWS:** one EC2 instance and Amazon Bedrock spend credits; CloudFront, CloudWatch, SNS, Systems Manager, Budgets and IAM stay inside free allowances.
