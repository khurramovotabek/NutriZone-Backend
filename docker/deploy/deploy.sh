#!/usr/bin/env bash
# Production deploy: ./deploy.sh [backend|frontend|all]   (default: all)
# Backend: pull -> build images -> migrate (compose dependency) -> restart -> health check.
# Frontend: pull -> build in a copy -> swap .next -> pm2 restart (the live site keeps serving during the build).
set -euo pipefail

ROOT=/opt/nutrizone
TARGET=${1:-all}
log() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }

deploy_backend() {
  log "Backend: git pull"
  cd "$ROOT/backend"
  git pull --ff-only
  DC="docker compose --env-file .env -f docker/compose/docker-compose.prod.yml"
  log "Backend: build"
  $DC build migrate web celery_worker_transactional celery_worker_default celery_worker_bulk celery_beat
  log "Backend: up (migrate runs first)"
  $DC up -d --remove-orphans
  log "Backend: health"
  for i in $(seq 1 30); do
    if curl -fsS -o /dev/null -H "X-Forwarded-Proto: https" http://127.0.0.1:8080/health/ready; then echo "ready"; break; fi
    sleep 3
  done
  curl -fsS -o /dev/null -H "X-Forwarded-Proto: https" -w "health/ready %{http_code}\n" http://127.0.0.1:8080/health/ready
  docker image prune -f >/dev/null
}

deploy_frontend() {
  log "Frontend: git pull"
  cd "$ROOT/frontend"
  git pull --ff-only
  BUILD="$ROOT/.frontend-build"
  rm -rf "$BUILD"
  mkdir -p "$BUILD"
  # Hard-link node_modules (fast, no extra disk); everything else is a real copy.
  rsync -a --exclude node_modules --exclude .next "$ROOT/frontend/" "$BUILD/"
  cp -al "$ROOT/frontend/node_modules" "$BUILD/node_modules"
  cd "$BUILD"
  FRESH_DEPS=0
  LOCK_SHA=$(sha256sum package-lock.json | cut -d' ' -f1)
  if [ "$LOCK_SHA" != "$(cat "$ROOT/frontend/.deps-lock-sha" 2>/dev/null)" ]; then
    log "Frontend: npm ci (lockfile changed)"
    rm -rf node_modules && npm ci --no-audit --no-fund
    FRESH_DEPS=1
  fi
  log "Frontend: next build"
  npm run build
  log "Frontend: swap + restart"
  if [ "$FRESH_DEPS" = 1 ]; then
    rm -rf "$ROOT/frontend/node_modules.old"
    mv "$ROOT/frontend/node_modules" "$ROOT/frontend/node_modules.old"
    mv node_modules "$ROOT/frontend/node_modules"
    echo "$LOCK_SHA" > "$ROOT/frontend/.deps-lock-sha"
  fi
  rm -rf "$ROOT/frontend/.next.old"
  [ -d "$ROOT/frontend/.next" ] && mv "$ROOT/frontend/.next" "$ROOT/frontend/.next.old"
  mv .next "$ROOT/frontend/.next"
  pm2 restart frontend --update-env
  sleep 4
  curl -fsS -o /dev/null -w "frontend %{http_code}\n" http://127.0.0.1:3000/
  rm -rf "$BUILD" "$ROOT/frontend/node_modules.old"
}

case "$TARGET" in
  backend) deploy_backend ;;
  frontend) deploy_frontend ;;
  all) deploy_backend; deploy_frontend ;;
  *) echo "usage: $0 [backend|frontend|all]"; exit 2 ;;
esac
log "Done"
