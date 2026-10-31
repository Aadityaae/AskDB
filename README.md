# AskDB

**Your data. Just ask.**

Upload a CSV or SQLite database, ask questions in plain English or by voice, and
explore the results as tables and charts. Inspect the generated SQL, review its
validation evidence, and revisit previous questions in your personal archive.

## Features

- Private CSV/SQLite uploads, plus an included synthetic demo database.
- Natural-language SQL generation through Groq's GPT-OSS 120B model.
- One-button Start/Stop voice capture with local English transcription.
- Table browsing, schema inspection, charts, guarded SQL editing, and CSV exports.
- Account-based query history, date filters, and feedback.
- Dark/light modes, keyboard shortcuts, responsive layouts, and reduced-motion support.

## Tech stack

| Technology | Purpose |
| --- | --- |
| Python / FastAPI | API, authentication, uploads, query pipeline |
| Streamlit / JavaScript / CSS | Workspace, charts, voice capture, responsive UI |
| Groq / GPT-OSS 120B | SQL generation and model-based validation |
| PostgreSQL / SQLAlchemy | Demo data, accounts, sessions, history, feedback |
| SQLite / pandas | Private snapshots and CSV processing |
| SQLGlot / SQLParse | SQL parsing, schema resolution, safety checks |
| Sentence Transformers / MiniLM | Relevant schema retrieval |
| Faster-Whisper (`tiny.en`) | Local speech transcription |
| Docker Compose / pytest | Services and regression testing |

## Run locally — step by step

AskDB currently runs locally. Clone this repository to try the complete app;
there is no hosted demo to sign into. You do not need a hosting account or domain.

### 1. Install the prerequisites

- [Git](https://git-scm.com/downloads).
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) with Docker
  Compose. Open it and wait for the Docker engine to start. On Windows, use Linux
  containers and complete Docker's WSL 2 setup if prompted.
- Your own [Groq API key](https://console.groq.com/keys) for generating SQL.

Docker installs Python and the project dependencies inside the containers. You
do **not** need to install Ollama, PostgreSQL, Python, or activate a virtual
environment separately. Allow disk space for Docker images and the small local
speech/embedding models. Internet access is needed for setup and Groq queries.

### 2. Clone the repository

Open a terminal (the VS Code terminal works too):

```powershell
git clone https://github.com/Aadityaae/AskDB.git
cd AskDB
```

### 3. Create your local configuration

On Windows, in PowerShell:

```powershell
Copy-Item .env.example .env
```

On macOS/Linux:

```sh
cp .env.example .env
```

Open `.env` in your editor. Set these values:

```dotenv
POSTGRES_PASSWORD=choose_your_own_admin_password
METADATA_PASSWORD=choose_your_own_metadata_password
READONLY_PASSWORD=choose_your_own_readonly_password
LLM_PROVIDER=groq
GROQ_API_KEY=paste_your_own_groq_api_key_here
GROQ_MODEL=openai/gpt-oss-120b
```

**Replace the example passwords and key above.** Choose three different long
passwords using letters, numbers, `_` and `-` so they work safely in database URLs.
You create these passwords yourself; they are not credentials you need to obtain
from another service. Keep the remaining defaults for your first run.

Compose constructs its internal database URLs from these passwords. The
`DATABASE_URL` and `READONLY_DATABASE_URL` entries in `.env` are only needed when
running Python outside Docker, so you can leave their examples unchanged here.
Never upload your `.env` or share your API key; `.env` is ignored by Git.

### 4. Start the services

Run from the cloned `AskDB` folder:

```powershell
docker compose up --build -d
docker compose ps
```

The first build downloads dependencies and can take several minutes. PostgreSQL
should become healthy and both `api` and `frontend` should be running before the
next step. The bundled synthetic business database is initialized automatically.

### 5. Download the local embedding and speech models

These are one-time downloads stored in a Docker volume:

```powershell
docker compose exec api python -m scripts.download_embeddings
docker compose exec api python -m scripts.download_speech_model
docker compose restart api
```

The restart lets the API warm up the downloaded voice model. No local large
language model is required: SQL generation uses Groq.

### 6. Open AskDB and try it

Open **[http://localhost:8000/landing/](http://localhost:8000/landing/)**.

1. Choose **Get Started** and create a local account with your email and a
   password of at least 10 characters. Use **Sign in** on later visits.
2. Open **Status** and check the database, schema, and SQL-model connections.
3. In **Ask**, select the demo database and try: **“How many completed orders are
   there?”** Review the generated SQL and results.
4. In **Databases**, upload a CSV or SQLite `.db` file. Select it in **Ask** and
   ask questions using its actual column names.
5. Try **Use your voice**, allow microphone access, speak, and stop recording.
   Review the transcription before submitting your question.

Accounts are created inside your local installation; they are separate from your
GitHub/Groq account. The workspace uses port **8501**, the API **8000**, and
PostgreSQL **5432**. Host ports bind to `127.0.0.1`.

The first question may take longer while local schema embeddings load. Strict
validation can make up to three model calls per question. Groq quotas and internet
availability affect response times. There is no automatic paid fallback.

### 7. Stop and start again

```powershell
docker compose stop
```

Next time, open Docker Desktop, open a terminal in the `AskDB` folder, and run:

```powershell
docker compose up -d
```

Then open the landing-page URL again. You do not need to repeat the downloads.
Accounts, history, uploads, and models remain in Docker volumes.

### Troubleshooting

| Problem | What to check |
| --- | --- |
| Docker engine cannot be reached | Open Docker Desktop and wait for it to start; run `docker info`. |
| `service "api" is not running` | Run `docker compose ps -a`, then `docker compose logs --tail=80 api postgres`. Fix the reported error before downloading models. |
| Port is already allocated | Another app is using 5432, 8000, or 8501. Stop that conflicting service and rerun `docker compose up -d`. |
| SQL model is unavailable | Check your own `GROQ_API_KEY`, internet connection, and Groq quota; after editing `.env`, run `docker compose up -d --force-recreate api`. |
| Voice model is unavailable | Repeat the speech download command, then `docker compose restart api`; allow browser microphone permission. |
| Database authentication fails after changing passwords | Existing volumes keep the original database passwords. Changing `.env` alone does not update them; restore the original configuration or deliberately rotate the database passwords. |

Keep API keys and passwords out of screenshots and logs you share. Avoid deleting
volumes to fix a startup error: that would also delete saved data.

## Voice and uploads

Select **Use your voice**, allow microphone access, speak, then select
**Stop recording**. Review the draft and press **Search** when ready. Recording
never executes SQL automatically. Browser microphone access requires localhost or
HTTPS. Speech processing stays local and uses CPU/int8 inference.

Uploads support CSV and standalone SQLite databases containing ordinary tables:
50 MB per file, 200,000 total records, 50 tables, and 200 columns. Each account
supports up to 10 snapshots / 200 MB. See [upload details](docs/DATA_UPLOADS.md).

Uploaded rows and database execution remain on the local server. Questions,
relevant schema descriptions, examples, and generated SQL are sent to the
configured model provider. Understand that data flow before using sensitive data.

## Tests and security

```powershell
docker compose exec -T -e PYTHONPATH=/workspace -e RUN_LIVE_TESTS=1 api python -m pytest -q
docker compose exec -T api python -m pip check
```

The 31 October 2026 audit passed **131 automated tests** and **36 separate
fresh-account checks**, including real Groq queries against fabricated CSV/SQLite
data. Read the [audit report](docs/audits/2026-10-31/report.md) for findings, fixes,
evidence, and coverage limits.

Safeguards include private account-scoped data, scrypt password hashes, hashed
session tokens, authentication before file parsing, bounded requests/results, SQL
allowlisting, read-only transactions, timeouts, and concurrency limits. They reduce
risk; they do not guarantee correct AI answers or make the app unhackable.

This project is intended for local development and demos. An optional
[server deployment guide](docs/DEPLOYMENT.md) is available for future hosting.
See [SECURITY.md](SECURITY.md) before deployment. Keep credentials, real databases,
and recordings out of Git; `.env.example` contains placeholders only.

## Useful commands

```powershell
docker compose ps
docker compose logs -f api frontend
docker compose stop
```

Docker volumes retain database records, uploaded snapshots, and downloaded models.
Do not use `docker compose down -v` unless you intend to delete that persisted data.
No virtual-environment activation is needed when using Docker.

## Project layout

```text
app/          API, authentication, imports, SQL pipeline, safeguards
frontend/     Landing page, accounts, workspace, browser components
database/     PostgreSQL initialization and synthetic seed data
config/       Demo glossary and few-shot SQL examples
docker/       Application image definition
scripts/      Explicit local model downloads
tests/        Regression and opt-in live database checks
docs/         Setup details and security audit evidence
```

[AskDB promotional poster](docs/assets/askdb-poster.png)

Bundled fonts retain their upstream license files. Runtime credentials, private
uploads, recordings, caches, and local generated output are excluded from Git.
