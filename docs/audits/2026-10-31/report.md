# AskDB application and security audit

Date: 31 October 2026 (Asia/Calcutta). Scope: the running local Docker deployment, FastAPI backend, Streamlit frontend, PostgreSQL roles, CSV/SQLite imports, local speech path, and installed Python dependencies.

## Outcome

Confirmed issues were fixed and deployed. The final automated suite passed **131 tests with live PostgreSQL checks enabled and no skipped tests**. A separate fresh-account audit passed **36 checks** using actual signup/login, PostgreSQL, private CSV/SQLite snapshots, Groq responses, and local speech inference. Temporary audit accounts, imported files, query records, feedback, and traversal canaries were removed.

This is an application audit with bounded functional/security testing, not a guarantee against compromise or a certification for public hosting. The remaining coverage limits and deployment requirements are listed below.

## Confirmed findings and changes

| Area | Finding | Change and verification |
| --- | --- | --- |
| Upload resource limits | Only database uploads had a total request-body limit. Voice multipart bodies could spool before their WAV bytes were checked. JSON bodies also lacked an application-wide byte bound. | Enforced total bodies, including chunked bodies: dataset multipart 50 MiB plus 1 MiB overhead; voice 6 MiB plus 64 KiB overhead; other POST/PUT/PATCH requests 128 KiB. Oversized requests return 413. Regression tests cover header and chunked-body limits. |
| Authentication before uploads | FastAPI file parameters caused multipart parsing before the authentication dependency finished. | Database and speech handlers now authenticate before calling the bounded form parser. Unauthenticated streamed multipart tests return 401 without consuming the body. Files/fields are explicitly limited and parsing/spool resources are closed. OpenAPI file-upload descriptions were retained. |
| Concurrent login attempts | Authentication limits used count-then-insert without serializing concurrent transactions. | PostgreSQL transaction-level advisory locks serialize the affected IP/email buckets. Twenty simultaneous real login attempts against a fresh audit address produced exactly ten 401 responses and ten 429 responses. |
| Password storage | Existing scrypt derivations used a lower work factor than the selected OWASP baseline. | New hashes use versioned scrypt N=16384, r=8, p=5, using approximately 16 MiB per derivation. At most four derivations run simultaneously. Old hashes still verify, use comparable verification effort, and upgrade after a successful login. Regression tests verify compatibility, migration, and wrong-password rejection. No existing user's password was changed. |
| Result memory/size | The 8 MiB result check applied only to SQLite. PostgreSQL fetched results without that byte check. | Applied the byte cap to both engines and enabled streaming result fetching with a bounded buffer. A real PostgreSQL query exceeding 8 MiB is rejected. Existing SQL timeouts, plan checks, row caps and read-only roles remain active. |
| Expensive work queues | Authenticated callers could queue repeated speech inferences and many simultaneous model queries. | Voice inference fails cleanly with a busy response instead of queueing behind another inference. Query execution has a four-job per-process capacity limit and returns 429 with Retry-After when full. These are concurrency bounds, not distributed per-user quotas. |
| Frontend transport | Streamlit transport defaults allowed larger uploads/messages than this application needs. Polling file watchers are unnecessary in the baked Docker image. | Explicitly retained CORS/XSRF protection, capped frontend uploads at 50 MiB and WebSocket messages at 16 MiB, and disabled source-file polling. The message cap accommodates the existing 8 MiB result bound and bounded voice events; CSV/SQLite files use the upload transport. |
| CSV exports | Text cells or column labels beginning with spreadsheet formula characters were exported unchanged. | Both export paths now prefix formula-like text, including leading whitespace/control characters and normalized full-width variants. Numeric negative values remain numeric, and original records are unchanged. Regression tests verify exported cells and headers. Spreadsheet programs differ; see the remaining CSV limitation below. |
| Logs and browser caching | Blocked-query logs included raw SQL, which could contain sensitive literals. Private API responses lacked explicit no-store headers. | Removed raw SQL/session values from blocked-query logs. API responses now include no-store/no-cache, MIME sniffing protection, frame restrictions, and a restrictive JSON-response CSP. These API headers do not constitute a full frontend CSP deployment. |
| Dependencies | The initial scanner reported advisory entries in certifi, filelock, Pillow and setuptools. Some advisory identifiers were duplicated, so the raw entry count should not be interpreted as unique exploitable application flaws. | Updated certifi to 2026.10.23, filelock to 4.2.6, Pillow to 13.0.0, and setuptools to 84.2.1. Streamlit was updated to 1.66.1 for declared Pillow 13 compatibility. `pip check` passes. Requirements now express the tested secure minimums. |

Password configuration follows an available memory-conscious option in the [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html). Multipart limits address the resource-consumption concerns described in [Starlette's request documentation](https://starlette.dev/requests/). Read-only SQL remains defense in depth alongside validation, consistent with [PostgreSQL's transaction documentation](https://www.postgresql.org/docs/current/sql-set-transaction.html).

## Fresh dataset correctness checks

The new CSV contained six fabricated orders, regions, statuses, amounts, nulls, and a formula-like text value. The SQLite database contained three departments and seven employees with declared relationships.

| Real natural-language request | Expected | Actual | Status shown by AskDB |
| --- | --- | --- | --- |
| Total amount of completed orders in the uploaded CSV | 500.00 | 500.00 | Needs review / low confidence |
| Employees in the Sales department in the uploaded SQLite database | 3 | 3 | Success |
| Number of records in the uploaded CSV table | 6 | 6 | Success |

All three answers were produced using the configured real Groq model, not a mocked SQL generator. The first was submitted through the Streamlit question editor. Its low-confidence warning was preserved: correct arithmetic in this fixture does not establish universal semantic correctness. The first cold question took about 37 seconds, including local schema relevance/model initialization and strict multi-call validation; the subsequent requests took about 5.3 and 4.6 seconds. No confidence thresholds were relaxed for the audit.

## Functional and security coverage

- UI signup, duplicate signup, invalid email, incorrect password, forged token, logout revocation, and signing back into the same persistent account.
- Password/session database storage checks: salted password hashes and hashed opaque session tokens, rather than raw credentials.
- New CSV and relational SQLite uploads; private source lists, schema inspection, table preview, source switching, and persistence after logging back in.
- Account isolation: a second real account could not read the first account's schema, browse records, query its private uploads, open its saved query, or submit feedback for that query.
- All six workspace destinations in both themes; default dark mode, current-tab deselection handling, date filtering, pagination, saved-query reopening, clarification restoration, feedback selection, SQL editor refresh, and chart modes.
- Read-only PostgreSQL role privileges and transaction enforcement, output caps, duplicate-column handling, non-finite values, SQLite authorizers/timeouts, unsafe function and system-table rejection, malformed files, quotas, and upload rollback behavior.
- Actual API rejection of DELETE, stacked statements, SQLite system-table reads, extension loading and database attachment attempts. No destructive statement was allowed to run.
- Encoded path-traversal probes using harmless canary files outside each static root. The frontend returned 400 and the API static mount returned 404; neither disclosed the canary. Canary files were removed.
- Real local speech transcription of an encoded 3.6-second synthetic question, with the expected Sales-department transcript. The endpoint returned transcript metadata and no SQL; voice did not submit a query.
- Voice timing was 3.8 seconds during concurrent audit load and 1.29 seconds in a separate timing check. These are sample timings, not latency guarantees.
- JavaScript runtime mock checks for first-click voice capture, Stop, partial-buffer flushing, 16 kHz WAV encoding, permission denial, cleanup on navigation, the 60-second limit and single upload; keyboard shortcut safeguards; landing menu/dialog/reduced-motion behavior. Navigation animation geometry and cleanup were checked during implementation.

## Dependency results

The post-update [pip-audit](https://github.com/pypa/pip-audit) result enumerated **92 distributions**: no known advisories were reported for the **91 auditable distributions**. The CPU wheel `torch==2.14.1+cpu` was skipped because the scanner could not match that distribution on PyPI. It must not be described as a clean scan of every installed component.

The CPU wheel was retained to avoid installing a CUDA distribution on this laptop. The app accepts CSV, SQLite and WAV input, not arbitrary PyTorch checkpoints. This limits exposure to model-loading attacks but is not a substitute for auditing that wheel. The [upstream PyTorch security advisories](https://github.com/pytorch/pytorch/security/advisories) remain relevant to ongoing maintenance.

Raw post-update output: [dependency-results.json](dependency-results.json). Fresh-account outcomes, generated SQL and synthetic results: [end-to-end-results.json](end-to-end-results.json). These files contain no API keys, passwords or bearer tokens.

## Remaining limits and requirements

1. **Local deployment scope.** Docker ports remain bound to 127.0.0.1. Before internet deployment, add HTTPS, trusted proxy configuration, edge upload/connection timeouts, distributed per-account quotas, monitoring, backups, and a reviewed frontend CSP. Current query capacity is per API process. Do not expose the database port publicly.
2. **Authentication lifecycle.** Email verification, MFA, password recovery and compromised-password screening are not implemented. Registration is therefore appropriate for the current local project, not a claim of enterprise identity verification. IP-based authentication limits see the frontend server's IP when it forwards account requests; this needs deliberate proxy/client identity design for a public multi-user service.
3. **Browser/hardware scope.** Streamlit AppTest exercises UI state and real API calls, but does not render pixels or measure 60fps. No live-browser visual, cross-browser accessibility, or physical microphone/permission-prompt test was completed in this run. The real speech backend and synthetic browser-capture lifecycle were tested separately.
4. **Scanner scope.** The CPU PyTorch wheel, Windows host, Docker daemon, operating-system packages, external Groq infrastructure, and unknown/unpublished vulnerabilities are outside the clean dependency result. This was not an unrestricted penetration test or sustained denial-of-service load test.
5. **AI correctness.** Three fresh-data questions matched known results; this does not prove all possible questions. Prompt injection and hallucinations remain reasons to retain SQL validation, account ownership checks, read-only execution and visible confidence warnings.
6. **CSV semantics.** Prefixing formula-like strings reduces risk on initial spreadsheet import and intentionally changes those exported text cells. Excel and other programs may reinterpret cells after editing/saving/reopening. There is no universal CSV sanitization strategy for every consumer; this is documented by [OWASP's CSV injection guidance](https://github.com/OWASP/www-community/blob/master/pages/attacks/CSV_Injection.md). Stored source values and displayed results are not changed.
7. **Availability and privacy.** Groq quotas, internet outages, local memory pressure and a recording submitted before speech warmup completes can still affect response times. Queries and schema descriptions use the configured model provider; speech remains local. The audit did not change that data flow.

## Repeating the regression checks

With Docker Desktop and the project services running, run from D:\TextToSQL:

```powershell
docker compose exec -T -e PYTHONPATH=/workspace -e RUN_LIVE_TESTS=1 api python -m pytest -q
docker compose exec -T api python -m pip check
```

Final result: `131 passed in 65.38s`. The initial expanded run exposed one test-order dependency: an unavailable-schema test assumed the previous test's missing-database configuration was still cached. The test now explicitly simulates schema unavailability, and configuration caches are reset between tests. This was a test-fixture correction, not suppression of an application failure.

Local audit harnesses and fixture recordings are retained under `.cache` for inspection. They are excluded from Docker build contexts. Existing user accounts and datasets were not deleted or reset. The patched application remains running.
