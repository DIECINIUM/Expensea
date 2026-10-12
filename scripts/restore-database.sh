#!/bin/sh
set -eu

: "${PGHOST:?Set PGHOST to the restore database hostname}"
: "${PGUSER:?Set PGUSER}"
: "${PGDATABASE:?Set PGDATABASE to a new spendgraph_restore_* database}"
: "${PGPASSWORD:?Set PGPASSWORD privately}"
: "${PGSSLMODE:=verify-full}"
export PGSSLMODE

case "$PGDATABASE" in
    spendgraph_restore_*) ;;
    *) echo "Restore is restricted to new spendgraph_restore_* databases." >&2; exit 1 ;;
esac
if [ "$#" -ne 1 ] || [ ! -s "$1" ]; then
    echo "Usage: sh scripts/restore-database.sh BACKUP_PATH" >&2
    exit 1
fi
# createdb refuses an existing target; no restore command drops existing data.
sh "$(dirname "$0")/postgres-client.sh" createdb "$PGDATABASE"
sh "$(dirname "$0")/postgres-client.sh" \
    pg_restore --exit-on-error --no-owner --no-acl --dbname="$PGDATABASE" < "$1"
echo "Restore completed in the isolated database. Run migrations and smoke checks before relying on this backup."
