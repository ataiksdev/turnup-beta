#!/usr/bin/env bash
# Update the running app to the latest commit of the checked-out branch.
#
# Run by GitHub Actions over SSH after CI passes (the Actions key is restricted to this
# script; see setup.sh), or by hand on the server:  /opt/turnup/deploy/oracle/deploy.sh
set -euo pipefail
cd "$(dirname "$0")/../.."

branch="$(git rev-parse --abbrev-ref HEAD)"
echo "==> Updating to the latest '$branch'"
git fetch --quiet origin "$branch"
before="$(git rev-parse --short HEAD)"
git reset --quiet --hard "origin/$branch"   # .env and data volumes aren't tracked: untouched
after="$(git rev-parse --short HEAD)"
echo "    $before -> $after"

echo "==> Rebuilding and restarting (migrations run first, automatically)"
docker compose up -d --build --remove-orphans

echo "==> Waiting for the API to report healthy"
for _ in $(seq 1 60); do
  state="$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q backend)" 2>/dev/null || true)"
  if [ "$state" = "healthy" ]; then
    docker image prune -f >/dev/null
    docker compose ps --format 'table {{.Service}}\t{{.Status}}'
    echo "==> Deployed $after"
    exit 0
  fi
  sleep 3
done

echo "!! The API did not become healthy. Recent logs:" >&2
docker compose logs --tail 60 migrate backend >&2
exit 1
