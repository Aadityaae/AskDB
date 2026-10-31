# Security and private configuration

AskDB targets a local Docker deployment. Keep host ports bound to `127.0.0.1`
unless you have reviewed the requirements for public hosting.

- Create your own `.env` from `.env.example`. Never commit real API keys, passwords,
  bearer tokens, `.streamlit/secrets.toml`, private databases, or recordings.
- Ignore rules prevent common accidental additions but are not a secret vault.
  Check staged changes before committing. Never force-add private files.
- If a secret is published, revoke/rotate it immediately. Removing it in a later
  commit does not remove it from Git history.
- Public hosting needs HTTPS, trusted proxy settings, request/connection timeouts,
  distributed per-account quotas, monitoring, backups, and reviewed frontend
  policies. Email verification, MFA and account recovery are not implemented.
- Keep SQL validation, account ownership checks, read-only roles, timeouts, and
  result limits enabled. Generated SQL is untrusted.
- Speech transcription is local. Questions and schema context are sent to the
  configured SQL model provider; understand that privacy boundary.

Do not put credentials or private data in public issues. Report security-sensitive
details privately to the repository owner.

The [31 October 2026 audit](docs/audits/2026-10-31/report.md) documents fixes, test
coverage, dependency-scan exclusions, and remaining limitations. It is not a
guarantee against compromise or a production security certification.
