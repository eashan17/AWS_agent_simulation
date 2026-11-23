# Rules: Techfest 2026-27 Campus to Cloud Hackathon sponsored by AWS

Source: `Idea+PS/Aws_Problem_Statement.pdf` (pages 1–6). Only what the document says; `[MISSING]` where it is silent.

| Item | What the rules say |
|---|---|
| Problem statement / theme | "How effectively can you identify a real, everyday problem faced by people, and build and deploy a working solution on AWS that makes their lives measurably better?" Build for the India you live in every day (examples given: local trains, university campuses, government portals, scholarship schemes, municipal water). The goal is to reward real-world impact, working builds and clear storytelling, not slide decks. Must solve a real problem for Indian users. |
| Judging criteria (with weights) | Same for Round 1 and Round 2. **Bharat Impact 30%**: how real is the problem, and how well does the solution serve Indian users? **Working AWS Build 25%**: is it live on AWS, does it work, are the AWS services used well? **Innovation 25%**: how fresh is the idea or the approach? **Demo & Storytelling 20%**: how clearly does the team show who it helps and how? |
| Demo format and time limit | **Round 1 (online):** demo video, **under 3 minutes**, explaining the problem, who it helps, how the solution works, the impact, and why the majority of people should care. **Round 2 (Finals, Demo Day at IIT Bombay, top 35 teams):** **3-minute live demo + 2-minute Q&A** before AWS and Techfest judges. Focus: how it works, impact on real users, key decisions made during development. Judges may ask about the problem, the solution, the technical implementation and real-world impact. |
| What we must submit | (1) **Live prototype**: a working URL deployed on AWS that stays accessible through Demo Day. (2) **Idea Brief**: the problem, who it's for, how the solution works, its impact. (3) **Build Summary**: the AWS services used and why / the development process. (4) **Code repository**: public repository encouraged. (5) **Demo video** under 3 minutes. All five go in **one Google Drive folder** (documents, prototype URL, repo link, video); the Drive folder link is pasted in the **'Submission Link'** field on techfest.org. Step 4 also says to paste our **Builder Center alias, our idea and our live project URL** in the submission link. Form field limits: `[MISSING]`. |
| Deadline | Registration: **30 Nov 2026, 11:59 PM IST**. Round 1 submission: **30 Nov 2026, 11:59 PM IST**. Student verification on AWS Builder Center recommended **by 27 Nov 2026**. Round 1 results: by 5 Dec 2026. Demo Day (offline, IIT Bombay): **17 Dec 2026**. Prize money form (winners): by 31 Dec 2026. |
| Required, allowed or banned tools and APIs | Required: build and deploy on the **AWS Free Tier**; prototype must be deployed on AWS. Every participant needs a free **AWS Builder Center** account with verified student status (via SheerID). AWS account may use the same Builder ID. Banned tools/APIs: none stated. Non-AWS services: `[MISSING]` (not addressed). |
| Sponsor prizes | Prize money for the **Top 3 teams** via NEFT, latest by May 2027 (amounts `[MISSING]`). Certificates of Excellence to the top 3; Finalist Certificates to all Demo Day participants. Student-verification rewards (not competition prizes): AWS Skill Builder premium 1 year, up to $30 AWS credits, a foundational AWS certification voucher. No separate sponsor-track prizes stated. |
| Team rules | Individuals or teams of **up to 4**. Students enrolled in any institution in India, **aged 18+**. Register at techfest.org to receive a Team ID. Submissions must be the team's original work; solutions must be original and not protected by patents, copyrights or publications. Finalists must be available to present and defend at IIT Bombay. Pre-existing code: `[MISSING]` (not addressed beyond "original work"). |

## AWS Free Tier terms that bind us (from AWS, not the PS; checked 24 Nov 2026)
The PS says "build using AWS Free Tier". AWS's own terms then apply:
- Free plan ends after 6 months **or when credits run out**, and the account is **suspended**. Running out of credits before 17 Dec would take the live URL down. ([terms](https://aws.amazon.com/free/terms/))
- Credits: USD 100 at sign-up + USD 20 per Free Tier activity, up to USD 100 more. ([activities](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier-plans-activities.html))
- **No multi-Region or cross-Region features on the Free plan**, including Bedrock cross-Region inference. ([Free plan services](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html))
- EC2 Free-plan-eligible types: t3.micro, t3.small, t4g.micro, t4g.small, c7i-flex.large, m7i-flex.large, all paid from credits. ([compute](https://aws.amazon.com/free/compute/))
- On a **Paid plan**, unused credits carry over and the account is not suspended when they run out, but usage beyond credits is billed. Cross-Region features are allowed.
- **One account per person:** "you are not eligible to receive Free Tier Credits for more than one account", and anyone who has ever held an AWS account is ineligible for the Free plan and credits. ([terms](https://aws.amazon.com/free/terms/), [FAQs](https://aws.amazon.com/free/faqs/))
- **Joining an AWS Organization** (or a Control Tower landing zone) ends an account's Free Tier credits immediately. ([FAQs](https://aws.amazon.com/free/faqs/))
- IAM Identity Center is not available on the Free plan, so team access is through IAM users. ([Free plan services](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html))

**Our reading of the PS (team decision, 24 Nov 2026):** "Free Tier" means anything free in AWS (always-free allowances or usage covered by Free Tier credits), on either plan. "A working project URL deployed on AWS" means any AWS-hosted link the judges can open; plain HTTP on an EC2 address would be enough, but we submit the free CloudFront HTTPS link so browsers show no warning. The PS does not require any particular AWS service, so only what a live link needs spends credits (EC2 with its disk and IP, Bedrock); other services are used only within their always-free allowances, and usage above an allowance also spends credits. We use **2–3 accounts, each owned by a different teammate** (one live, the rest for development), which stays within the one-account-per-person rule. The link is shared only with our team and the judges.

## What a winning project must show
- **Bharat Impact (30%)**: a real, everyday problem that Indian users live with, a clearly named Indian user, and a believable account of how the solution makes their lives measurably better.
- **Working AWS Build (25%)**: a live URL on AWS that works during judging and through Demo Day, with AWS services that are used well and explained in the Build Summary.
- **Innovation (25%)**: an idea or approach that judges have not seen before, shown in the product, not just claimed.

## Top 2 criteria to optimise for
1. **Bharat Impact (30%)**: the largest weight; judged on how real the problem is for Indian users.
2. **Working AWS Build (25%)**: tied with Innovation on weight; chosen because a broken or offline URL fails a required deliverable as well as the score.

## Watch out
- **Only the Team Leader may submit.** Submissions by any other member are not valid.
- **All deliverables in one Google Drive folder**, with the folder link in the 'Submission Link' field.
- **The live URL must stay accessible through Demo Day (17 Dec 2026).** The URL must be deployed on AWS. Round 1 judges open it at an unknown time before 5 Dec, so we freeze deploys to the live account from 30 Nov to 5 Dec. On the Free plan, running out of credits suspends the account and takes the URL down.
- **Each AWS account must belong to a different teammate** who never held an AWS account; never link our accounts in an AWS Organization.
- **Demo video must be under 3 minutes.**
- **Every participant must have an AWS Builder Center account and verified student enrollment to qualify to win.** Verification recommended by 27 Nov 2026.
- **Build on the AWS Free Tier.**
- **Original work only**; the solution must not be protected by patents, copyrights or publications.
- Team must **register on techfest.org** (deadline 30 Nov 2026, 11:59 PM IST).
- Techfest is not responsible for late or lost entries.
- Queries go only through the **Techfest Competition Portal → Doubt section**; emailed queries are not answered. Announcements come from siddhi@techfest.org.
- Finalists must attend in person at IIT Bombay.
- Organisers' and judges' decisions are final.
