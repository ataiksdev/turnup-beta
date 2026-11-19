#!/usr/bin/env bash
# One-time setup of a fresh Oracle Cloud Ubuntu VM to run the Turnup backend.
# Follow deploy/oracle/README.md; in short, from your PC:
#   scp deploy/oracle/setup.sh ubuntu@<server-ip>:
#   ssh ubuntu@<server-ip>        then, on the server:   bash setup.sh
# (It asks questions, so run it in an interactive SSH session, not as `ssh host 'bash ...'`.)
# Safe to run again: every step checks whether it's already done.
set -euo pipefail

REPO="${REPO:-git@github.com:ataiksdev/turnup-beta.git}"
BRANCH="${BRANCH:-claude/build-turnup-platform-hhOzs}"
APP_DIR="${APP_DIR:-/opt/turnup}"
ME="$(id -un)"

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
ask()  { local prompt="$1" var; read -r -p "$prompt" var </dev/tty; printf '%s' "$var"; }

[ "$(id -u)" -ne 0 ] || { echo "Run this as your normal user (e.g. ubuntu), not root; it uses sudo." >&2; exit 1; }
grep -qi ubuntu /etc/os-release || { echo "This script expects Ubuntu." >&2; exit 1; }

say "System updates, automatic security updates, basic tools"
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq git curl ca-certificates openssl \
  unattended-upgrades iptables-persistent >/dev/null
sudo dpkg-reconfigure -f noninteractive unattended-upgrades

say "Swap file (headroom for building images on the server)"
if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
  sudo mkswap /swapfile >/dev/null && sudo swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

say "Firewall: open 80 and 443 on the VM itself"
# Oracle's Ubuntu images ship iptables rules that reject everything except SSH, IN ADDITION
# to the cloud console's security list, so both need ports 80/443 open. Insert the ACCEPT
# rules before the image's catch-all REJECT and persist them.
open_port() {  # proto port
  if ! sudo iptables -C INPUT -p "$1" --dport "$2" -m state --state NEW -j ACCEPT 2>/dev/null; then
    local at; at="$(sudo iptables -L INPUT --line-numbers | awk '/REJECT/ {print $1; exit}')"
    sudo iptables -I INPUT "${at:-1}" -p "$1" --dport "$2" -m state --state NEW -j ACCEPT
  fi
}
open_port tcp 80; open_port tcp 443; open_port udp 443
sudo netfilter-persistent save >/dev/null

say "Docker"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
fi
sudo usermod -aG docker "$ME"
docker_() { sudo docker "$@"; }   # group membership only applies to new logins

say "Read-only access to the GitHub repository (deploy key)"
mkdir -p ~/.ssh && chmod 700 ~/.ssh
if [ ! -f ~/.ssh/turnup_repo ]; then
  ssh-keygen -q -t ed25519 -N "" -C "turnup-server-$(hostname)" -f ~/.ssh/turnup_repo
fi
if ! grep -q "turnup_repo" ~/.ssh/config 2>/dev/null; then
  printf 'Host github.com\n  IdentityFile ~/.ssh/turnup_repo\n  IdentitiesOnly yes\n' >> ~/.ssh/config
  chmod 600 ~/.ssh/config
fi
ssh-keyscan -t ed25519 github.com 2>/dev/null >> ~/.ssh/known_hosts
sort -u -o ~/.ssh/known_hosts ~/.ssh/known_hosts
until git ls-remote --heads "$REPO" "$BRANCH" >/dev/null 2>&1; do
  echo
  echo "Add this key on GitHub: repository -> Settings -> Deploy keys -> Add deploy key"
  echo "(title: turnup server, leave 'Allow write access' UNCHECKED):"
  echo
  cat ~/.ssh/turnup_repo.pub
  echo
  ask "Press Enter once it's added... " >/dev/null
done

say "Code in $APP_DIR"
sudo mkdir -p "$APP_DIR" && sudo chown "$ME:$ME" "$APP_DIR"
if [ ! -d "$APP_DIR/.git" ]; then
  git clone --branch "$BRANCH" "$REPO" "$APP_DIR"
fi

say "Configuration ($APP_DIR/.env)"
if [ ! -f "$APP_DIR/.env" ]; then
  api_domain="$(ask 'API domain pointing at this server (e.g. api.turnup.example or turnup-api.duckdns.org): ')"
  website="$(ask 'Website address (e.g. https://turnup.vercel.app): ')"
  website="${website%/}"
  cat > "$APP_DIR/.env" <<ENV
# Turnup backend on this server. Edit, then run: $APP_DIR/deploy/oracle/deploy.sh
SECRET_KEY=$(openssl rand -hex 32)
POSTGRES_PASSWORD=$(openssl rand -hex 24)

# API only: the website is hosted elsewhere (Vercel)
COMPOSE_PROFILES=
WEB_MODE=redirect
SITE_ADDRESS=$api_domain
PUBLIC_BASE_URL=https://$api_domain
FRONTEND_URL=$website
# Pages allowed to call the API: the website, and the Android app (its origin is http://localhost)
ALLOWED_ORIGINS=$website,http://localhost
BACKUP_KEEP_DAYS=14

# Object storage and off-server backups (guide: deploy/oracle/README.md, "Storage and backups").
# Leave STORAGE_BACKEND=local until the bucket is set up.
STORAGE_BACKEND=local
S3_ENDPOINT_URL=
S3_ACCESS_KEY_ID=
S3_SECRET_ACCESS_KEY=
S3_BUCKET=
S3_PUBLIC_BASE_URL=
BACKUP_S3_BUCKET=
# Encrypts the off-server backups. SAVE IT IN A PASSWORD MANAGER: without it they can't be restored.
BACKUP_PASSPHRASE=$(openssl rand -base64 33 | tr -d '/+=' | cut -c1-40)

# Email: until SMTP is filled in, emails are printed to the logs (docker compose logs backend)
EMAIL_CONSOLE=true
SMTP_HOST=
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=noreply@turnup.app

# Payments (required for paid tickets)
PAYSTACK_SECRET_KEY=
PAYSTACK_PUBLIC_KEY=

# Optional
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=
ENV
  chmod 600 "$APP_DIR/.env"
  echo "Wrote $APP_DIR/.env (secrets generated). Add Paystack/SMTP keys there later."
  echo
  echo "IMPORTANT: copy this backup passphrase into a password manager now. Off-server backups"
  echo "can't be restored without it (it's also in $APP_DIR/.env):"
  grep '^BACKUP_PASSPHRASE=' "$APP_DIR/.env" | cut -d= -f2
fi

say "First start (builds images; takes a few minutes)"
cd "$APP_DIR" && docker_ compose up -d --build

say "Key for automatic deploys from GitHub Actions"
# This key can ONLY run deploy.sh: the forced command in authorized_keys ignores whatever
# the client asks to run, and forwarding/terminal access are disabled.
if [ ! -f ~/.ssh/turnup_actions ]; then
  ssh-keygen -q -t ed25519 -N "" -C "github-actions-deploy" -f ~/.ssh/turnup_actions
fi
line="command=\"$APP_DIR/deploy/oracle/deploy.sh\",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty $(cat ~/.ssh/turnup_actions.pub)"
touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys
grep -qF "$(cat ~/.ssh/turnup_actions.pub)" ~/.ssh/authorized_keys || echo "$line" >> ~/.ssh/authorized_keys

ip="$(curl -fsS https://api.ipify.org 2>/dev/null || hostname -I | awk '{print $1}')"
cat <<DONE

==========================================================================================
 Done. Last step: add these 4 secrets on GitHub (repository -> Settings -> Secrets and
 variables -> Actions -> New repository secret) to turn on automatic deploys:

 ORACLE_HOST         $ip
 ORACLE_USER         $ME
 ORACLE_KNOWN_HOSTS  (the line below, starting with $ip)
$(ssh-keyscan -t ed25519 localhost 2>/dev/null | sed "s/^localhost/$ip/")
 ORACLE_SSH_KEY      (everything below, including the BEGIN/END lines)
$(cat ~/.ssh/turnup_actions)

 Then check:  https://$(grep '^SITE_ADDRESS=' "$APP_DIR/.env" | cut -d= -f2)/api/health
 Demo data:   cd $APP_DIR && sudo docker compose run --rm migrate python -m app.cli seed
==========================================================================================
DONE
