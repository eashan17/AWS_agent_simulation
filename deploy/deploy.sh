#!/usr/bin/env bash
# Deploys one tagged version of RuleStorm on the EC2 instance (slice 11).
#
# In a Session Manager shell, from the repo checkout at that tag:
#     bash deploy/deploy.sh <tag>
# It installs the tag in /opt/rulestorm/releases/<tag>, writes /etc/rulestorm.env only if it is
# missing (settings only), restores the seeded demo run (`reset-demo`, no Bedrock) and restarts
# rulestorm.service, which runs as the non-root user `rulestorm` on port 80.
# AWS access comes from the instance's IAM role. This script never writes AWS keys, and stops
# if it finds any on the machine.
set -euo pipefail

TAG="${1:-}"
if [ -z "$TAG" ]; then echo "usage: bash deploy/deploy.sh <tag>" >&2; exit 2; fi
if ! [[ "$TAG" =~ ^[A-Za-z0-9._-]+$ ]]; then echo "not a tag name: $TAG" >&2; exit 2; fi
if [ "$(id -u)" -ne 0 ]; then exec sudo bash "$0" "$@"; fi

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OWNER="${SUDO_USER:-root}"   # who owns the checkout; git runs as them, never as root
APP=/opt/rulestorm
DATA=/var/lib/rulestorm
ENV_FILE=/etc/rulestorm.env
UNIT=/etc/systemd/system/rulestorm.service
SVC=rulestorm

say() { printf '==> %s\n' "$*"; }
git_src() { sudo -u "$OWNER" -H git -c credential.helper= -C "$SRC" "$@"; }

# 1. The code at that tag. A private repo asks for a GitHub token here; git saves nothing.
if ! git_src rev-parse -q --verify "refs/tags/$TAG^{commit}" >/dev/null; then
  git_src fetch --quiet --tags origin
fi
if ! COMMIT="$(git_src rev-parse -q --short --verify "refs/tags/$TAG^{commit}")"; then
  echo "tag $TAG not found here or on origin; push it first: git push origin $TAG" >&2; exit 1
fi
say "deploying tag $TAG (commit $COMMIT)"

need=()
command -v git >/dev/null || need+=(git)
command -v curl >/dev/null || need+=(curl)
dpkg -s python3.12-venv >/dev/null 2>&1 || need+=(python3.12-venv)
if [ "${#need[@]}" -gt 0 ]; then
  say "installing ${need[*]}"
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${need[@]}" >/dev/null
fi

REL="$APP/releases/$TAG"
NEW="$REL.new"
rm -rf "$NEW"
mkdir -p "$NEW"
git_src archive "refs/tags/$TAG" | tar -x -C "$NEW"
python3.12 -m venv "$NEW/.venv"
"$NEW/.venv/bin/python" -m pip install --quiet --disable-pip-version-check "$NEW"
rm -rf "$REL"
mv "$NEW" "$REL"
ln -sfn "$REL" "$APP/current"
say "installed in $REL"

# 2. The service user, its data folder and the settings file.
id -u "$SVC" >/dev/null 2>&1 || useradd --system --home-dir "$DATA" --shell /usr/sbin/nologin "$SVC"
install -d -o "$SVC" -g "$SVC" -m 750 "$DATA"
if [ ! -f "$ENV_FILE" ]; then
  install -m 640 -o root -g "$SVC" "$REL/deploy/rulestorm.env" "$ENV_FILE"
  say "wrote $ENV_FILE (settings only)"
else
  say "kept $ENV_FILE"
fi

# 3. No AWS keys anywhere the app or a user could pick them up.
if grep -Eq '^[[:space:]]*(AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY|AWS_SESSION_TOKEN|AWS_PROFILE)[[:space:]]*=' "$ENV_FILE"; then
  echo "$ENV_FILE sets AWS keys or a profile; remove them, the instance role gives access" >&2; exit 1
fi
found="$(ls -d /root/.aws/credentials /home/*/.aws/credentials "$DATA/.aws/credentials" 2>/dev/null || true)"
if [ -n "$found" ]; then echo "AWS key files found, remove them: $found" >&2; exit 1; fi
say "AWS keys on this machine: none (Bedrock access comes from the instance role)"

# 4. The service and the demo run.
install -m 644 "$REL/deploy/rulestorm.service" "$UNIT"
systemctl daemon-reload
systemctl enable --quiet "$SVC"
sudo -u "$SVC" -H bash -c \
  'set -a; . /etc/rulestorm.env; set +a; cd /var/lib/rulestorm && exec /opt/rulestorm/current/.venv/bin/python -m rulestorm.cli reset-demo'
systemctl restart "$SVC"

for _ in $(seq 1 30); do
  curl -fsS http://127.0.0.1/api/health >/dev/null 2>&1 && break
  sleep 1
done
state="$(systemctl show -p ActiveState --value "$SVC")"
sub="$(systemctl show -p SubState --value "$SVC")"
pid="$(systemctl show -p MainPID --value "$SVC")"
user="$(ps -o user:32= -p "$pid" 2>/dev/null | tr -d ' ' || true)"
echo "rulestorm.service $state ($sub) as user ${user:-?}"
echo "health: $(curl -fsS http://127.0.0.1/api/health 2>&1 || true)"
echo "demo run: $(curl -fsS http://127.0.0.1/api/runs/demo 2>/dev/null \
  | python3 -c 'import json, sys; print(json.load(sys.stdin)["status"])' 2>&1 || echo 'not answering')"
if [ "$state" != active ] || [ "$user" != "$SVC" ]; then
  echo "deploy failed; see: journalctl -u $SVC -n 50 --no-pager" >&2; exit 1
fi
say "deployed tag $TAG (commit $COMMIT)"
