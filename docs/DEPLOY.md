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
    }
  ]
}
```

### 3. Firewall (security group)
EC2 → Security Groups → **Create security group**. Name: `rulestorm-web`, in the default VPC.
- Inbound: **HTTP, port 80, from Anywhere-IPv4** (slice 12 narrows this to CloudFront only).
- No SSH rule: we use Session Manager, so port 22 stays closed.

### 4. The server
EC2 → **Launch instance**.
- Name: `rulestorm`.
- Image: **Ubuntu Server 24.04 LTS**, 64-bit (x86).
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
Write the address here: `[MISSING: elastic IP]`.

### 6. The code
- **Public repo:** nothing to do.
- **Private repo:** make a GitHub fine-grained token with read-only **Contents** access to this one repo and a short expiry. When git asks during a deploy, type your GitHub username and paste the token as the password. Nothing on the server saves it.

## Deploy (every time)

On the laptop, tag the version and push the tag:
```
git tag <tag>
git push origin <tag>
```
In EC2 → the instance → **Connect** → **Session Manager** → Connect. The shell starts in `sh`, so type `bash` first.

**First time:**
```
cd ~ && git clone https://github.com/eashan17/AWS_agent_simulation.git rulestorm && cd rulestorm && git checkout <tag> && bash deploy/deploy.sh <tag>
```

**Later deploys:**
```
cd ~/rulestorm && git fetch --tags && git checkout <tag> && bash deploy/deploy.sh <tag>
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

- [ ] 1 Budgets alert `rulestorm-monthly` listed
- [ ] 2 Role `rulestorm-ec2` with SSM and `rulestorm-bedrock`
- [ ] 3 Security group `rulestorm-web` (port 80 only)
- [ ] 4 Instance `rulestorm`, t3.small, Standard credits, no key pair
- [ ] 5 Elastic IP associated and written above
- [ ] 6 Code access (public repo, or a read-only token)
- [ ] First deploy prints `active (running) as user rulestorm`
- [ ] `llm smoke` on the server prints `auth: instance-role` and `ok: true`
- [ ] `curl http://<elastic-ip>/api/runs/demo` from the laptop shows `completed`
