# Deploying radarr-janitor on docker01

## CLI + quarterly cron

```bash
cd /home/artagel/radarr-genre-filter
python3 -m venv .venv && ./.venv/bin/pip install -e .
cp .env.example .env   # fill in keys
```

Quarterly Telegram report (crontab -e as artagel):

```
0 9 1 1,4,7,10 * /home/artagel/radarr-genre-filter/deploy/quarterly-report.sh >> /home/artagel/radarr-genre-filter/quarterly.log 2>&1
```

## Web UI container

Add this service to `/root/compose.yaml` (shares the compose network so it can reach `radarr` by name; the port is published only to localhost so it is reachable by the host's `cloudflared`, never directly from the LAN/internet):

```yaml
  radarr-janitor-web:
    build: /home/artagel/radarr-genre-filter
    container_name: radarr-janitor-web
    environment:
      - RADARR_URL=http://radarr:7878
      - RADARR_API_KEY=${RADARR_API_KEY}
      - OMDB_API_KEY=${OMDB_API_KEY}
      - TMDB_API_KEY=${TMDB_API_KEY}
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID}
      - JANITOR_DB=/data/janitor.db
    volumes:
      - /home/artagel/radarr-genre-filter/data:/data
    ports:
      - "127.0.0.1:5056:5056"
    restart: unless-stopped
```

Put the env values in `/root/.env` (compose reads it) or inline them. Then:

```bash
docker compose up -d --build radarr-janitor-web
```

## Cloudflare (janitor.dangericke.com)

The `cloudflare-tunnel` container uses a token-managed tunnel, so add the route in the
Cloudflare **Zero Trust dashboard**:

1. **Networks → Tunnels →** your tunnel **→ Public Hostname → Add**:
   - Subdomain `janitor`, domain `dangericke.com`
   - Service: `HTTP` → `http://localhost:5056`
2. **Access → Applications → Add** a self-hosted app for `janitor.dangericke.com` with a
   policy that allows only your email. This is the only auth in front of a delete-capable UI, so keep it on.
