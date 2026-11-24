#!/usr/bin/env bash
# One-shot installer for a fresh Ubuntu VPS. Run as root:
#
#   bash <(curl -fsSL https://raw.githubusercontent.com/priyanshuvlogs-collab/clipper/main/deploy/install.sh)
#
# Optional environment: DOMAIN, APP_USER, BRANCH, APP_DIR.
# Safe to run again: it updates the code and rebuilds, keeping your settings and data.
set -euo pipefail

REPO_URL="https://github.com/priyanshuvlogs-collab/clipper.git"
BRANCH="${BRANCH:-main}"
APP_DIR="${APP_DIR:-/opt/clipper}"
DOMAIN="${DOMAIN:-clipforge.com}"
APP_USER="${APP_USER:-admin}"

say() { printf '\n\033[1;35m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mError: %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Run this as root (or with sudo)."
[ -r /dev/tty ] || die "No terminal available to ask for a password. Run it from an SSH session."

say "1/6 Installing Docker and git"
export DEBIAN_FRONTEND=noninteractive
if ! command -v git >/dev/null 2>&1 || ! command -v curl >/dev/null 2>&1; then
  apt-get update -qq && apt-get install -y -qq git curl ca-certificates
fi
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi
docker compose version >/dev/null 2>&1 || die "Docker is installed but 'docker compose' is missing."
systemctl enable --now docker >/dev/null 2>&1 || true

say "2/6 Opening the firewall for SSH and the website"
if command -v ufw >/dev/null 2>&1; then
  ufw allow OpenSSH >/dev/null
  ufw allow 80 >/dev/null
  ufw allow 443 >/dev/null
  ufw --force enable >/dev/null
fi

say "3/6 Getting the code ($BRANCH)"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch --quiet origin "$BRANCH"
  git -C "$APP_DIR" checkout --quiet -B "$BRANCH" FETCH_HEAD
else
  git clone --quiet -b "$BRANCH" "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

say "4/6 Settings"
ENV_FILE="deploy/.env"
if [ -f "$ENV_FILE" ] && ! grep -q "paste-the-hash-here" "$ENV_FILE"; then
  echo "Keeping the existing $APP_DIR/$ENV_FILE (delete it and re-run to start over)."
  DOMAIN="$(grep -E '^DOMAIN=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
else
  while :; do
    printf 'Choose a password for the site (login name: %s): ' "$APP_USER" > /dev/tty
    IFS= read -rs PW < /dev/tty; echo > /dev/tty
    printf 'Type it again: ' > /dev/tty
    IFS= read -rs PW2 < /dev/tty; echo > /dev/tty
    if [ "$PW" != "$PW2" ]; then echo "They did not match, try again." > /dev/tty; continue; fi
    if [ "${#PW}" -lt 8 ]; then echo "Use at least 8 characters." > /dev/tty; continue; fi
    break
  done
  HASH="$(printf '%s\n' "$PW" | docker run --rm -i caddy:2 caddy hash-password)"
  unset PW PW2
  case "$HASH" in '$2'*) ;; *) die "Could not create the password hash." ;; esac
  umask 077
  cat > "$ENV_FILE" <<ENV
DOMAIN=$DOMAIN
APP_USER=$APP_USER
APP_PASSWORD_HASH='$HASH'
WHISPER_MODEL=small
ENV
  echo "Wrote $APP_DIR/$ENV_FILE"
fi

say "5/6 Checking that $DOMAIN points at this server"
MY_IP="$(curl -4 -fsS --max-time 8 https://api.ipify.org || true)"
DNS_IP="$(getent ahostsv4 "$DOMAIN" | awk 'NR==1{print $1}' || true)"
if [ -n "$MY_IP" ] && [ "$MY_IP" = "$DNS_IP" ]; then
  echo "OK: $DOMAIN -> $MY_IP"
else
  echo "WARNING: $DOMAIN currently points to '${DNS_IP:-nothing}', but this server is ${MY_IP:-unknown}."
  echo "In your DNS zone, set A records for @ and www to ${MY_IP:-this server's IP}."
  echo "The app will start anyway; HTTPS begins working a few minutes after DNS is correct."
fi

say "6/6 Building and starting (the first build takes several minutes)"
docker compose up -d --build

say "Done"
docker compose ps
cat <<MSG

Open:      https://$DOMAIN
Login:     $APP_USER  +  the password you just chose
Then:      add your API keys under "AI settings" in the app

Logs:      cd $APP_DIR && docker compose logs -f
Update:    run this installer again
MSG
