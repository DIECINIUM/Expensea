#!/bin/sh
set -eu

: "${PGHOST:?Set PGHOST}"
: "${PGUSER:?Set PGUSER}"
: "${PGPASSWORD:?Set PGPASSWORD privately}"
: "${PGSSLMODE:=verify-full}"
export PGSSLMODE

case "$PGSSLMODE" in
    verify-full|verify-ca)
        : "${PGSSLROOTCERT_FILE:?Set PGSSLROOTCERT_FILE to the trusted database CA file}"
        test -f "$PGSSLROOTCERT_FILE"
        exec docker run --rm -i \
            --mount "type=bind,src=$PGSSLROOTCERT_FILE,dst=/tmp/database-ca.crt,readonly" \
            --env PGSSLROOTCERT=/tmp/database-ca.crt \
            --env PGHOST --env PGPORT --env PGUSER --env PGDATABASE \
            --env PGPASSWORD --env PGSSLMODE postgres:17-alpine "$@"
        ;;
    require|disable)
        exec docker run --rm -i --env PGHOST --env PGPORT --env PGUSER \
            --env PGDATABASE --env PGPASSWORD --env PGSSLMODE postgres:17-alpine "$@"
        ;;
    *)
        echo "Use verify-full for production; require/disable need explicit operator selection." >&2
        exit 1
        ;;
esac
