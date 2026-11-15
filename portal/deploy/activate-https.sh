#!/usr/bin/env bash
set -Eeuo pipefail
umask 027
(( EUID == 0 )) || { echo 'Run as root.' >&2; exit 1; }
exec 9>/run/lock/safspp-deploy.lock
flock -n 9 || { echo 'Another SAFSPP deployment/activation is running.' >&2; exit 1; }
if [[ -f /etc/safspp/deployment-mode ]] && grep -Eq '^domain(-www)?$' /etc/safspp/deployment-mode; then
  echo 'A custom domain is active. Use activate-domain.sh; IP activation must not replace it.' >&2
  exit 1
fi
DEPLOY=/opt/safspp/source/portal/deploy
CERT=/etc/letsencrypt/live/safspp-ip
[[ -r "$CERT/fullchain.pem" && -r "$CERT/privkey.pem" ]] || { echo 'Issue the IP certificate first; this script never requests one.' >&2; exit 1; }
openssl x509 -in "$CERT/fullchain.pem" -noout -checkend 3600 >/dev/null
openssl x509 -in "$CERT/fullchain.pem" -noout -checkip 194.58.103.10 >/dev/null
install -m 0644 "$DEPLOY/nginx/safspp-https.conf" /etc/nginx/sites-available/safspp-https.conf
OLD_TARGET=$(readlink /etc/nginx/sites-enabled/safspp.conf || true)
ln -sfn /etc/nginx/sites-available/safspp-https.conf /etc/nginx/sites-enabled/safspp.conf
if ! nginx -t; then
  [[ -n "$OLD_TARGET" ]] && ln -sfn "$OLD_TARGET" /etc/nginx/sites-enabled/safspp.conf
  echo 'HTTPS configuration rejected; prior active configuration retained.' >&2
  exit 1
fi
install -m 0644 "$DEPLOY/nginx/safspp-https.conf" /etc/nginx/sites-available/safspp.conf
ln -sfn /etc/nginx/sites-available/safspp.conf /etc/nginx/sites-enabled/safspp.conf
install -d -m 0755 /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/safspp-nginx <<'HOOK'
#!/bin/sh
set -eu
/usr/sbin/nginx -t
/usr/bin/systemctl reload nginx
HOOK
chmod 0755 /etc/letsencrypt/renewal-hooks/deploy/safspp-nginx
systemctl reload nginx
curl --fail --silent --show-error --max-time 15 https://194.58.103.10/healthz/ >/dev/null
echo 'HTTPS enabled and verified with normal certificate validation.'
