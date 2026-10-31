import io
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app import auth, main, sources, service
from app.config import settings
from app.db import Base, Dataset, History, analytical_engine
from app.executor import execute
from app.guardrails import validate_sql, Blocked
from app.models import Generation
from app.schema import extract_schema
from app.browser import browse_records


@pytest.fixture
def studio(monkeypatch, tmp_path):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    for module in (auth, main, sources):
        monkeypatch.setattr(module, 'metadata_session', factory)
    monkeypatch.setattr(main, 'metadata_engine', lambda: engine)
    monkeypatch.setattr(service, 'save_history', lambda request, response: store(factory, request, response))
    monkeypatch.setenv('DATASET_DIR', str(tmp_path / 'uploads'))
    monkeypatch.setenv('VALIDATION_MODE', 'fast')
    settings.cache_clear()
    with TestClient(main.app) as client:
        accounts = []
        for email in ('one@example.com', 'two@example.com'):
            r = client.post('/v1/auth/signup', json={'email': email, 'name': 'Test', 'password': 'long enough password'}).json()
            accounts.append((r['user'], {'Authorization': 'Bearer ' + r['token']}))
        yield client, accounts, factory
    settings.cache_clear()
    engine.dispose()


def store(factory, request, response):
    with factory() as db:
        h = History(session_id=request.session_id, question=request.question, status=response.status, response=response.model_dump(mode='json'))
        db.add(h)
        db.flush()
        response.id = h.id
        h.response = response.model_dump(mode='json')
        db.commit()


def upload(client, headers, data, filename='sales.csv', name='My sales'):
    return client.post('/v1/sources', headers=headers, files={'file': (filename, data)}, data={'name': name})


def test_csv_types_preview_query_history_and_owner_isolation(studio, monkeypatch):
    client, ((user, headers), (other, other_headers)), factory = studio
    r = upload(client, headers, b'Order ID,Amount,Region,Code,Note\n1,12.50,North,001,\n2,7.25,South,002,hello\n')
    assert r.status_code == 201, r.text
    source_id = r.json()['id']
    listed = client.get('/v1/sources', headers=headers).json()['items']
    assert [x['id'] for x in listed] == ['demo', source_id]
    assert len(client.get('/v1/sources', headers=other_headers).json()['items']) == 1
    schema = client.get('/v1/schema', headers=headers, params={'source_id': source_id}).json()['tables']
    assert schema['data']['columns']['amount']['type'] == 'REAL'
    assert schema['data']['columns']['code']['type'] == 'TEXT'
    assert schema['data']['original_headers']['order_id'] == 'Order ID'
    rows = client.get('/v1/data/data', headers=headers, params={'source_id': source_id, 'limit': 1, 'offset': 1}).json()
    assert rows['total_rows'] == 2 and rows['rows'][0]['code'] == '002'
    for route in ('/v1/schema', '/v1/data/data'):
        assert client.get(route, headers=other_headers, params={'source_id': source_id}).status_code == 404
    assert client.post('/v1/query', headers=other_headers, json={'question': 'Count rows', 'source_id': source_id}).status_code == 404
    assert client.get('/v1/sources').status_code == 401
    assert upload(client, {}, b'id\n1\n').status_code == 401
    monkeypatch.setattr(service, 'select_schema', lambda question, s: (s, []))
    class Provider:
        def structured(self, prompt, model):
            assert 'SQLite analytical SQL' in prompt
            assert 'GLOSSARY: {}' in prompt and 'EXAMPLES: []' in prompt
            return Generation(sql='SELECT SUM(amount) AS total FROM data')
    monkeypatch.setattr(service, 'get_provider', Provider)
    result = client.post('/v1/query', headers=headers, json={'question': 'Total amount?', 'source_id': source_id}).json()
    assert result['results'] == [{'total': 19.75}], result
    assert result['source_id'] == source_id and result['source_name'] == 'My sales'
    saved = client.get('/v1/history/' + str(result['id']), headers=headers).json()
    assert saved['source_id'] == source_id
    assert client.get('/v1/history/' + str(result['id']), headers=other_headers).status_code == 404
    with sources.use_source(source_id, user):
        assert execute(validate_sql('SELECT COUNT(*) AS n FROM data', extract_schema()))[0] == [{'n': 2}]
        with pytest.raises(Blocked):
            validate_sql('DELETE FROM data', extract_schema())
        with analytical_engine().connect() as conn:
            for sql in ('DELETE FROM data', "ATTACH DATABASE ':memory:' AS evil", "SELECT load_extension('evil')"):
                with pytest.raises(Exception):
                    conn.execute(text(sql))
    assert sources.current_source.get() is None


def sqlite_bytes(tmp_path, ddl, inserts=''):
    path = tmp_path / 'original.db'
    path.unlink(missing_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(ddl + inserts)
    return path.read_bytes()


def test_sqlite_relationships_names_trigger_stripping_and_safe_join(studio, tmp_path):
    client, ((user, headers), _), factory = studio
    data = sqlite_bytes(tmp_path, 'CREATE TABLE departments(id INTEGER PRIMARY KEY, name TEXT); CREATE TABLE employees(id INTEGER PRIMARY KEY, department_id INTEGER REFERENCES departments(id), name TEXT); CREATE TRIGGER t AFTER INSERT ON employees BEGIN DELETE FROM departments; END;', "INSERT INTO departments VALUES(1,'Sales'); INSERT INTO employees VALUES(1,1,'Ada'); INSERT INTO departments VALUES(1,'Sales');")
    r = upload(client, headers, data, 'company.db', 'Company')
    assert r.status_code == 201, r.text
    with sources.use_source(r.json()['id'], user):
        schema = extract_schema()
        assert schema['employees']['foreign_keys'][0]['referred_table'] == 'departments'
        sql = validate_sql('SELECT e.name AS employee, d.name AS department FROM employees e JOIN departments d ON e.department_id=d.id', schema)
        assert execute(sql)[0] == [{'employee': 'Ada', 'department': 'Sales'}]
        assert browse_records('employees', 50, 0).total_rows == 1
    with sqlite3.connect(sources.root() / (r.json()['id'] + '.db')) as conn:
        assert conn.execute("SELECT count(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0] == 0


@pytest.mark.parametrize('data,filename', [(b'', 'x.csv'), (b'id,id\n1,2\n','x.csv'), (b'A b,A-b\n1,2\n','x.csv'), (b'id,name\n1\n','x.csv'), (b'hello','x.db'), (b'id\n','x.csv'), (b'id\n1\n','x.exe'), (b'id,name\n1,\xff\n','x.csv')])
def test_invalid_uploads_leave_no_dataset_or_snapshot(studio, data, filename):
    client, ((user, headers), _), factory = studio
    assert upload(client, headers, data, filename).status_code in (400, 413)
    with factory() as db:
        assert not db.scalars(select(Dataset)).all()
    assert not list(sources.root().glob('*.db'))


def test_sqlite_rejects_views_blobs_and_corrupt_files(studio, tmp_path):
    client, ((user, headers), _), factory = studio
    for ddl in ('CREATE TABLE a(id INT); CREATE VIEW v AS SELECT * FROM a;', 'CREATE TABLE a(payload BLOB);', 'CREATE VIRTUAL TABLE a USING fts5(body);'):
        r = upload(client, headers, sqlite_bytes(tmp_path, ddl), 'bad.db')
        assert r.status_code == 400, r.text
    assert upload(client, headers, b'SQLite format 3\x00' + b'x' * 4096, 'bad.db').status_code == 400


def test_size_row_quota_and_path_safety(studio, monkeypatch):
    client, ((user, headers), _), factory = studio
    monkeypatch.setattr(sources, 'MAX_BYTES', 16)
    assert upload(client, headers, b'x' * 17).status_code == 413
    monkeypatch.setattr(sources, 'MAX_BYTES', 50 * 1024 * 1024)
    monkeypatch.setattr(sources, 'MAX_ROWS', 1)
    assert upload(client, headers, b'id\n1\n2\n').status_code == 400
    monkeypatch.setattr(sources, 'MAX_ROWS', 200000)
    r = upload(client, headers, b'id\n1\n', '../../escape.csv')
    assert r.status_code == 201
    assert (sources.root() / (r.json()['id'] + '.db')).is_file()
    monkeypatch.setattr(sources, 'MAX_SOURCES', 1)
    assert upload(client, headers, b'id\n2\n').status_code == 409
    assert len(list(sources.root().glob('*.db'))) == 1
    assert client.get('/v1/schema', headers=headers, params={'source_id': '../../etc/passwd'}).status_code == 422


def test_request_contexts_do_not_mix_and_timeout_is_enforced(studio, monkeypatch):
    client, ((user, headers), _), factory = studio
    ids = [upload(client, headers, f'id\n{n}\n'.encode()).json()['id'] for n in (11, 22)]
    def run(pair):
        sid, expected = pair
        with sources.use_source(sid, user):
            assert execute(validate_sql('SELECT SUM(id) AS n FROM data', extract_schema()))[0] == [{'n': expected}]
        assert sources.current_source.get() is None
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(run, zip(ids, (11, 22))))
    with sources.use_source(ids[0], user):
        real = sources.monotonic
        ticks = iter([real(), real() + 100])
        monkeypatch.setattr(sources, 'monotonic', lambda: next(ticks, real() + 100))
        with pytest.raises(Exception, match='interrupted'):
            execute('WITH RECURSIVE t(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM t WHERE n<1000000) SELECT sum(n) FROM t')


def test_csv_quotes_unicode_nulls_full_column_inference_and_sqlite_dates(studio):
    client, ((user, headers), _), factory = studio
    r = upload(client, headers, '\ufeffDate;Amount;Code;Name;Mixed\n2026-10-01;1.25;001;"A;B";7\n2026-10-02;2.75;002;Åda;later\n2026-10-03;;003;;9\n'.encode('utf-8'))
    assert r.status_code == 201, r.text
    with sources.use_source(r.json()['id'], user):
        schema = extract_schema()
        assert schema['data']['columns']['mixed']['type'] == 'TEXT'
        rows = browse_records('data', 50, 0).rows
        assert rows[0]['name'] == 'A;B'
        assert rows[1]['name'] == 'Åda'
        assert rows[2]['amount'] is None and rows[2]['name'] is None
        sql = validate_sql("SELECT strftime('%Y-%m', date) AS month, SUM(amount) AS total FROM data GROUP BY strftime('%Y-%m', date)", schema)
        assert execute(sql)[0] == [{'month': '2026-10', 'total': 4}]


def test_sqlite_quoted_identifiers_implicit_foreign_keys_and_wal_rejection(studio, tmp_path):
    client, ((user, headers), _), factory = studio
    data = sqlite_bytes(tmp_path, 'CREATE TABLE "Sales teams"("Team ID" INT PRIMARY KEY); CREATE TABLE people(id INT PRIMARY KEY, team INT REFERENCES "Sales teams");', 'INSERT INTO "Sales teams" VALUES(4); INSERT INTO people VALUES(1,4);')
    r = upload(client, headers, data, 'quoted.db')
    assert r.status_code == 201, r.text
    with sources.use_source(r.json()['id'], user):
        schema = extract_schema()
        assert schema['people']['foreign_keys'][0]['referred_columns'] == ['Team ID']
        assert execute(validate_sql('SELECT "Team ID" AS id FROM "Sales teams"', schema))[0] == [{'id': 4}]
        assert browse_records('Sales teams', 50, 0).total_rows == 1
    wal = bytearray(data)
    wal[18:20] = b'\x02\x02'
    r = upload(client, headers, bytes(wal), 'wal.db')
    assert r.status_code == 400 and 'WAL' in r.text


def test_request_body_size_is_bounded_before_multipart_parsing(studio, monkeypatch):
    from app import upload_limits
    client, ((user, headers), _), factory = studio
    r = client.post('/v1/sources', headers={**headers, 'content-length': str(60 * 1024 * 1024)}, files={'file': ('tiny.csv', b'id\n1\n')})
    assert r.status_code == 413
    monkeypatch.setattr(upload_limits, 'MAX_BYTES', 1)
    def chunks():
        yield b'--b\r\nContent-Disposition: form-data; name="file"; filename="large.csv"\r\n\r\n'
        yield b'x' * (1024 * 1024 + 1)
        yield b'\r\n--b--\r\n'
    r = client.post('/v1/sources', headers={**headers, 'content-type': 'multipart/form-data; boundary=b'}, content=chunks())
    assert r.status_code == 413
    with factory() as db:
        assert not db.scalars(select(Dataset)).all()


def test_failed_metadata_finalization_rolls_back_and_removes_snapshot(studio, monkeypatch):
    client, ((user, headers), _), factory = studio
    def failed(record):
        raise ValueError('Could not finalize the source.')
    monkeypatch.setattr(sources, 'describe', failed)
    assert upload(client, headers, b'id\n1\n').status_code == 400
    with factory() as db:
        assert not db.scalars(select(Dataset)).all()
    assert not list(sources.root().glob('*.db'))
