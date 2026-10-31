# AskDB

Full hosting setup: [Deploy the complete app](docs/DEPLOYMENT.md).

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

## Run locally

Install Docker Desktop with Docker Compose and Git. A Groq API key is needed for
natural-language SQL generation. Ollama is optional and not required by default.

In PowerShell:

```powershell
git clone https://github.com/Aadityaae/AskDB.git
cd AskDB
Copy-Item .env.example .env
```

Edit your local `.env`:

1. Choose three different strong, URL-safe passwords for `POSTGRES_PASSWORD`,
   `METADATA_PASSWORD`, and `READONLY_PASSWORD`.
2. Set `GROQ_API_KEY` to your own key.
3. Keep `LLM_PROVIDER=groq` and `GROQ_MODEL=openai/gpt-oss-120b` unless deliberately
   selecting another supported configuration.

Compose constructs its internal database URLs from the passwords. The localhost
URL examples are for running Python directly outside Docker.

```powershell
docker compose up --build -d
docker compose exec api python -m scripts.download_embeddings
docker compose exec api python -m scripts.download_speech_model
```

Open **http://localhost:8000/landing/** and choose **Get Started** or **Sign in**.
The workspace uses port **8501**, the API **8000**, and PostgreSQL **5432**. Host
ports bind to `127.0.0.1`.

The first question may take longer while local schema embeddings load. Strict
validation can make up to three model calls per question. Groq quotas and internet
availability affect response times. There is no automatic paid fallback.

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

This is a local development project, not a turnkey public hosting configuration.
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
