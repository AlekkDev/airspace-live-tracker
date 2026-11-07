#!/bin/bash
# Deploys main on the VM (docs/01-architecture.md#deployment): pull the code, build the images,
# run migrations before the new code starts, then restart what changed.
# Run by hand or by deploy.yml over Tailscale. Safe to run again: each step is idempotent.
set -euo pipefail

# Everything is inside main(), so bash has read the whole script before `git merge` can change it.
main() {
  cd "$(dirname "$0")/.."

  exec 9>/tmp/airspace-deploy.lock
  flock -n 9 || { echo "another deploy is running" >&2; exit 1; }

  if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo "local changes in $(pwd); commit them through a PR or discard them first:" >&2
    git status --short --untracked-files=no >&2
    exit 1
  fi
  git fetch --quiet origin main
  git checkout --quiet main
  git merge --quiet --ff-only origin/main
  echo "deploying $(git log --oneline -1)"

  cd infra
  docker compose pull --quiet --ignore-buildable
  docker compose build --quiet
  docker compose run --rm migrate
  docker compose up -d --wait --remove-orphans
  docker image prune -f >/dev/null
  docker compose ps --format '{{.Name}} {{.Status}}'
}

main "$@"
exit
