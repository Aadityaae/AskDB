# Full AskDB deployment

This deploys the existing landing page, Streamlit workspace, FastAPI, PostgreSQL, speech and embedding models, and persistent uploads together on one Linux server. Vercel is not required. A hosting account, server and domain are still needed; these files do not purchase or provision them.

## Server

For a small demo, start with Ubuntu 24.04 x86-64, 2+ vCPUs, 8 GB RAM and 40+ GB disk. These are initial estimates, not load-tested capacity guarantees. Install Docker Engine and the Compose plugin using [Docker's Ubuntu instructions](https://docs.docker.com/engine/install/ubuntu/).

Allow inbound TCP 80/443, optional UDP 443, and SSH from your administrative IP. Do not expose 5432, 8000 or 8501. Point a domain A record to the server IPv4; add AAAA only if IPv6 works. [Caddy obtains HTTPS automatically](https://caddyserver.com/docs/automatic-https) when DNS and ports are reachable.

## Deploy

Run on the server:

```sh
git clone https://github.com/Aadityaae/AskDB.git
cd AskDB
umask 077
cp deploy/production.env.example .env.production
nano .env.production
```

Set APP_DOMAIN to the hostname only, GROQ_API_KEY to your key, and three different long URL-safe passwords. Generate each password with `openssl rand -hex 24`. Never commit the completed environment file.

```sh
docker compose --env-file .env.production -f docker-compose.production.yml up --build -d
docker compose --env-file .env.production -f docker-compose.production.yml ps -a
docker compose --env-file .env.production -f docker-compose.production.yml logs --tail=80 models api frontend proxy
```

First build/model downloads take several minutes. The models job must finish with exit code 0 before the API starts. Its cache persists. If downloading fails, inspect logs and retry. Use this standalone Compose file; do not combine it with the local one.

Open `https://YOUR_DOMAIN/`. Sign in and Get Started open the workspace under `/workspace/`. Bare workspace visits return to the landing page. HTTPS and browser permission are required for the microphone.

This creates fresh production databases. Laptop users, history and uploads are not automatically migrated. Local speech runs on the server; questions/schema context go to Groq. External video/fonts still depend on their upstream services.

## Verify before sharing

- Register, sign out and sign back in.
- Check Status: databases, schema and Groq connected.
- Ask a demo question; inspect SQL and charts.
- Upload CSV and SQLite files, browse records and query each.
- Check archive dates, feedback, navigation, both themes and mobile layout.
- Record/stop voice, check transcription and submit.
- Verify a second account cannot see another account's uploads/history.
- Restart services and confirm accounts, history and uploads survive.

## Maintain

Update with `git pull --ff-only`, then repeat the deployment command. Back up PostgreSQL and the app_cache volume (contains user uploads) before updates. Keep encrypted backups outside the server and test restores. Stop frontend/api while taking coordinated database/upload backups. Save the environment file separately in a password manager.

Never run `down -v`: it deletes persistent volumes. Editing environment passwords alone does not change passwords in an existing PostgreSQL volume. Continue applying OS/container patches and monitoring API quotas and disk usage.

This configuration has not yet been verified on a public server. Local tests do not establish public availability, server capacity, or immunity to attacks.
