#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
(( EUID == 0 )) || { echo 'Run as root.' >&2; exit 1; }
BACKUPS=/var/backups/safspp
install -d -o root -g root -m 0700 "$BACKUPS"
exec 9>/run/lock/safspp-backup.lock
flock -n 9 || { echo 'Another SAFSPP backup is running.' >&2; exit 1; }
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP="$BACKUPS/safspp-$STAMP"
[[ ! -e "$BACKUP" ]] || { echo 'Backup timestamp already exists.' >&2; exit 1; }
install -d -o root -g root -m 0700 "$BACKUP"
# Redirection is performed by root; the service account cannot access the archive.
runuser -u safspp -- pg_dump --host=/var/run/postgresql --username=safspp --dbname=safspp --format=custom --no-password > "$BACKUP/database.dump.partial"
pg_restore --list "$BACKUP/database.dump.partial" >/dev/null
mv "$BACKUP/database.dump.partial" "$BACKUP/database.dump"
CONFIG_PATHS=(
  etc/safspp
  etc/nginx/sites-available/safspp.conf
  etc/nginx/snippets/safspp-common.conf
  etc/nginx/conf.d/safspp-log.conf
  etc/systemd/system/safspp-portal.service
  etc/systemd/system/safspp-backup.service
  etc/systemd/system/safspp-backup.timer
)
for optional in var/lib/safspp-deploy etc/nginx/sites-available/safspp-ip-fallback.conf etc/apt/apt.conf.d/52safspp-security etc/fail2ban/jail.d/safspp-sshd.local etc/sysctl.d/90-safspp-swap.conf; do
  [[ ! -e "/$optional" ]] || CONFIG_PATHS+=("$optional")
done
tar -czf "$BACKUP/configuration.tar.gz" -C / "${CONFIG_PATHS[@]}"
COMMIT=$(git -C /opt/safspp/source rev-parse HEAD)
printf '{"application":"safspp","completed_at":"%s","source_commit":"%s"}\n' "$STAMP" "$COMMIT" > "$BACKUP/manifest.json"
chmod 0600 "$BACKUP"/*
(
  cd "$BACKUP"
  sha256sum database.dump configuration.tar.gz manifest.json > SHA256SUMS
)
# Only complete, root-owned archives created by this script are eligible.
python3 - "$BACKUPS" <<'PY'
from pathlib import Path
import datetime, json, re, shutil, sys
base = Path(sys.argv[1])
cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)
for entry in base.iterdir():
    if entry.is_symlink() or not entry.is_dir() or entry.stat().st_uid != 0:
        continue
    if not re.fullmatch(r'safspp-20\d{6}T\d{6}Z', entry.name):
        continue
    try:
        manifest = json.loads((entry / 'manifest.json').read_text())
        when = datetime.datetime.strptime(manifest['completed_at'], '%Y%m%dT%H%M%SZ').replace(tzinfo=datetime.timezone.utc)
        complete = (entry / 'SHA256SUMS').is_file()
    except (OSError, ValueError, KeyError):
        continue
    if manifest.get('application') == 'safspp' and complete and when < cutoff:
        shutil.rmtree(entry)
PY
echo "Backup complete: $BACKUP"
