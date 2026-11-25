# Deploy

How RuleStorm gets onto its EC2 server in the live AWS account. You do the one-time console setup by hand, in order (we keep account setup out of scripts on purpose; see ARCHITECTURE.md). After that, each deploy is one command in a Session Manager shell.

- **Live account:** our current account, the one `rulestorm-dev` signs in to (team decision, 25 Nov). It is the only account we have, so development runs here too: keep test runs light. On 25 Nov it had **USD 100 of Free plan credits**, which must last until 17 Dec.
- **Region:** Asia Pacific (Sydney), ap-southeast-2. Check the Region menu at the top right of every console page.
- **Never deploy from 30 Nov to 5 Dec** (Round 1 judging).

## One-time setup (console)

### 1. Budgets alert (do this first)
Billing and Cost Management → Budgets → **Create budget**.
- Use a template → **Monthly cost budget**. Name: `rulestorm-monthly`.
- Budgeted amount: **USD 30**. Email: the team inbox, or the account owner's email.
- After creating it, edit it and add alerts at **50% and 80% of actual** spend, and **100% of forecasted** spend.
- Ours (25 Nov): alerts at 85% and 100% of actual and 100% of forecasted.
- Under the budget's advanced options, leave **Credits** unticked. The budget then counts what we use before credits are taken off, which is what runs the credits down.

Check from the laptop: `aws budgets describe-budgets --account-id <id> --profile rulestorm-dev` lists `rulestorm-monthly`.

### 2. The server's role (Bedrock without keys)
IAM → Roles → **Create role** → Trusted entity: AWS service → Use case: **EC2**.
- Attach the AWS managed policy **AmazonSSMManagedInstanceCore** (this lets Session Manager open a shell on the server).
- Name it `rulestorm-ec2` and create it.
- Open the role → Add permissions → **Create inline policy** → JSON. Paste the policy below and name it `rulestorm-bedrock`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CallTheOneModel",
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
      "Resource": "arn:aws:bedrock:ap-southeast-2::foundation-model/deepseek.v3.2"
    },
    {
      "Sid": "SmokeTestReadsOnly",
      "Effect": "Allow",
      "Action": ["bedrock:GetFoundationModel", "servicequotas:ListServiceQuotas"],
      "Resource": "*"
    },
    {
      "Sid": "WriteRunLinesToOneLogGroup",
      "Effect": "Allow",
      "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "arn:aws:logs:ap-southeast-2:<account-id>:log-group:/rulestorm/app:*"
    }
  ]
}
```
The third statement (added 25 Nov, slice 14) lets the app write run lines to one log group only (step 9). Replace `<account-id>` with the account's 12-digit ID.

### 3. Firewall (security group)
EC2 → Security Groups → **Create security group**. Name: `rulestorm-web`, in the default VPC.
- Inbound: **HTTP, port 80, from Anywhere-IPv4** (kept open so `http://15.134.48.1` stays as the backup link).
- No SSH rule: we use Session Manager, so port 22 stays closed.

### 4. The server
EC2 → **Launch instance**.
- Name: `rulestorm`. Instance `i-08888d059fbc81572`.
- Image: **Ubuntu Server LTS**, 64-bit (x86). Ours runs 26.04 (Python 3.14); the script needs Python 3.12 or newer.
- Instance type: **t3.small**.
- Key pair: **Proceed without a key pair**.
- Network: default VPC, auto-assign public IP **on**, security group **rulestorm-web**.
- Storage: **16 GiB gp3**.
- Advanced details:
  - IAM instance profile: **rulestorm-ec2**.
  - Credit specification: **Standard**. t3 defaults to Unlimited, which can bill extra CPU time.
  - Metadata version: **V2 only**.

Cost from our credits: about USD 0.03 an hour for the server, plus USD 0.005 an hour for its public address and about USD 1.50 a month for the disk. That comes to about **USD 18 up to 17 Dec**, leaving the rest of the USD 100 for Bedrock.

### 5. A fixed address (Elastic IP)
EC2 → Elastic IPs → **Allocate Elastic IP address** → Allocate. Then Actions → **Associate** → instance `rulestorm`.
Our address: **15.134.48.1**.

### 6. The code
- **Public repo:** nothing to do.
- Ours is **public** since 25 Nov.
- **Private repo:** make a GitHub fine-grained token with read-only **Contents** access to this one repo and a short expiry. When git asks during a deploy, type your GitHub username and paste the token as the password. Nothing on the server saves it.

### 7. The HTTPS link (CloudFront)
Created 25 Nov (slice 12): distribution **E1IG4DB09R82EC**, link **https://d2emiyaz9dq4bi.cloudfront.net**. This is the link we submit.

| Setting | Value |
|---|---|
| Origin | `ec2-15-134-48-1.ap-southeast-2.compute.amazonaws.com` (the Elastic IP's AWS name; CloudFront needs a name, not an IP), **HTTP only**, port 80 |
| Origin response timeout | **60 s** (a blueprint takes up to 55 s); keep-alive 5 s |
| Behaviours | `/api/*` and the default: viewer **Redirect HTTP to HTTPS**; allowed methods **GET, HEAD, OPTIONS, PUT, POST, PATCH, DELETE** |
| Cache policy | **Managed-CachingDisabled** (nothing is cached, so every answer is live) |
| Origin request policy | **Managed-AllViewer** (headers, query strings and cookies go through to the server) |
| Compression | on |
| Price class | **North America, Europe, Asia, Middle East and Africa** (PriceClass_200, includes India) |
| HTTP versions | HTTP/2 and HTTP/3; IPv6 on |

Cost: inside CloudFront's always-free allowance (1 TB and 10 million requests a month).

### 8. Alarm if the server dies (CloudWatch + SNS)
- SNS topic **rulestorm-alerts** (Sydney), email subscription to the budget alert's address. The subscription only works after someone clicks **Confirm subscription** in AWS's email.
- CloudWatch alarm **rulestorm-status-check**:
  - metric `AWS/EC2 StatusCheckFailed` for the instance, Maximum over 1 minute;
  - goes off when it is ≥ 1 for 3 minutes in a row;
  - **missing data counts as failing**, so a stopped server also sets it off;
  - emails the topic when it goes off and again when the server is OK.
- Cost: inside the always-free allowances (10 alarms; 1,000 emails a month).
- This alarm only sees the server. If the app stops while the server is fine, it stays quiet; for that, check `/api/health`.

### 9. Run metrics and logs (CloudWatch Logs, slice 14)
- CloudWatch → Log groups → **Create log group** `/rulestorm/app` in Sydney, retention **7 days**.
- The role's third statement (step 2) lets the app write to it; the unit sets `RULESTORM_LOG_GROUP=/rulestorm/app`.
- Each finished run writes one JSON line (stream `runs-<date>`) in CloudWatch's embedded metric format, so CloudWatch makes three metrics from it in namespace **RuleStorm**, with no dimensions: `LLMCalls`, `Tokens` and `RunDurationSeconds`. A failed run reports only `RunDurationSeconds`.
- Check from the laptop: `aws cloudwatch list-metrics --namespace RuleStorm --region ap-southeast-2`. Metrics appear a few minutes after the first line.
- Cost: inside the always-free allowances (5 GB of logs, 10 custom metrics; this uses 3).

## Deploy (every time)

On the laptop, tag the version and push the tag:
```
git tag <tag>
git push origin <tag>
```
In EC2 → the instance → **Connect** → **Session Manager** → Connect. The shell starts in `sh`, so type `bash` first.

The server keeps one checkout in `/opt/rulestorm/src`, owned by root, so the same commands work from Session Manager and from Run Command.

**First time:**
```
sudo git clone https://github.com/eashan17/AWS_agent_simulation.git /opt/rulestorm/src && sudo git -C /opt/rulestorm/src checkout <tag> && bash /opt/rulestorm/src/deploy/deploy.sh <tag>
```

**Later deploys:**
```
sudo git -C /opt/rulestorm/src fetch --tags && sudo git -C /opt/rulestorm/src checkout <tag> && bash /opt/rulestorm/src/deploy/deploy.sh <tag>
```

The script ends with these lines:
```
==> AWS keys on this machine: none (Bedrock access comes from the instance role)
restored run demo (schema 2) with policy and blueprint
rulestorm.service active (running) as user rulestorm
health: {"ok":true}
demo run: completed
==> deployed tag <tag> (commit …)
```

Check that the server reaches Bedrock through its role. This makes one small Bedrock call:
```
sudo -u rulestorm -H bash -c 'set -a; . /etc/rulestorm.env; set +a; cd /var/lib/rulestorm && /opt/rulestorm/current/.venv/bin/python -m rulestorm.cli llm smoke'
```
It must print `auth: instance-role` and `ok: true`.

From the laptop:
```
curl -s http://<elastic-ip>/api/health
curl -s http://<elastic-ip>/api/runs/demo
```

**Deploy from the laptop without opening a shell:** AWS Systems Manager → Run Command → `AWS-RunShellScript` on instance `rulestorm`, with the later-deploy line above as the command (it runs as root; first deploy on 25 Nov ran this way).

## On the server

| What | Where |
|---|---|
| Code (read-only) | `/opt/rulestorm/current` → `/opt/rulestorm/releases/<tag>` |
| Settings | `/etc/rulestorm.env` (written on the first deploy only; edit it, then `sudo systemctl restart rulestorm`) |
| Store and run files | `/var/lib/rulestorm` (`rulestorm.db`, `runs/`) |
| Service | `rulestorm.service`, user `rulestorm`, port 80 |
| Logs | `journalctl -u rulestorm -n 100 --no-pager` |

The live caps are lower than the code's defaults: 10 runs and 1,000 model calls a day, about USD 2 at most. To roll back, run the deploy with the previous tag.

## Checklist

- [x] 1 Budgets alert `rulestorm-monthly` listed
- [x] 2 Role `rulestorm-ec2` with SSM and `rulestorm-bedrock`
- [x] 3 Security group `rulestorm-web` (port 80 only)
- [x] 4 Instance `rulestorm`, t3.small, Standard credits, no key pair
- [x] 5 Elastic IP associated and written above
- [x] 6 Code access (public repo, or a read-only token)
- [x] First deploy prints `active (running) as user rulestorm`
- [x] `llm smoke` on the server prints `auth: instance-role` and `ok: true`
- [x] 7 CloudFront link answers `/api/health` with 200
- [x] 8 Alarm email confirmed (SNS subscription not `pending confirmation`)
- [x] `curl http://<elastic-ip>/api/runs/demo` from the laptop shows `completed`
- [x] 9 After a run, `aws cloudwatch list-metrics --namespace RuleStorm` lists `LLMCalls`, `Tokens`, `RunDurationSeconds` (25 Nov, run L-2237d170)
