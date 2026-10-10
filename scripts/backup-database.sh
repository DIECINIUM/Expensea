#!/bin/sh
set -eu
umask 077

: "${PGHOST:?Set PGHOST to the database hostname}"
: "${PGUSER:?Set PGUSER}"
: "${PGDATABASE:?Set PGDATABASE}"
: "${PGPASSWORD:?Set PGPASSWORD privately}"
: "${PGSSLMODE:=verify-full}"
export PGSSLMODE

if [ "$#" -ne 1 ] || [ -e "$1" ]; then
    echo "Usage: sh scripts/backup-database.sh NEW_BACKUP_PATH (must not exist)" >&2
    exit 1
fi
backup=$1
temporary="${backup}.partial"
if [ -e "$temporary" ]; then
    echo "Partial backup already exists; choose a new path." >&2
    exit 1
fi
trap 'rm -f "$temporary"' EXIT HUP INT TERM
sh "$(dirname "$0")/postgres-client.sh" \
    pg_dump --format=custom --no-owner --no-acl > "$temporary"
test -s "$temporary"
mv "$temporary" "$backup"
echo "Backup written. Store it in encrypted storage with a retention policy."
