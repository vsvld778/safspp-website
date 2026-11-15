#!/usr/bin/env bash
# Run only after reviewing and checking out the intended server-portal commit.
# This script does not fetch Git, run apt, request certificates or create accounts.
set -Eeuo pipefail
umask 027
SOURCE=/opt/safspp/source
APP="$SOURCE/portal"
DEPLOY="$APP/deploy"
ENV_FILE=/etc/safspp/portal.env
MODE=${1:---check}
[[ "$MODE" == --check || "$MODE" == --apply ]] || { echo 'Usage: bootstrap.sh --check|--apply' >&2; exit 2; }
(( EUID == 0 )) || { echo 'Run as root.' >&2; exit 1; }
[[ -d "$SOURCE/.git" && -f "$APP/manage.py" && -f "$APP/requirements.txt" ]] || { echo 'Expected the verified checkout at /opt/safspp/source with portal/.' >&2; exit 1; }
[[ $(git -C "$SOURCE" rev-parse --show-toplevel) == "$SOURCE" ]] || exit 1
git -C "$SOURCE" diff --quiet
git -C "$SOURCE" diff --cached --quiet
for bin in python3 nginx psql pg_dump pg_restore runuser systemctl rsync curl openssl git tar sha256sum flock; do
  command -v "$bin" >/dev/null || { echo "Missing prerequisite: $bin" >&2; exit 1; }
done
python3 -c 'import venv'
[[ -f "$SOURCE/index.html" && -d "$SOURCE/assets" ]] || { echo 'Expected static homepage files at checkout root.' >&2; exit 1; }
printf 'Verified checkout commit: %s\n' "$(git -C "$SOURCE" rev-parse HEAD)"
if [[ "$MODE" == --check ]]; then
  echo 'Prerequisites found. No system changes made. Run --apply after review.'
  exit 0
fi
if ! getent passwd safspp >/dev/null; then
  useradd --system --user-group --home-dir /var/lib/safspp --no-create-home --shell /usr/sbin/nologin safspp
fi
[[ $(getent passwd safspp | cut -d: -f7) == /usr/sbin/nologin ]] || { echo 'Existing safspp user must have nologin shell; review manually.' >&2; exit 1; }
[[ $(id -u safspp) != 0 ]] || exit 1
if id -nG safspp | tr ' ' '\n' | grep -Eq '^(sudo|wheel|docker|lxd)$'; then
  echo 'Runtime user belongs to a privileged group; review manually.' >&2
  exit 1
fi
install -d -o root -g root -m 0755 /opt/safspp /srv/safspp /srv/safspp/public /var/www/acme
install -d -o root -g safspp -m 0750 /etc/safspp
install -d -o safspp -g safspp -m 0750 /var/lib/safspp
install -d -o safspp -g safspp -m 0755 /srv/safspp/static
if [[ ! -e "$ENV_FILE" ]]; then
  python3 - "$ENV_FILE" <<'PY'
import os, secrets, sys
path = sys.argv[1]
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as stream:
    stream.write('DJANGO_SECRET_KEY=' + secrets.token_urlsafe(64) + '\n')
    stream.write('''DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=194.58.103.10,127.0.0.1,localhost
DJANGO_CSRF_TRUSTED_ORIGINS=https://194.58.103.10
DJANGO_TRUST_PROXY=true
DJANGO_SECURE_COOKIES=true
DJANGO_SECURE_SSL_REDIRECT=true
PUBLIC_SITE_URL=https://194.58.103.10/
DB_NAME=safspp
DB_USER=safspp
DB_HOST=/var/run/postgresql
DB_PORT=5432
STATIC_ROOT=/srv/safspp/static
REGISTRATION_MODE=closed
PORTAL_INTAKE_MODE=test
''')
PY
fi
[[ ! -L "$ENV_FILE" ]] || { echo 'Environment file must not be a symlink.' >&2; exit 1; }
chown root:safspp "$ENV_FILE"
chmod 0640 "$ENV_FILE"

systemctl enable --now postgresql
if ! runuser -u postgres -- psql --no-psqlrc -At --command="SELECT 1 FROM pg_roles WHERE rolname='safspp';" | grep -qx 1; then
  runuser -u postgres -- createuser --no-superuser --no-createdb --no-createrole safspp
fi
# Never elevate an existing role. Fail if an unexpected administrator role exists.
ROLE_FLAGS=$(runuser -u postgres -- psql --no-psqlrc -At --command="SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls FROM pg_roles WHERE rolname='safspp';")
[[ "$ROLE_FLAGS" == f ]] || { echo 'Existing database role has elevated rights; review manually.' >&2; exit 1; }
if ! runuser -u postgres -- psql --no-psqlrc -At --command="SELECT 1 FROM pg_database WHERE datname='safspp';" | grep -qx 1; then
  runuser -u postgres -- createdb --owner=safspp --template=template0 safspp
fi
HBA_FILE=$(runuser -u postgres -- psql --no-psqlrc -At --command='SHOW hba_file;')
python3 - "$HBA_FILE" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
text = p.read_text()
line = 'local   safspp   safspp   peer'
if line not in text.splitlines():
    p.write_text('# SAFSPP: local operating-system identity only.\n' + line + '\n' + text)
PY
runuser -u postgres -- psql --no-psqlrc -v ON_ERROR_STOP=1 --command='SELECT pg_reload_conf();' >/dev/null
runuser -u safspp -- psql --no-psqlrc --host=/var/run/postgresql --username=safspp --dbname=safspp --no-password -At --command='SELECT 1;' | grep -qx 1

if [[ ! -x /opt/safspp/venv/bin/python ]]; then python3 -m venv /opt/safspp/venv; fi
/opt/safspp/venv/bin/python -m pip install --disable-pip-version-check -r "$APP/requirements.txt"
/opt/safspp/venv/bin/python -m pip check
install -o root -g root -m 0755 "$DEPLOY/manage.sh" /usr/local/sbin/safspp-manage
install -o root -g root -m 0755 "$DEPLOY/backup.sh" /usr/local/sbin/safspp-backup
install -o root -g root -m 0755 "$DEPLOY/restore-check.sh" /usr/local/sbin/safspp-restore-check
install -o root -g root -m 0755 "$DEPLOY/prepare-public.py" /usr/local/sbin/safspp-prepare-public
if [[ -f /etc/systemd/system/safspp-portal.service ]]; then
  # Preserve pre-migration state on subsequent deployments.
  /usr/local/sbin/safspp-backup
fi
/usr/local/sbin/safspp-manage check --deploy --fail-level ERROR
/usr/local/sbin/safspp-manage migrate --noinput
/usr/local/sbin/safspp-manage collectstatic --noinput
find /srv/safspp/static -type d -exec chmod 0755 {} +
find /srv/safspp/static -type f -exec chmod 0644 {} +
/usr/local/sbin/safspp-prepare-public

install -d -m 0755 /etc/nginx/snippets
install -m 0644 "$DEPLOY/nginx/safspp-common.conf" /etc/nginx/snippets/safspp-common.conf
cat > /etc/nginx/conf.d/safspp-log.conf <<'NGINX'
# No query strings, cookies or referrers in the public-site request log.
log_format safspp_safe '$remote_addr [$time_local] "$request_method $uri $server_protocol" $status $body_bytes_sent';
NGINX
# Preserve HTTPS on repeat deployment. Initial bootstrap must remain HTTP-only.
if [[ -f /etc/nginx/sites-available/safspp.conf ]] && grep -q 'listen 443 ssl' /etc/nginx/sites-available/safspp.conf; then
  install -m 0644 "$DEPLOY/nginx/safspp-https.conf" /etc/nginx/sites-available/safspp.conf
else
  install -m 0644 "$DEPLOY/nginx/safspp-http.conf" /etc/nginx/sites-available/safspp.conf
fi
ln -sfn /etc/nginx/sites-available/safspp.conf /etc/nginx/sites-enabled/safspp.conf
nginx -t
for unit in safspp-portal.service safspp-backup.service safspp-backup.timer; do
  install -m 0644 "$DEPLOY/systemd/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemctl enable safspp-portal.service safspp-backup.timer
systemctl restart safspp-portal.service
systemctl start safspp-backup.timer
systemctl enable --now nginx
systemctl reload nginx
curl --fail --silent --show-error --retry 8 --retry-connrefused --retry-delay 1 --max-time 10 \
  --header 'Host: 194.58.103.10' --header 'X-Forwarded-Proto: https' \
  http://127.0.0.1:8001/healthz/ >/dev/null
install -d -o root -g root -m 0700 /var/lib/safspp-deploy
/opt/safspp/venv/bin/python -m pip freeze > /var/lib/safspp-deploy/requirements-installed.txt
git -C "$SOURCE" rev-parse HEAD > /var/lib/safspp-deploy/source-commit.txt
chmod 0600 /var/lib/safspp-deploy/*
/usr/local/sbin/safspp-backup
echo 'Portal started; registration remains as configured. HTTPS is a separate activation step.'
echo 'Host firewall/swap/security updates: bash /opt/safspp/source/portal/deploy/harden-host.sh'
