#!/usr/bin/env bash
# Production deploy for speechAgent on the Azure VM.
#
# Run from GitHub Actions (after git reset to origin/main) or manually on the VM:
#   bash /home/azureuser/speechAgent/scripts/deploy-vm.sh
#
# Safety:
#   - Additive DB migrations only (database/migrate.py) — never DROP SCHEMA
#   - Dump only when pending migrations > 0 (keep last 3)
#   - Restart API on failure if it never became healthy

set -euo pipefail

DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
REPO_DIR="${REPO_DIR:-/home/azureuser/speechAgent}"
WEB_ROOT="${WEB_ROOT:-/var/www/speechagent}"
BACKUP_DIR="${BACKUP_DIR:-${REPO_DIR}/backups/db}"
MIGRATE_PY="${REPO_DIR}/database/migrate.py"
API_STARTED=0

log() { echo "==> $*"; }
err() { echo "ERROR: $*" >&2; }

restore_api_if_needed() {
  if [ "${API_STARTED}" -eq 0 ]; then
    log "Deploy failed before API healthy — attempting to restart speechagent-api"
    sudo systemctl start speechagent-api || true
  fi
}
trap restore_api_if_needed EXIT

log "Deploy branch: ${DEPLOY_BRANCH}"
log "Repo: ${REPO_DIR}"
cd "${REPO_DIR}"

log "Stop backend (speechagent-api)"
sudo systemctl stop speechagent-api || true

log "Fetch and pull ${DEPLOY_BRANCH}"
git remote -v
git fetch origin
git checkout "${DEPLOY_BRANCH}"
git reset --hard "origin/${DEPLOY_BRANCH}"
git pull --ff-only origin "${DEPLOY_BRANCH}"
echo "Now at: $(git log -1 --oneline)"
echo "HEAD: $(git rev-parse HEAD)"

log "Backend dependencies"
cd "${REPO_DIR}/backend"
# shellcheck disable=SC1091
source venv/bin/activate
pip install -r requirements.txt

log "Database migrations (additive only; no DROP SCHEMA)"
if [ ! -f "${MIGRATE_PY}" ]; then
  err "missing ${MIGRATE_PY}"
  exit 1
fi
if [ ! -f "${REPO_DIR}/backend/.env" ]; then
  err "missing backend/.env (DATABASE_URL required)"
  exit 1
fi

# pending-count prints ONLY an integer on stdout; logs go to stderr.
PENDING_COUNT="$(python "${MIGRATE_PY}" pending-count | tr -d '[:space:]')"
echo "Pending migrations: ${PENDING_COUNT}"

if [ -z "${PENDING_COUNT}" ]; then
  err "pending-count returned empty"
  exit 1
fi
case "${PENDING_COUNT}" in
  *[!0-9]*)
    err "pending-count did not return an integer: [${PENDING_COUNT}]"
    exit 1
    ;;
esac

if [ "${PENDING_COUNT}" -gt 0 ]; then
  log "Pre-migrate dump (schema + data, compressed; keep last 3)"
  mkdir -p "${BACKUP_DIR}"
  if ! command -v pg_dump >/dev/null 2>&1; then
    err "pg_dump not found. Install postgresql-client on the VM."
    exit 1
  fi
  python "${MIGRATE_PY}" dump --dir "${BACKUP_DIR}" --keep 3
  log "Apply pending migrations"
  python "${MIGRATE_PY}" apply
else
  log "No pending migrations — skip dump (saves disk)"
fi
python "${MIGRATE_PY}" status

log "Start backend (speechagent-api)"
sudo systemctl start speechagent-api
sleep 3
if ! sudo systemctl is-active --quiet speechagent-api; then
  err "speechagent-api failed to start"
  sudo systemctl status speechagent-api --no-pager >&2 || true
  exit 1
fi
API_STARTED=1

log "Frontend production build"
cd "${REPO_DIR}/frontend"
npm ci
npm run build

log "Publish static files to nginx root (nginx stays up)"
sudo mkdir -p "${WEB_ROOT}"
sudo cp -r dist/. "${WEB_ROOT}/"
sudo chown -R www-data:www-data "${WEB_ROOT}"

log "Health checks"
curl -fsS --retry 5 --retry-delay 2 http://127.0.0.1:8000/health >/dev/null
HTTP_CODE="$(curl -fsS -o /dev/null -w '%{http_code}' --retry 3 http://127.0.0.1/)"
echo "Frontend HTTP status: ${HTTP_CODE}"
if [ "${HTTP_CODE}" -lt 200 ] || [ "${HTTP_CODE}" -ge 400 ]; then
  err "unexpected frontend HTTP status ${HTTP_CODE}"
  exit 1
fi

log "Deploy OK (${DEPLOY_BRANCH} @ $(cd "${REPO_DIR}" && git rev-parse --short HEAD))"
trap - EXIT
exit 0
