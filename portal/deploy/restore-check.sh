#!/usr/bin/env bash
# A manual proof of restoration into a fresh temporary DB; production is untouched.
set -Eeuo pipefail
umask 077
(( EUID == 0 )) || { echo 'Run as root.' >&2; exit 1; }
[[ $# == 1 ]] || { echo 'Usage: safspp-restore-check /var/backups/safspp/safspp-TIMESTAMP' >&2; exit 1; }
BACKUP=$(realpath -e -- "$1")
[[ "$BACKUP" =~ ^/var/backups/safspp/safspp-20[0-9]{6}T[0-9]{6}Z$ ]] || { echo 'Expected a local SAFSPP backup directory.' >&2; exit 1; }
[[ $(stat -c %u "$BACKUP") == 0 ]] || { echo 'Backup must belong to root.' >&2; exit 1; }
(cd "$BACKUP" && sha256sum --check --status SHA256SUMS)
TEST_DB="safspp_restorecheck_$(date -u +%Y%m%d%H%M%S)_$$"
CREATED=0
cleanup() {
  if (( CREATED )); then runuser -u postgres -- dropdb --if-exists -- "$TEST_DB"; fi
}
trap cleanup EXIT
runuser -u postgres -- createdb --owner=safspp --template=template0 -- "$TEST_DB"
CREATED=1
# stdin lets postgres read the root-only archive without changing its permissions.
runuser -u postgres -- pg_restore --exit-on-error --single-transaction --no-owner --no-acl --role=safspp --dbname="$TEST_DB" < "$BACKUP/database.dump"
TABLES=$(runuser -u postgres -- psql --no-psqlrc -At --dbname="$TEST_DB" --command="SELECT count(*) FROM pg_tables WHERE schemaname='public';")
[[ "$TABLES" =~ ^[0-9]+$ ]] && (( TABLES > 0 )) || { echo 'Restore produced no application tables.' >&2; exit 1; }
runuser -u postgres -- psql --no-psqlrc --dbname="$TEST_DB" --command='SELECT count(*) AS applied_migrations FROM django_migrations;'
echo "Restore verified in temporary database ($TABLES public tables); it will now be removed."
