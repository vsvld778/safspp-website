# Optional custom domain: migrantmost.ru

These files are prepared configuration only. Adding them to the checkout does
not change DNS or the running IP website. `bootstrap.sh` stays in IP mode until
`activate-domain.sh --apply --dns-verified` succeeds. No script here orders a
domain, changes registrar records, requests a certificate or opens registration.

## Before activation

The administrator must independently confirm control of `migrantmost.ru` and
that public DNS points to `194.58.103.10`. The script also checks the server's
local DNS resolution, but that is a consistency check, not proof of ownership.
Remove stale A/AAAA records that direct visitors to another server. This prepared
deployment uses IPv4; it deliberately refuses activation while any selected name
resolves to an unconfigured IPv6 address.

Issue a certificate named **`safspp-domain`** for `migrantmost.ru`, with files:

```text
/etc/letsencrypt/live/safspp-domain/fullchain.pem
/etc/letsencrypt/live/safspp-domain/privkey.pem
```

The ACME webroot is `/var/www/acme`. After DNS verification for **both**
`migrantmost.ru` and `www.migrantmost.ru`, explicitly enable the prepared
**HTTP-only ACME** server block before certificate issuance:

```sh
install -m 0644 /opt/safspp/source/portal/deploy/nginx/safspp-domain-acme.conf /etc/nginx/sites-available/safspp-domain-acme.conf
ln -sfn /etc/nginx/sites-available/safspp-domain-acme.conf /etc/nginx/sites-enabled/safspp-domain-acme.conf
nginx -t && systemctl reload nginx
```

This serves only challenge files; all other paths return plain-text 503, without
forms or cookies. Verify a harmless temporary challenge through the public
hostname before issuance. The prepared temporary `server_name` contains both
names, so test the challenge URL through both. For an apex-only deployment whose
www DNS is not yet verified, remove www from that temporary block first. Certificate
issuance remains an administrator action. The activation script removes only this
exact owned staging symlink on success and restores it on rollback. Do not enable
an HTTPS server block before a valid matching certificate exists.

The existing `safspp-ip` certificate must also remain valid. It is used by the
retained IP fallback, with its existing renewal profile.

## Activate the apex domain

Run as root, from a reviewed checkout:

```sh
bash /opt/safspp/source/portal/deploy/activate-domain.sh --check
# Only after independently confirming ownership/public DNS:
bash /opt/safspp/source/portal/deploy/activate-domain.sh --apply --dns-verified
```

`--check` is read-only and validates certificate names/expiry and local DNS.
`--apply` requires the explicit `--dns-verified` flag. It validates Nginx before
reloading, preserves a restricted backup of the previous configuration, updates
the environment atomically, checks Django and health, and automatically restores
the previous application/site configuration if a subsequent step fails.
`ERR`, `HUP`, `INT` and `TERM` trigger rollback once mutation begins. Bootstrap and
both activation scripts share a non-blocking deployment lock. Prefer running the
activation in a transient systemd unit so a dropped SSH connection does not
interrupt it; inspect that unit's exit status and journal before considering it
complete. A forced kill/power loss cannot run shell traps and requires checking
the retained backup and current configuration manually.

After success:

- `https://migrantmost.ru/` is canonical; HTTP redirects there except ACME.
- `PUBLIC_SITE_URL=https://migrantmost.ru/`.
- `DJANGO_ALLOWED_HOSTS` includes the apex domain, IP and loopback names.
- `DJANGO_CSRF_TRUSTED_ORIGINS` includes HTTPS apex and the existing HTTPS IP.
- Secure cookies, HTTPS redirect and trusted proxy handling remain enabled.
- Existing registration/intake modes, secrets and unrelated settings are preserved.
- `https://194.58.103.10/` remains available as a compatible fallback.
- `/etc/safspp/deployment-mode` is `domain`; later bootstrap runs preserve this.

## Optional www redirect

Do not add `www` merely because the apex works. First confirm ownership and DNS
for **`www.migrantmost.ru`**, then expand the same `safspp-domain` certificate to
include both names. After that:

```sh
bash /opt/safspp/source/portal/deploy/activate-domain.sh --check --www
bash /opt/safspp/source/portal/deploy/activate-domain.sh --apply --dns-verified --www
```

HTTP and HTTPS `www` then redirect to `https://migrantmost.ru`, preserving the
request path/query. HTTP ACME remains directly reachable. The persisted mode is
`domain-www`. Without `--www`, no www-specific virtual host is installed or
promised to work. Repeat invocations are safe; the latest explicit choice of
`--www` determines whether the optional redirect is installed.

## Verification and renewal

```sh
nginx -t
curl --fail --show-error https://migrantmost.ru/healthz/
curl -I http://migrantmost.ru/login/
curl -I https://migrantmost.ru/login/
# Only if --www was activated:
curl -I https://www.migrantmost.ru/
certbot renew --dry-run
systemctl list-timers --all | grep certbot
```

Verify the same results from a separate network/device to cover public DNS and
routing. TLS checks use normal hostname/chain verification; never use `curl -k`
or disable browser certificate checks. Both certificate lineages must continue
renewing. The deploy hook reloads Nginx after successful renewal. The existing
noindex/test-site markings remain: domain activation does not enable production
intake or remove staging notices.

The IP fallback is loaded before the domain TLS server so clients making direct
IP requests without SNI still receive the IP certificate. Activation verifies
both the domain and IP health endpoints with TLS validation before committing.

Activation backups are root-only under
`/var/lib/safspp-deploy/domain-activation-TIMESTAMP-PID/` and include the secret
environment file. They must not be copied into the repository. They are retained
for deliberate administrator rollback, not automatically deleted by the seven-day
database-backup retention job.
