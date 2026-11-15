#!/usr/bin/env bash
set -Eeuo pipefail
umask 027
if (( EUID == 0 )); then
  exec runuser -u safspp -- /usr/local/sbin/safspp-manage "$@"
fi
[[ $(id -un) == safspp ]] || { echo 'Run as root or safspp.' >&2; exit 1; }
# Root-owned environment file; never enable shell tracing here.
set -a
source /etc/safspp/portal.env
set +a
cd /opt/safspp/source/portal
exec /opt/safspp/venv/bin/python manage.py "$@"
