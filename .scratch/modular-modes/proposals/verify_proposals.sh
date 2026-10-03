#!/usr/bin/env bash
# Reproducible isolated schema/assertion verification; no production connection is accepted.
set -euo pipefail

case "${PGHOST:-}" in
  /tmp/amigo-mode016.*|/private/tmp/amigo-mode016.*) ;;
  *) echo 'PGHOST must be the isolated amigo-mode016 temporary cluster' >&2; exit 2 ;;
esac
case "${PGDATABASE:-}" in
  amigo_pairing|amigo_modes) ;;
  *) echo 'PGDATABASE must identify the isolated Mode proposal fixture' >&2; exit 2 ;;
esac
if [[ "${PGPORT:-0}" -lt 55000 ]]; then
  echo 'PGPORT must identify an isolated high-port test server' >&2
  exit 2
fi

# A fresh database is required; existing schema is never dropped or reset.
if [[ "$(psql -X -q -A -t -v ON_ERROR_STOP=1 -c "SELECT to_regclass('public.user_profiles') IS NULL")" != 't' ]]; then
  echo 'Refusing to rewrite an existing fixture; create a fresh isolated database' >&2
  exit 2
fi
psql -X -v ON_ERROR_STOP=1 -f tests/sql/bootstrap_supabase_roles.sql
for proposal_migration in migrations/*.sql; do
  psql -X -v ON_ERROR_STOP=1 -f "$proposal_migration"
done

if psql -X -v ON_ERROR_STOP=1 -f .scratch/modular-modes/proposals/016_session_modes_grants_handoffs.sql; then
  echo '016 incorrectly accepted a chain missing 015' >&2
  exit 1
fi
psql -X -v ON_ERROR_STOP=1 \
  -f .scratch/modular-modes/proposals/015_ordered_pairing_locks.sql \
  -f .scratch/modular-modes/proposals/assert_015_ordered_pairing_locks.sql \
  -f .scratch/modular-modes/proposals/016_session_modes_grants_handoffs.sql \
  -f .scratch/modular-modes/proposals/assert_016_session_modes_grants_handoffs.sql
