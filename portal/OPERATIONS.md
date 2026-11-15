# SAFSPP portal — deployment and operations

This deployment targets Ubuntu 24.04 on `194.58.103.10` (2 vCPU, 2 GB RAM,
40 GB storage). The existing GitHub Pages homepage remains unchanged. The server
copy gets a visible **«Личный кабинет · тестовый режим»** link and `noindex`.

## Layout and contract

| Purpose | Path or value |
| --- | --- |
| Reviewed source checkout | `/opt/safspp/source`, Git branch `server-portal` |
| Django application | `/opt/safspp/source/portal`, `manage.py`, `config.wsgi:application` |
| Python environment | `/opt/safspp/venv` |
| Runtime identity | `safspp:safspp`, system account, `/usr/sbin/nologin`, no sudo |
| Configuration | `/etc/safspp/portal.env`, `root:safspp`, mode `0640` |
| PostgreSQL | database/role `safspp`, Unix socket `/var/run/postgresql`, peer auth |
| Gunicorn | `127.0.0.1:8001`, two workers, service `safspp-portal` |
| Public homepage | `/srv/safspp/public` — allowlisted copy only |
| Django static files | `/srv/safspp/static` |
| ACME webroot | `/var/www/acme` |
| TLS certificate | `/etc/letsencrypt/live/safspp-ip/{fullchain,privkey}.pem` |
| Local backups | `/var/backups/safspp`, root-only, seven days |

Nginx serves `/` from the static copy and proxies only `/login/`, `/logout/`,
`/signup/`, `/cases/`, `/partners/`, `/admin/` and `/healthz/`. It never exposes the
Git checkout, `.git`, `.env`, backend source, or the `portal/` directory. Existing
public navigation/flags/mobile menu are preserved by the copy script.

## Prerequisites and first deployment

Install these Ubuntu packages as the server administrator before bootstrap:

```sh
apt install python3 python3-venv python3-pip nginx postgresql postgresql-client \
  curl rsync ca-certificates ufw fail2ban unattended-upgrades
```

`git`, `openssl`, `tar`, `gzip`, `coreutils` and `util-linux` are also required.
Bootstrap does **not** run `apt update`, install OS packages, fetch Git, issue
certificates or create administrator/customer accounts. The checkout must already
be present, clean and reviewed. `portal/` must contain the complete application,
templates, static assets, requirements and `deploy/` directory. Verify the exact
commit rather than deploying an unreviewed moving branch.

```sh
git -C /opt/safspp/source status --short
git -C /opt/safspp/source rev-parse HEAD
bash /opt/safspp/source/portal/deploy/bootstrap.sh --check
bash /opt/safspp/source/portal/deploy/bootstrap.sh --apply
bash /opt/safspp/source/portal/deploy/harden-host.sh
```

Run these commands as root. `--check` verifies prerequisites and does not change
the system. `--apply` is repeatable: it preserves the Django secret and existing
configuration, database contents, and an already enabled HTTPS configuration.
Before later migrations it takes a local backup. It records the source commit
and installed Python package versions in `/var/lib/safspp-deploy/`.

The source checkout and virtual environment must be writable only by the
administrator, not by `safspp` or the Nginx worker. Do not store deployment tokens,
private keys, database dumps, `.env` files or customer information in Git.

Host hardening preserves existing UFW rules and allows port 22, configured SSH
ports and the current SSH server port **before** enabling default-deny incoming.
It adds 80/443, creates a dedicated 1 GB swap file only if no swap is active,
enables security updates without automatic reboots, and enables conservative SSH
Fail2ban rules (10 failures/10 minutes, 10-minute ban). The current SSH client IP
is excluded when `SSH_CONNECTION` is available. Keep the original SSH session
open and confirm a **second** session succeeds before disconnecting. No SSH
authentication settings are changed.

## Configuration and controlled testing

The first bootstrap generates a random Django secret directly on the server. It
is never printed. The root-owned environment file uses `KEY=value` syntax; values
containing spaces must be quoted. It is read by systemd and the management helper,
so use simple quoted literal values, not shell expressions.

```text
DJANGO_DEBUG=False
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
```

There is no database password. A specific `local safspp safspp peer` rule is added
to PostgreSQL's active `pg_hba.conf`; other rules are preserved. The runtime DB
role has no superuser, role-creation, database-creation, replication or RLS-bypass
privileges. Do not make PostgreSQL or port 8001 publicly reachable.

Keep registration `closed` until the administrator selects the test accounts.
For invite-only testing use `REGISTRATION_MODE=invite` and configure
`REGISTRATION_INVITE_SHA256` with the SHA-256 digest of a strong invite token;
never commit the token or print it in deployment logs. Keep `PORTAL_INTAKE_MODE=test`
and use synthetic records only. `disabled` suspends intake entirely. Do not
switch to `live` before the operator, privacy process and service are approved:
live intake additionally requires `PORTAL_OPERATOR_NAME`, `PORTAL_POLICY_VERSION`
and `PORTAL_POLICY_URL` according to application validation.

After editing configuration:

```sh
/usr/local/sbin/safspp-manage check --deploy --fail-level ERROR
systemctl restart safspp-portal
```

Administrator creation is a separate, interactive handoff:

```sh
/usr/local/sbin/safspp-manage createsuperuser
```

Do not use environment variables, command-line arguments or transcripts to pass
the administrator password. The helper runs Django management commands as the
unprivileged `safspp` user.

## HTTPS on the IP address

Initial HTTP mode serves the public homepage and ACME challenges, but every
authentication/application route returns **503 with plain text**, no form and no
session cookie. TLS flags remain enabled in Django throughout. Direct loopback
health checks may include trusted proxy headers; do not expose Gunicorn.

The administrator installs Certbot from Snap (version **5.4 or newer**) and issues
an IP certificate using the webroot and Let's Encrypt's `shortlived` profile.
No script in this repository performs certificate issuance or accepts ACME terms.
The certificate must be named `safspp-ip` and cover IP `194.58.103.10`.

After issuance:

```sh
certbot --version
certbot certificates
bash /opt/safspp/source/portal/deploy/activate-https.sh
certbot renew --dry-run
systemctl list-timers --all | grep -E 'certbot|safspp'
```

The activation script checks certificate validity and the IP SAN, tests Nginx,
enables HTTPS and verifies `/healthz/` with normal certificate validation. HTTP
then redirects to HTTPS except for ACME challenges. A deploy hook reloads Nginx
after successful renewal. IP certificates are short-lived (six days): automatic
Snap renewal must remain enabled and external expiry monitoring is needed. Do
not disable renewal merely because the initial certificate works.

The homepage permits its existing inline JS/CSS. Portal pages allow only local
JavaScript and local resources; application templates must not depend on inline
JavaScript handlers, external CDNs or third-party fonts. Portal responses use
`Cache-Control: private, no-store`. Plain static assets receive only a one-hour
cache lifetime; immutable caching is not used for unversioned filenames.

## Verify a deployment

```sh
systemctl is-active postgresql nginx safspp-portal
systemctl is-enabled safspp-backup.timer
nginx -t
curl --fail --show-error https://194.58.103.10/healthz/
curl -I https://194.58.103.10/login/
curl -I http://194.58.103.10/login/
curl -I https://194.58.103.10/.git/config
curl -I https://194.58.103.10/portal/config/settings.py
ss -lntp
ufw status verbose
fail2ban-client status sshd
```

Expect healthy services, a valid certificate, HTTP-to-HTTPS redirect after
activation, private/no-store for login, 404 for source paths, Gunicorn only on
127.0.0.1:8001, and no public PostgreSQL listener. Before TLS activation the HTTP
login request must be 503. Check forms on a phone: registration remains closed or
invite-only, displayed intake mode is test, error messages do not expose secrets,
and ordinary users cannot access another user's case or staff pages. Application
tests and a role/access review are still required; deployment does not replace
them.

Useful diagnostics (do not paste unreviewed log contents into public channels):

```sh
journalctl -u safspp-portal -n 80 --no-pager
journalctl -u safspp-backup -n 80 --no-pager
systemctl status safspp-backup.timer --no-pager
df -h / /var/backups/safspp
free -h
```

Nginx application access logs are disabled to avoid recording invitation tokens
and case IDs. Public access logs omit query strings, cookies and referrers.
Gunicorn has no access log. Error logs can still contain operational details and
must be treated as restricted. Existing distro Nginx log rotation applies.

## Backups and restoration proof

The timer runs daily at **03:35 Europe/Moscow**, with up to ten minutes of jitter
and catch-up after downtime. It produces a PostgreSQL custom-format dump, a
configuration archive, a source-commit manifest and SHA-256 checksums. Files are
mode 0600 under a root-only 0700 directory. `prune_portal_data` then removes expired
sessions/rate-limit records according to application policy.

```sh
systemctl start safspp-backup.service
systemctl status safspp-backup.service --no-pager
/usr/local/sbin/safspp-restore-check /var/backups/safspp/safspp-YYYYMMDDTHHMMSSZ
```

The manual restore check validates checksums, creates a uniquely named temporary
database, restores the dump in one transaction, verifies application tables and
the migration table, and drops only that newly created test database. It never
restores into or drops the production `safspp` database. Do not treat a successful
`pg_dump` alone as proof of restoration.

Only complete root-owned archives marked `application=safspp`, with the exact
owned timestamp naming scheme and older than seven days, are deleted. Partial
archives remain for manual inspection. These local archives contain secrets and
are **not encrypted**; filesystem permissions restrict access. They do not protect
against loss of the VPS. Arrange a separate encrypted off-server backup and test
its recovery before accepting real personal data. TLS account/private-key files
are excluded from this application archive; manage them separately.

## Updates and rollback

Take a backup, fetch/review the intended `server-portal` commit as administrator,
record the old commit, then check out the reviewed commit and run bootstrap
`--check`, followed by `--apply`. Do not pull/fetch code as the runtime account.
Retain the previous `/var/lib/safspp-deploy/requirements-installed.txt` when a
strict dependency reproduction is needed; source ranges alone do not lock every
transitive Python dependency.

For a code-only rollback compatible with the current database schema, check out
the earlier reviewed commit and redeploy. Database migrations may be irreversible:
do not automatically reverse migrations or overwrite production from a backup.
Restore to a separate database first, verify it, and plan any production cutover
with the administrator. The scripts intentionally do not automate destructive
production restores or reset existing configuration.

## Primary references

- [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/)
- [PostgreSQL peer authentication](https://www.postgresql.org/docs/current/auth-peer.html)
- [PostgreSQL pg_dump and custom archives](https://www.postgresql.org/docs/current/app-pgdump.html)
- [systemd sandboxing options](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html)
- [Let's Encrypt: short-lived IP certificates and Certbot 5.4](https://letsencrypt.org/2026/03/11/shorter-certs-certbot.html)
