# Private data uploads

Sign in, open **Your databases**, upload a CSV or SQLite `.db` file, and press **Import & explore**. A successful import activates the new database and opens the Data explorer. Use the sidebar **Active database** selector to switch back to Demo database or another import. Query, Data and Schema all follow that selection. Switching clears the current draft/result and resets pagination. The archive retains answers from all sources, with their dataset name; Open restores the associated source and saved answer.

Uploads and source lists are private to their account. The API verifies ownership for every schema, browse and query request. Files persist in the existing Docker cache volume under `/home/appuser/.cache/texttosql/datasets`; dataset ownership/schema metadata persists in PostgreSQL. Keep backups of both volumes together. Original user filenames are never used as storage paths. Uploads are snapshots, not live connections. User accounts share the existing demo database.

## CSV

UTF-8 (BOM accepted), with a header row. Comma, semicolon and tab separators are detected. Headers normalize to lowercase underscore names, and must stay unique after normalization. The imported table is **data**. Blank cells become NULL; surrounding spaces in values are preserved. Type inference checks the whole column. Mixed columns, leading-zero codes, dates and booleans stay text. Ordinary integers use INTEGER, decimal/scientific numbers use REAL (floating point, not exact financial decimal arithmetic). The schema response records original headers.

## SQLite

Upload a complete standalone `.db` file. Close your database, checkpoint WAL if applicable, and set `PRAGMA journal_mode=DELETE` before making the upload copy. WAL-mode files are rejected to avoid silently omitting changes in companion files. Ordinary tables are copied to a clean snapshot, retaining column names, primary keys and foreign-key relationship descriptions. Views, virtual tables, generated/hidden columns and binary BLOBs are unsupported. Executable defaults, triggers, indexes and custom collations/functions are not imported. Queries use SQLite syntax, and no demo business glossary is applied.

## Limits and safety

50 MB per upload and per resulting snapshot; 200,000 total records; 50 tables; 200 columns per table; 10 datasets and 200 MB total per account. SQLite import work has a 20-second deadline, individual values are limited to 1 MB, SQL execution uses the configured query timeout, queries retain the normal row limit, and uploaded-query results are capped at 8 MB. SQL remains SELECT-only with schema/function guardrails. Runtime SQLite connections are immutable, read-only, disable trusted schema, deny writes/attachments and cannot load extensions. SQLite uses time/resource bounds rather than PostgreSQL cost estimates.

Uploaded files remain on the AskDB server. Questions and schema descriptions go to the configured SQL model provider; uploaded records are not sent as prompt examples. SQLite snapshots are rebuilt rather than executing uploaded schema scripts. Back up original files separately. No upload delete/replace UI is provided in this version.
