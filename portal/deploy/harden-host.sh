#!/usr/bin/env bash
# Dedicated-server settings. Preserve all existing firewall rules and SSH access.
set -Eeuo pipefail
(( EUID == 0 )) || { echo 'Run as root.' >&2; exit 1; }
for bin in ufw swapon fallocate mkswap sshd; do command -v "$bin" >/dev/null; done
if [[ -z $(swapon --show --noheadings) ]]; then
  SWAP=/swapfile-safspp
  if [[ -e "$SWAP" ]]; then
    [[ -f "$SWAP" && ! -L "$SWAP" ]] || { echo 'Unexpected swap path.' >&2; exit 1; }
    [[ $(blkid -s TYPE -o value "$SWAP" 2>/dev/null) == swap ]] || { echo 'Existing named swap file is not initialized; inspect it manually.' >&2; exit 1; }
  else
    fallocate -l 1G "$SWAP"
    chmod 0600 "$SWAP"
    mkswap "$SWAP"
  fi
  swapon "$SWAP"
  if ! awk '$1=="/swapfile-safspp" {found=1} END {exit !found}' /etc/fstab; then
    printf '\n/swapfile-safspp none swap sw 0 0\n' >> /etc/fstab
  fi
fi
printf 'vm.swappiness=10\n' > /etc/sysctl.d/90-safspp-swap.conf
sysctl --load=/etc/sysctl.d/90-safspp-swap.conf

# Allow standard SSH and every configured/current SSH port BEFORE default deny.
SSH_PORTS=$( { printf '22\n'; sshd -T | awk '$1=="port" {print $2}'; if [[ -n ${SSH_CONNECTION:-} ]]; then printf '%s\n' "$SSH_CONNECTION" | awk '{print $4}'; fi; } | sort -nu)
while read -r port; do
  [[ "$port" =~ ^[0-9]+$ ]] && (( port >= 1 && port <= 65535 )) || exit 1
  ufw allow "$port/tcp" comment 'SAFSPP preserve SSH'
done <<< "$SSH_PORTS"
ufw allow 80/tcp comment 'SAFSPP HTTP and ACME'
ufw allow 443/tcp comment 'SAFSPP HTTPS'
ufw default deny incoming
ufw default allow outgoing
ufw --force enable

install -d -m 0755 /etc/fail2ban/jail.d
SSH_IGNORE='127.0.0.1/8 ::1'
if [[ -n ${SSH_CONNECTION:-} ]]; then
  CLIENT_IP=${SSH_CONNECTION%% *}
  if python3 - "$CLIENT_IP" <<'PY'
import ipaddress, sys
ipaddress.ip_address(sys.argv[1])
PY
  then SSH_IGNORE="$SSH_IGNORE $CLIENT_IP"; fi
fi
cat > /etc/fail2ban/jail.d/safspp-sshd.local <<EOF
[sshd]
enabled = true
backend = systemd
port = $(printf '%s' "$SSH_PORTS" | tr '\n' ',')
maxretry = 10
findtime = 10m
bantime = 10m
ignoreip = $SSH_IGNORE
EOF
fail2ban-client --test
systemctl enable --now fail2ban
systemctl reload fail2ban

# Security-only policy augments Ubuntu's package-managed defaults.
cat > /etc/apt/apt.conf.d/52safspp-security <<'APT'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
Unattended-Upgrade::Allowed-Origins {
  "${distro_id}:${distro_codename}-security";
  "${distro_id}ESMApps:${distro_codename}-apps-security";
  "${distro_id}ESM:${distro_codename}-infra-security";
};
Unattended-Upgrade::Automatic-Reboot "false";
APT
systemctl enable --now apt-daily.timer apt-daily-upgrade.timer
echo 'Host hardening configured. Verify a second SSH session before closing this one.'
