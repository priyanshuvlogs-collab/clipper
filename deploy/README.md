# Deploying Pro Clipper to a VPS

One `docker compose` stack: **Caddy** (HTTPS + a password in front of everything) →
**web** (Next.js) and **api** (FastAPI + FFmpeg + Whisper).

## What you need

- A VPS running Ubuntu 22.04 or 24.04 with **at least 4 GB RAM and 2 vCPU**, and 40 GB+
  disk (source videos and renders are stored on it).
- A domain whose DNS you control.

## 1. Point the domain at the VPS

In your DNS zone, create two **A records** pointing to the VPS's IPv4 address:

| Type | Name | Value |
| --- | --- | --- |
| A | `@` | your VPS IP |
| A | `www` | your VPS IP |

Remove any older `A` / `AAAA` / parking records for `@` and `www`. Wait until
`ping yourdomain.com` answers from the VPS IP before step 4, or the HTTPS certificate
request will fail.

## 2. Prepare the server

```bash
ssh root@YOUR_VPS_IP
curl -fsSL https://get.docker.com | sh          # Docker + compose plugin
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw --force enable
```

## 3. Get the code and configure it

```bash
git clone https://github.com/priyanshuvlogs-collab/clipper.git /opt/clipper
cd /opt/clipper
cp deploy/.env.example deploy/.env

# Create the login password hash and copy the line it prints
docker run --rm caddy:2 caddy hash-password --plaintext 'choose-a-strong-password'

nano deploy/.env      # set DOMAIN, APP_USER, APP_PASSWORD_HASH (keep the single quotes)
```

For a private repository, clone with a GitHub personal access token or a deploy key.

## 4. Start it

```bash
docker compose up -d --build     # first build takes several minutes
docker compose logs -f caddy     # watch the certificate being issued, Ctrl+C to leave
```

Open `https://yourdomain.com`, sign in with `APP_USER` and your password, then add your
API keys under **AI settings**.

## Day to day

```bash
cd /opt/clipper
git pull && docker compose up -d --build   # update to the latest code
docker compose logs -f api                 # see processing / errors
docker compose restart                     # restart everything
docker system df                           # check disk used by images
```

Videos, the database and saved API keys live in the `data` volume. Back it up with:

```bash
docker run --rm -v clipper_data:/data -v "$PWD":/backup alpine \
  tar czf /backup/clipper-data.tgz -C /data .
```

## Good to know

- **Keep the password on.** The app itself has no login. Without the Caddy password,
  anyone who finds the site can spend your AI credits.
- **Transcription speed.** Whisper runs on the VPS CPU: roughly real-time on a small
  server with `WHISPER_MODEL=small`. Set `GROQ_API_KEY` in `deploy/.env` for much faster
  transcription, or use `WHISPER_MODEL=base`.
- **YouTube links** are often blocked from data-centre IPs. If a link fails, upload the
  file instead.
- **Disk fills up** over time: delete old videos from the dashboard.
