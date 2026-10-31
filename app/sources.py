"""Private, bounded imports. Queries only use rebuilt read-only SQLite snapshots."""
import csv
import io
import math
import re
import sqlite3
import tempfile
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.datastructures import UploadFile
from starlette.concurrency import run_in_threadpool
from sqlalchemy import create_engine, select
from sqlalchemy.pool import NullPool
from app.auth import require_user
from app.config import settings
from app.db import Dataset, metadata_session, User

router = APIRouter(prefix='/v1/sources', tags=['data sources'])
current_source = ContextVar('data_source', default=None)
MAX_BYTES = 50 * 1024 * 1024
MAX_ROWS = 200000
MAX_TABLES = 50
MAX_COLUMNS = 200
MAX_SOURCES = 10
MAX_STORAGE = 200 * 1024 * 1024


def dialect():
    return 'sqlite' if current_source.get() else 'postgres'


def source_info():
    source = current_source.get()
    return {'source_id': source['id'], 'source_name': source['name']} if source else {'source_id': 'demo', 'source_name': 'Demo database'}


def root():
    path = Path(settings().dataset_dir).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def identifier(name):
    return '"' + name.replace('"', '""') + '"'


def read_connection(path):
    conn = sqlite3.connect(path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
    conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1024 * 1024)
    conn.execute('PRAGMA trusted_schema=OFF')
    conn.execute('PRAGMA query_only=ON')
    deadline = monotonic() + settings().max_query_seconds
    conn.set_progress_handler(lambda: int(monotonic() > deadline), 1000)
    # No extension loading, attachments, schema changes, or writes, even if SQL validation regresses.
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
    conn.set_authorizer(lambda action, a, b, db, trigger: sqlite3.SQLITE_OK if action in allowed or (action == sqlite3.SQLITE_PRAGMA and a == 'read_uncommitted' and b is None) else sqlite3.SQLITE_DENY)
    return conn


@contextmanager
def use_source(source_id, user):
    if source_id == 'demo':
        token = current_source.set(None)
        try:
            yield
        finally:
            current_source.reset(token)
        return
    with metadata_session() as db:
        record = db.get(Dataset, source_id)
        if not record or record.user_id != user['id']:
            raise HTTPException(404, 'Data source not found.')
        path = root() / (record.id + '.db')
        if not path.is_file():
            raise HTTPException(503, 'The uploaded database file is unavailable.')
        engine = create_engine('sqlite://', creator=lambda: read_connection(path), poolclass=NullPool)
        source = {'id': record.id, 'name': record.name, 'engine': engine, 'schema': record.tables}
    token = current_source.set(source)
    try:
        yield
    finally:
        current_source.reset(token)
        engine.dispose()


def describe(record):
    return {'id': record.id, 'name': record.name, 'kind': record.kind, 'size_bytes': record.size_bytes,
            'table_count': len(record.tables), 'created_at': record.created_at.isoformat()}


@router.get('')
def list_sources(user=Depends(require_user)):
    with metadata_session() as db:
        records = db.scalars(select(Dataset).where(Dataset.user_id == user['id']).order_by(Dataset.created_at.desc())).all()
        return {'items': [{'id': 'demo', 'name': 'Demo database', 'kind': 'demo', 'table_count': None}, *map(describe, records)]}


def csv_import(data, conn):
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise ValueError('Save your CSV as UTF-8 and upload it again.') from None
    csv.field_size_limit(1024 * 1024)
    try:
        delimiter = csv.Sniffer().sniff(text[:8192], delimiters=',;\t').delimiter
    except csv.Error:
        delimiter = ','
    reader = csv.reader(io.StringIO(text, newline=''), delimiter=delimiter, strict=True)
    headers = next(reader, None)
    if not headers or len(headers) > MAX_COLUMNS:
        raise ValueError('CSV needs a header row with 1–200 columns.')
    names = [re.sub(r'[^a-zA-Z0-9_]+', '_', h.strip()).strip('_').lower() for h in headers]
    if any(not n or len(n) > 128 for n in names) or len(set(names)) != len(names):
        raise ValueError('CSV headers must be nonempty and unique after spaces/punctuation become underscores.')
    kinds = ['INTEGER'] * len(names)
    count = 0
    for row in reader:
        if not row:
            continue
        count += 1
        if count > MAX_ROWS or len(row) != len(names):
            raise ValueError('CSV has mismatched row widths or exceeds 200,000 records.')
        for i, value in enumerate(row):
            if value == '':
                continue
            if re.fullmatch(r'-?(0|[1-9][0-9]*)', value) and -(2**63) <= int(value) < 2**63:
                continue
            if re.fullmatch(r'-?(0|[1-9][0-9]*)\.[0-9]+([eE][+-]?[0-9]+)?|-?[1-9][0-9]*[eE][+-]?[0-9]+', value) and math.isfinite(float(value)):
                if kinds[i] != 'TEXT':
                    kinds[i] = 'REAL'
            else:
                kinds[i] = 'TEXT'
    if not count:
        raise ValueError('CSV has no data rows.')
    conn.execute('CREATE TABLE "data" (' + ', '.join(identifier(n) + ' ' + k for n, k in zip(names, kinds)) + ')')
    reader = csv.reader(io.StringIO(text, newline=''), delimiter=delimiter, strict=True)
    next(reader)
    def values():
        for row in reader:
            if row:
                yield [None if v == '' else int(v) if k == 'INTEGER' else float(v) if k == 'REAL' else v for v, k in zip(row, kinds)]
    conn.executemany('INSERT INTO "data" VALUES (' + ','.join('?' for n in names) + ')', values())
    return {'data': {'columns': {n: {'type': k, 'nullable': True} for n, k in zip(names, kinds)},
                     'primary_key': [], 'foreign_keys': [], 'indexes': [], 'row_count': count,
                     'original_headers': dict(zip(names, headers))}}


def sqlite_import(data, target):
    if not data.startswith(b'SQLite format 3\x00'):
        raise ValueError('This is not a SQLite database file. Upload a valid .db file.')
    if data[18:20] != b'\x01\x01':
        raise ValueError('SQLite WAL files need a standalone export. Close/checkpoint your database and set PRAGMA journal_mode=DELETE before uploading the .db file.')
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'input.db'
        path.write_bytes(data)
        source = sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)
        try:
            source.execute('PRAGMA trusted_schema=OFF')
            source.execute('PRAGMA query_only=ON')
            source.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1024 * 1024)
            deadline = monotonic() + 20
            source.set_progress_handler(lambda: int(monotonic() > deadline), 1000)
            if source.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise ValueError('SQLite integrity check failed.')
            objects = source.execute("SELECT name, type, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
            if any(kind == 'view' or (ddl and 'CREATE VIRTUAL TABLE' in ddl.upper()) for name, kind, ddl in objects):
                raise ValueError('Upload a SQLite database containing ordinary tables; views and virtual tables are not supported.')
            names = [name for name, kind, ddl in objects if kind == 'table']
            if not names or len(names) > MAX_TABLES:
                raise ValueError('SQLite uploads need 1–50 ordinary tables.')
            schema = {}
            for name in names:
                if len(name) > 128 or '/' in name or '\x00' in name:
                    raise ValueError('Table names must be at most 128 characters without slashes.')
                extended = source.execute('PRAGMA table_xinfo(' + identifier(name) + ')').fetchall()
                if any(c[6] for c in extended):
                    raise ValueError('Generated or hidden columns are unsupported. Export their values to ordinary columns first.')
                columns = source.execute('PRAGMA table_info(' + identifier(name) + ')').fetchall()
                if not columns or len(columns) > MAX_COLUMNS:
                    raise ValueError('Each table needs 1–200 ordinary columns.')
                info = {'columns': {}, 'primary_key': [c[1] for c in sorted(columns, key=lambda c: c[5]) if c[5]], 'foreign_keys': [], 'indexes': []}
                definitions = []
                for _, col, declared, notnull, default, pk in columns:
                    declared = (declared or '').upper()
                    kind = 'INTEGER' if 'INT' in declared else 'TEXT' if any(t in declared for t in ('CHAR', 'CLOB', 'TEXT', 'DATE', 'TIME')) else 'REAL' if any(t in declared for t in ('REAL', 'FLOA', 'DOUB')) else 'NUMERIC'
                    if 'BLOB' in declared or len(col) > 128:
                        raise ValueError('Binary BLOB columns and column names over 128 characters are not supported.')
                    info['columns'][col] = {'type': kind, 'nullable': not bool(notnull or pk)}
                    definitions.append(identifier(col) + ' ' + kind)
                if info['primary_key']:
                    definitions.append('PRIMARY KEY (' + ','.join(map(identifier, info['primary_key'])) + ')')
                fks = {}
                for fid, seq, other, local, remote, *_ in source.execute('PRAGMA foreign_key_list(' + identifier(name) + ')'):
                    if other not in names:
                        continue
                    fk = fks.setdefault(fid, {'constrained_columns': [], 'referred_table': other, 'referred_columns': [], 'referred_schema': None})
                    fk['constrained_columns'].append(local)
                    fk['referred_columns'].append(remote)
                info['foreign_keys'] = list(fks.values())
                target.execute('CREATE TABLE ' + identifier(name) + ' (' + ','.join(definitions) + ')')
                schema[name] = info
            # Imported triggers, defaults, constraints and executable schema never reach the stored snapshot.
            source.set_authorizer(lambda action, a, b, db, trigger: sqlite3.SQLITE_OK if action in {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ} else sqlite3.SQLITE_DENY)
            total = 0
            for name, info in schema.items():
                cols = ','.join(map(identifier, info['columns']))
                cursor = source.execute('SELECT ' + cols + ' FROM ' + identifier(name))
                count = 0
                while batch := cursor.fetchmany(500):
                    if any(isinstance(v, bytes) for row in batch for v in row):
                        raise ValueError('Binary BLOB values are not supported.')
                    count += len(batch)
                    total += len(batch)
                    if total > MAX_ROWS:
                        raise ValueError('SQLite uploads support at most 200,000 total records.')
                    target.executemany('INSERT INTO ' + identifier(name) + ' VALUES (' + ','.join('?' for c in info['columns']) + ')', batch)
                info['row_count'] = count
            for info in schema.values():
                for fk in info['foreign_keys']:
                    if any(c is None for c in fk['referred_columns']):
                        pk = schema[fk['referred_table']]['primary_key']
                        if len(pk) == len(fk['constrained_columns']):
                            fk['referred_columns'] = pk
                        else:
                            raise ValueError('A foreign key does not resolve to a valid primary key.')
            return schema
        finally:
            source.close()


@router.post('', status_code=201, openapi_extra={'requestBody': {'required': True, 'content': {'multipart/form-data': {'schema': {'type': 'object', 'required': ['file'], 'properties': {'file': {'type': 'string', 'format': 'binary'}, 'name': {'type': 'string', 'maxLength': 80}}}}}}})
async def upload_source(request: Request, user=Depends(require_user)):
    # Authenticate before multipart parsing or opening spool files.
    async with request.form(max_files=1, max_fields=1, max_part_size=1024) as form:
        file, name = form.get('file'), form.get('name', '')
        if not isinstance(file, UploadFile) or not isinstance(name, str):
            raise HTTPException(422, 'Provide one database file and an optional dataset name.')
        return await run_in_threadpool(import_source, file, name, user)


def import_source(file, name, user):
    final = None
    try:
        name = name.strip() or Path(file.filename or 'My data').stem.strip()
        if not 1 <= len(name) <= 80:
            raise HTTPException(422, 'Dataset name must have 1–80 characters.')
        suffix = Path(file.filename or '').suffix.lower()
        if suffix not in {'.csv', '.db'}:
            raise HTTPException(400, 'Upload a CSV (.csv) or SQLite (.db) file.')
        data = file.file.read(MAX_BYTES + 1)
        if not data or len(data) > MAX_BYTES:
            raise HTTPException(413, 'Upload a nonempty file up to 50 MB.')
        dataset_id = uuid.uuid4().hex
        with tempfile.TemporaryDirectory(dir=root()) as folder:
            staged = Path(folder) / 'snapshot.db'
            with sqlite3.connect(staged) as conn:
                conn.execute('PRAGMA journal_mode=DELETE')
                schema = csv_import(data, conn) if suffix == '.csv' else sqlite_import(data, conn)
            size = staged.stat().st_size
            if size > MAX_BYTES:
                raise HTTPException(413, 'The imported snapshot exceeds 50 MB.')
            with metadata_session() as db:
                # Serialize per-account quota checks for concurrent uploads.
                db.scalar(select(User).where(User.id == user['id']).with_for_update())
                records = db.scalars(select(Dataset).where(Dataset.user_id == user['id'])).all()
                if len(records) >= MAX_SOURCES or sum(r.size_bytes for r in records) + size > MAX_STORAGE:
                    raise HTTPException(409, 'Your upload allowance is 10 datasets and 200 MB total.')
                record = Dataset(id=dataset_id, user_id=user['id'], name=name, kind='csv' if suffix == '.csv' else 'sqlite', size_bytes=size, tables=schema)
                final = root() / (dataset_id + '.db')
                staged.replace(final)
                db.add(record)
                db.flush()
                result = describe(record)
                db.commit()
                final = None
                return result
    except (ValueError, csv.Error, sqlite3.Error, UnicodeError) as exc:
        raise HTTPException(400, str(exc) if isinstance(exc, (ValueError, csv.Error)) else 'SQLite file could not be imported. Check that it is complete and valid.') from None
    finally:
        file.file.close()
        if final:
            final.unlink(missing_ok=True)
