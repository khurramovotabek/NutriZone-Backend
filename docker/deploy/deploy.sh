#!/usr/bin/env bash
# Production deploy: ./deploy.sh [backend|frontend|all]   (default: all)
# Backend: pull -> build images -> migrate (old web keeps serving) -> rolling web swap (no 502) -> workers -> health check.
# Frontend: pull -> build in a copy -> swap .next -> standby on :3001 -> pm2 restart -> standby gone (no gap).
set -euo pipefail

ROOT=/opt/nutrizone
TARGET=${1:-all}
log() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }

# Zero-downtime web swap. `up` used to recreate both replicas at once: ~1 min of 502 on every deploy.
# nginx resolves `web` only when (re)loaded, so it is reloaded once the new replicas are up and once the old ones are gone;
# in between, a retiring replica refuses connections and nginx retries the request on another one (proxy_next_upstream).
roll_web() {
  local old new id ok
  old=$($DC ps -q web)
  local count; count=$(echo "$old" | grep -c . || true)
  $DC up -d --no-deps --no-recreate --scale web=$((count > 0 ? count * 2 : 2)) web
  new=$(comm -13 <(echo "$old" | sort) <($DC ps -q web | sort))
  for id in $new; do
    ok=0
    for _ in $(seq 1 60); do
      if docker exec "$id" curl -fsS -o /dev/null http://localhost:8000/health/live 2>/dev/null; then ok=1; break; fi
      sleep 2
    done
    if [ "$ok" != 1 ]; then
      echo "new web replica $id never became live -- removing the new replicas, the old ones keep serving" >&2
      docker logs --tail 40 "$id" >&2 || true
      echo "$new" | xargs -r docker rm -f >/dev/null
      exit 1
    fi
  done
  $DC exec -T nginx nginx -s reload
  sleep 2
  if [ -n "$old" ]; then
    echo "$old" | xargs -r docker stop -t 35 >/dev/null  # gunicorn finishes in-flight requests (graceful_timeout 30 s)
    echo "$old" | xargs -r docker rm >/dev/null
  fi
  $DC exec -T nginx nginx -s reload
}

deploy_backend() {
  log "Backend: git pull"
  cd "$ROOT/backend"
  git pull --ff-only
  DC="docker compose --env-file .env -f docker/compose/docker-compose.prod.yml"
  log "Backend: build"
  $DC build migrate web celery_worker_transactional celery_worker_default celery_worker_bulk celery_beat
  log "Backend: migrate + collectstatic"
  # a failing migration stops the deploy here, with the old web replicas still serving
  $DC run --rm -T --no-deps migrate
  log "Backend: web (rolling -- new replicas next to the old ones, then the old ones retire)"
  roll_web
  log "Backend: workers, beat, the rest"
  $DC up -d --no-deps --remove-orphans celery_worker_transactional celery_worker_default celery_worker_bulk celery_beat
  $DC up -d --no-deps db redis db_backup nginx
  log "Backend: health"
  for i in $(seq 1 30); do
    if curl -fsS -o /dev/null -H "X-Forwarded-Proto: https" http://127.0.0.1:8080/health/ready; then echo "ready"; break; fi
    sleep 3
  done
  curl -fsS -o /dev/null -H "X-Forwarded-Proto: https" -w "health/ready %{http_code}\n" http://127.0.0.1:8080/health/ready
  docker image prune -f >/dev/null
}

wait_http() {  # wait_http URL NAME -- up to 60 s for a 200
  for _ in $(seq 1 60); do
    if curl -fsS -o /dev/null --max-time 10 "$1"; then echo "$2 ready"; return 0; fi
    sleep 1
  done
  echo "$2 never answered $1" >&2
  return 1
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
  # No gap while the live process restarts: a standby on :3001 (the backup server of host nginx's nz_storefront
  # upstream, docker/deploy/host-nginx-tune.sh) answers meanwhile. Only one process serves at a time -- the
  # refresh-token exchange dedupe in proxy.ts is per process, so two live ones could replay a refresh token.
  cd "$ROOT/frontend"
  pm2 delete frontend-standby >/dev/null 2>&1 || true
  pm2 start npm --name frontend-standby --cwd "$ROOT/frontend" -- start -- -p 3001 -H 127.0.0.1 >/dev/null
  wait_http http://127.0.0.1:3001/ standby
  pm2 restart frontend --update-env
  wait_http http://127.0.0.1:3000/ frontend
  sleep 12  # host nginx keeps the restarted :3000 out for fail_timeout (10 s); the standby serves until then
  pm2 delete frontend-standby >/dev/null
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
