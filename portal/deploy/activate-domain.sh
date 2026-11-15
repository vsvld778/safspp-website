#!/usr/bin/env bash
# Explicit opt-in only; never changes DNS, requests certificates or enables signup.
set -Eeuo pipefail
umask 077
MODE=--check
WITH_WWW=0
DNS_VERIFIED=0
for arg in "$@"; do
  case "$arg" in
    --check|--apply) MODE="$arg" ;;
    --www) WITH_WWW=1 ;;
    --dns-verified) DNS_VERIFIED=1 ;;
    *) echo 'Usage: activate-domain.sh [--check|--apply --dns-verified] [--www]' >&2; exit 2 ;;
  esac
done
(( EUID == 0 )) || { echo 'Run as root.' >&2; exit 1; }
DEPLOY=/opt/safspp/source/portal/deploy
ENV_FILE=/etc/safspp/portal.env
SITE=/etc/nginx/sites-available/safspp.conf
ENABLED=/etc/nginx/sites-enabled/safspp.conf
CERT=/etc/letsencrypt/live/safspp-domain
[[ -f "$ENV_FILE" && ! -L "$ENV_FILE" && -f "$SITE" && ! -L "$SITE" && -L "$ENABLED" ]] || { echo 'Complete the existing IP deployment first.' >&2; exit 1; }
[[ -r "$CERT/fullchain.pem" && -r "$CERT/privkey.pem" ]] || { echo 'Issue certificate safspp-domain for migrantmost.ru first; no certificate is requested here.' >&2; exit 1; }
openssl x509 -in "$CERT/fullchain.pem" -noout -checkend 3600 >/dev/null
openssl x509 -in "$CERT/fullchain.pem" -noout -checkhost migrantmost.ru >/dev/null
# Existing IP fallback continues to use its own certificate and renewal profile.
openssl x509 -in /etc/letsencrypt/live/safspp-ip/fullchain.pem -noout -checkend 3600 >/dev/null
openssl x509 -in /etc/letsencrypt/live/safspp-ip/fullchain.pem -noout -checkip 194.58.103.10 >/dev/null
DOMAINS=(migrantmost.ru)
if (( WITH_WWW )); then
  DOMAINS+=(www.migrantmost.ru)
  openssl x509 -in "$CERT/fullchain.pem" -noout -checkhost www.migrantmost.ru >/dev/null
fi
if (( DNS_VERIFIED )); then
  # A stale VPS resolver is tolerated only after these independent live checks.
  python3 "$DEPLOY/verify-domain-dns.py" "${DOMAINS[@]}"
else
  python3 - "${DOMAINS[@]}" <<'PY'
import socket, sys
for domain in sys.argv[1:]:
    try:
        addresses = {result[4][0] for result in socket.getaddrinfo(domain, 443, type=socket.SOCK_STREAM)}
    except socket.gaierror:
        raise SystemExit('DNS has not resolved for ' + domain)
    if addresses != {'194.58.103.10'}:
        raise SystemExit('DNS for ' + domain + ' must resolve exclusively to 194.58.103.10; check stale A/AAAA records first')
print('Local DNS resolves all selected names to the expected VPS.')
PY
fi
if [[ "$MODE" == --check ]]; then
  echo 'Certificate names, expiry and selected DNS checks passed. No settings changed.'
  echo 'After independently confirming ownership and public DNS, run --apply --dns-verified (plus --www only if verified).'
  exit 0
fi
(( DNS_VERIFIED )) || { echo 'Activation requires --dns-verified after the administrator confirms ownership and public DNS.' >&2; exit 1; }
exec 9>/run/lock/safspp-deploy.lock
flock -n 9 || { echo 'Another SAFSPP deployment/activation is running.' >&2; exit 1; }
BACKUP=/var/lib/safspp-deploy/domain-activation-$(date -u +%Y%m%dT%H%M%SZ)-$$
install -d -o root -g root -m 0700 "$BACKUP"
cp --preserve=mode,ownership "$ENV_FILE" "$BACKUP/portal.env"
cp --preserve=mode,ownership "$SITE" "$BACKUP/safspp.conf"
if [[ -f /etc/nginx/sites-available/safspp-ip-fallback.conf ]]; then
  cp --preserve=mode,ownership /etc/nginx/sites-available/safspp-ip-fallback.conf "$BACKUP/safspp-ip-fallback.conf"
fi
if [[ -f /etc/safspp/deployment-mode ]]; then
  cp --preserve=mode,ownership /etc/safspp/deployment-mode "$BACKUP/deployment-mode"
fi
OLD_TARGET=$(readlink "$ENABLED")
printf '%s\n' "$OLD_TARGET" > "$BACKUP/enabled-target.txt"
STAGED_ACME=/etc/nginx/sites-enabled/safspp-domain-acme.conf
STAGED_ACME_TARGET=''
if [[ -e "$STAGED_ACME" || -L "$STAGED_ACME" ]]; then
  [[ -L "$STAGED_ACME" && $(readlink "$STAGED_ACME") == /etc/nginx/sites-available/safspp-domain-acme.conf ]] || { echo 'Unexpected staging ACME entry; inspect it manually before activation.' >&2; exit 1; }
  STAGED_ACME_TARGET=$(readlink "$STAGED_ACME")
fi
ENV_CHANGED=0
CONFIG_CHANGED=0
MODE_CHANGED=0
rollback() {
  failure=${1:-$?}
  trap - ERR HUP INT TERM
  set +e
  rollback_ok=1
  if (( ENV_CHANGED )); then
    cp --preserve=mode,ownership "$BACKUP/portal.env" "$ENV_FILE" || rollback_ok=0
    systemctl restart safspp-portal || rollback_ok=0
  fi
  if (( CONFIG_CHANGED )); then
    cp --preserve=mode,ownership "$BACKUP/safspp.conf" "$SITE" || rollback_ok=0
    if [[ -f "$BACKUP/safspp-ip-fallback.conf" ]]; then
      cp --preserve=mode,ownership "$BACKUP/safspp-ip-fallback.conf" /etc/nginx/sites-available/safspp-ip-fallback.conf || rollback_ok=0
    fi
    ln -sfn "$OLD_TARGET" "$ENABLED" || rollback_ok=0
    if [[ -n "$STAGED_ACME_TARGET" ]]; then ln -sfn "$STAGED_ACME_TARGET" "$STAGED_ACME" || rollback_ok=0; fi
    if ! nginx -t || ! systemctl reload nginx; then rollback_ok=0; fi
  fi
  if (( MODE_CHANGED )); then
    if [[ -f "$BACKUP/deployment-mode" ]]; then
      cp --preserve=mode,ownership "$BACKUP/deployment-mode" /etc/safspp/deployment-mode || rollback_ok=0
    else
      printf 'ip\n' > /etc/safspp/deployment-mode || rollback_ok=0
      chmod 0600 /etc/safspp/deployment-mode || rollback_ok=0
    fi
  fi
  if (( rollback_ok )); then
    echo "Domain activation failed; prior configuration restored and service restarts accepted. Verify health. Restricted backup: $BACKUP" >&2
  else
    echo "Domain activation failed and rollback needs administrator attention. Restricted backup: $BACKUP" >&2
  fi
  exit "$failure"
}
trap rollback ERR
trap 'rollback 129' HUP
trap 'rollback 130' INT
trap 'rollback 143' TERM
CONFIG_CHANGED=1
if [[ -n "$STAGED_ACME_TARGET" ]]; then unlink "$STAGED_ACME"; fi
install -m 0644 "$DEPLOY/nginx/safspp-https.conf" /etc/nginx/sites-available/safspp-ip-fallback.conf
CANDIDATE=/etc/nginx/sites-available/safspp-domain.pending.conf
install -m 0644 "$DEPLOY/nginx/safspp-domain.conf" "$CANDIDATE"
if (( WITH_WWW )); then cat "$DEPLOY/nginx/safspp-domain-www.conf" >> "$CANDIDATE"; fi
ln -sfn "$CANDIDATE" "$ENABLED"
nginx -t
ENV_CHANGED=1
if (( WITH_WWW )); then
  python3 "$DEPLOY/configure-domain-env.py" "$ENV_FILE" --www
else
  python3 "$DEPLOY/configure-domain-env.py" "$ENV_FILE"
fi
/usr/local/sbin/safspp-manage check --deploy --fail-level ERROR
systemctl restart safspp-portal
curl --fail --silent --show-error --retry 8 --retry-connrefused --retry-delay 1 --max-time 10 \
  --header 'Host: migrantmost.ru' --header 'X-Forwarded-Proto: https' \
  http://127.0.0.1:8001/healthz/ >/dev/null
install -m 0644 "$CANDIDATE" "$SITE"
ln -sfn "$SITE" "$ENABLED"
nginx -t
systemctl reload nginx
# Nginx reload returns before all new workers are ready. Retry short-lived old
# worker responses, including certificate mismatches, without weakening TLS.
TLS_RETRY=(--retry 5 --retry-all-errors --retry-delay 1 --retry-max-time 20 --connect-timeout 3 --max-time 8)
# Resolve locally while retaining normal HTTPS hostname/chain verification.
curl --fail --silent --show-error "${TLS_RETRY[@]}" --resolve migrantmost.ru:443:127.0.0.1 https://migrantmost.ru/healthz/ >/dev/null
# IP clients may omit SNI; confirm that the fallback still presents the IP cert.
curl --fail --silent --show-error "${TLS_RETRY[@]}" --resolve 194.58.103.10:443:127.0.0.1 https://194.58.103.10/healthz/ >/dev/null
if (( WITH_WWW )); then
  RESULT=$(curl --fail --silent --show-error "${TLS_RETRY[@]}" --resolve www.migrantmost.ru:443:127.0.0.1 --output /dev/null --write-out '%{http_code} %{redirect_url}' https://www.migrantmost.ru/)
  [[ "$RESULT" == '308 https://migrantmost.ru/' ]]
fi
install -d -m 0755 /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/safspp-nginx <<'HOOK'
#!/bin/sh
set -eu
/usr/sbin/nginx -t
/usr/bin/systemctl reload nginx
HOOK
chmod 0755 /etc/letsencrypt/renewal-hooks/deploy/safspp-nginx
DEPLOYMENT_MODE=domain
(( ! WITH_WWW )) || DEPLOYMENT_MODE=domain-www
MODE_CHANGED=1
printf '%s\n' "$DEPLOYMENT_MODE" > /etc/safspp/deployment-mode
chown root:root /etc/safspp/deployment-mode
chmod 0600 /etc/safspp/deployment-mode
trap - ERR HUP INT TERM
echo 'Canonical site activated: https://migrantmost.ru/ . IP fallback retained; intake and registration mode unchanged.'
