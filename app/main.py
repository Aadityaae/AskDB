from contextlib import asynccontextmanager
import logging
import httpx
from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Depends
from sqlalchemy import select, text, func
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from app.config import settings
from app.db import Base, History, Feedback, analytical_engine, metadata_engine, metadata_session
from app.models import QueryRequest, QueryResponse, FeedbackRequest, FeedbackResponse, HealthResponse, SchemaResponse, HistoryResponse
from app.service import run_query
from app.schema import extract_schema
from app.browser import browse_records
from app.models import TableRecordsResponse
from app.guardrails import Blocked
from app.models import TranscriptionResponse
from app import speech
from app.auth import router as auth_router, require_user
from app.sources import router as sources_router, use_source
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
import mimetypes
from threading import Thread, BoundedSemaphore
from starlette.datastructures import UploadFile as ParsedUploadFile
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi import Request

mimetypes.add_type('font/woff2', '.woff2')
query_capacity = BoundedSemaphore(4)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')


@asynccontextmanager
async def lifespan(app):
    try:
        Base.metadata.create_all(metadata_engine())
    except Exception:
        logging.warning('Metadata unavailable. Configure DATABASE_URL and start PostgreSQL.')
    Thread(target=speech.warmup, name='local-speech-warmup', daemon=True).start()
    yield


app = FastAPI(title='AskDB API', version='0.1.0', lifespan=lifespan)
from app.upload_limits import UploadBodyLimit
app.add_middleware(UploadBodyLimit)
from app.security import SecurityHeaders
app.add_middleware(SecurityHeaders)
app.include_router(auth_router)
app.include_router(sources_router)
app.mount('/landing', StaticFiles(directory=Path(__file__).resolve().parents[1] / 'frontend' / 'landing', html=True), name='landing')


@app.get('/', include_in_schema=False)
def landing_home():
    return RedirectResponse('/landing/')


@app.get('/workspace', include_in_schema=False)
def workspace_entry(request: Request, entry: str = Query('signin', pattern=r'^(signin|signup|workspace)$')):
    target = settings().workspace_url or str(request.url.replace(port=8501, path='/', query=''))
    return RedirectResponse(target.rstrip('/') + '/?entry=' + entry)


@app.post('/v1/transcribe', response_model=TranscriptionResponse, openapi_extra={'requestBody': {'required': True, 'content': {'multipart/form-data': {'schema': {'type': 'object', 'required': ['audio'], 'properties': {'audio': {'type': 'string', 'format': 'binary'}}}}}}})
async def transcribe_recording(request: Request, user=Depends(require_user)):
    try:
        async with request.form(max_files=1, max_fields=0) as form:
            audio = form.get('audio')
            if not isinstance(audio, ParsedUploadFile):
                raise HTTPException(422, 'Provide one WAV recording.')
            data = await audio.read(speech.MAX_AUDIO_BYTES + 1)
        return await run_in_threadpool(speech.transcribe, data)
    except StarletteHTTPException:
        raise
    except speech.InvalidAudio as exc:
        raise HTTPException(400, str(exc))
    except speech.SpeechUnavailable as exc:
        raise HTTPException(503, str(exc))
    except Exception:
        logging.error('speech_transcription_failed')
        raise HTTPException(503, 'Transcription could not complete. Try a shorter, clearer recording.')


@app.post('/v1/query', response_model=QueryResponse)
def query(request: QueryRequest, user=Depends(require_user)):
    if not query_capacity.acquire(blocking=False):
        raise HTTPException(429, 'The query service is busy. Please retry shortly.', headers={'Retry-After': '2'})
    try:
        request.session_id = f'user:{user["id"]}'
        with use_source(request.source_id, user):
            return run_query(request)
    finally:
        query_capacity.release()


@app.get('/v1/schema', response_model=SchemaResponse)
def schema(source_id: str = Query('demo', pattern=r'^(demo|[0-9a-f]{32})$'), user=Depends(require_user)):
    try:
        with use_source(source_id, user):
            return SchemaResponse(tables=extract_schema())
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, 'Schema unavailable. Check PostgreSQL and the analyst connection.')


@app.get('/v1/data/{table_name}', response_model=TableRecordsResponse)
def table_records(table_name: str, limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), source_id: str = Query('demo', pattern=r'^(demo|[0-9a-f]{32})$'), user=Depends(require_user)):
    try:
        with use_source(source_id, user):
            return browse_records(table_name, limit, offset)
    except HTTPException:
        raise
    except KeyError:
        raise HTTPException(404, 'Table not found in the business database.')
    except Blocked:
        raise HTTPException(400, 'This table cannot be browsed within the configured query safety limits.')
    except Exception:
        logging.error('table_browser_failed table=%r', table_name)
        raise HTTPException(503, 'Records unavailable. Check the business database connection.')


@app.get('/v1/health', response_model=HealthResponse)
def health():
    status = {}
    for label, getter in [('database', analytical_engine), ('metadata', metadata_engine)]:
        try:
            with getter().connect() as connection:
                connection.execute(text('SELECT 1'))
            status[label] = 'ok'
        except Exception:
            status[label] = 'unavailable'
    try:
        schema_status = 'ok' if extract_schema() else 'empty'
    except Exception:
        schema_status = 'unavailable'
    cfg = settings()
    if cfg.llm_provider == 'groq':
        llm, message = 'key_missing', 'Add GROQ_API_KEY to .env, then run docker compose up -d api.'
        key = cfg.groq_api_key.get_secret_value().strip()
        if key:
            try:
                response = httpx.get('https://api.groq.com/openai/v1/models', headers={'Authorization': 'Bearer ' + key}, timeout=10)
                if response.status_code in (401, 403):
                    llm, message = 'unauthorized', 'Check your Groq API key and model access.'
                elif response.status_code == 429:
                    llm, message = 'rate_limited', 'Groq rate limit reached. Retry later.'
                else:
                    response.raise_for_status()
                    models = {item['id'] for item in response.json().get('data', [])}
                    llm = 'ok' if cfg.groq_model in models else 'model_missing'
                    message = '' if llm == 'ok' else 'Check GROQ_MODEL against your available Groq models.'
            except Exception:
                llm, message = 'unavailable', 'Could not reach Groq. Check internet connectivity.'
        return HealthResponse(**status, llm=llm, provider='groq', model=cfg.groq_model, schema_status=schema_status, message=message)
    ollama, message = 'unavailable', 'Start Ollama and check OLLAMA_BASE_URL.'
    try:
        response = httpx.get(settings().ollama_base_url + '/api/tags', timeout=3)
        response.raise_for_status()
        models = {m['name'] for m in response.json().get('models', [])}
        ollama = 'ok' if settings().ollama_model in models else 'model_missing'
        message = '' if ollama == 'ok' else f'Run: ollama pull {settings().ollama_model}'
    except Exception:
        pass
    return HealthResponse(**status, ollama=ollama, llm=ollama, model=settings().ollama_model, schema_status=schema_status, message=message)


@app.get('/v1/history', response_model=HistoryResponse)
def history(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), status: str | None = None,
            start_date: date | None = None, end_date: date | None = None, user=Depends(require_user)):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(422, 'Start date must be on or before end date.')
    try:
        with metadata_session() as session:
            statement = select(History).where(History.session_id == f'user:{user["id"]}').order_by(History.timestamp.desc(), History.id.desc())
            if status:
                statement = statement.where(History.status == status)
            zone = ZoneInfo('Asia/Kolkata')
            if start_date:
                statement = statement.where(History.timestamp >= datetime.combine(start_date, time.min, zone))
            if end_date:
                statement = statement.where(History.timestamp < datetime.combine(end_date + timedelta(days=1), time.min, zone))
            total = session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
            return HistoryResponse(items=[{**{k: v for k, v in h.response.items() if k != 'results'}, 'id': h.id, 'timestamp': h.timestamp.isoformat()} for h in session.scalars(statement.limit(limit).offset(offset))], offset=offset, total=total)
    except Exception:
        raise HTTPException(503, 'History database unavailable.')


@app.get('/v1/history/{query_id}')
def saved_query(query_id: int, user=Depends(require_user)):
    try:
        with metadata_session() as session:
            record = session.get(History, query_id)
            if not record or record.session_id != f'user:{user["id"]}':
                raise HTTPException(404, 'Query not found.')
            return {**record.response, 'id': record.id, 'timestamp': record.timestamp.isoformat()}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, 'History database unavailable.')


@app.post('/v1/feedback', response_model=FeedbackResponse)
def feedback(request: FeedbackRequest, user=Depends(require_user)):
    try:
        with metadata_session() as session:
            record = session.get(History, request.query_id)
            if not record or record.session_id != f'user:{user["id"]}':
                raise HTTPException(404, 'Query not found.')
            session.add(Feedback(**request.model_dump()))
            session.commit()
        return FeedbackResponse(saved=True)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, 'Feedback database unavailable.')
