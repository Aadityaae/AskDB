"""Bound multipart request bodies before oversized uploads can fill temporary storage."""
from starlette.formparsers import MultiPartException
from starlette.responses import JSONResponse
from app.sources import MAX_BYTES
from app.speech import MAX_AUDIO_BYTES


class UploadBodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('method') not in {'POST', 'PUT', 'PATCH'}:
            return await self.app(scope, receive, send)
        path = scope.get('path', '').rstrip('/')
        if path == '/v1/sources':
            maximum, detail = MAX_BYTES + 1024 * 1024, 'Upload a file up to 50 MB.'
        elif path == '/v1/transcribe':
            maximum, detail = MAX_AUDIO_BYTES + 64 * 1024, 'Record audio up to 6 MB and 60 seconds.'
        else:
            maximum, detail = 128 * 1024, 'Request body exceeds 128 KB.'
        headers = dict(scope.get('headers', []))
        error = JSONResponse({'detail': detail}, status_code=413)
        if b'content-length' in headers:
            try:
                length = int(headers[b'content-length'])
                if length < 0:
                    raise ValueError('Negative request size')
                if length > maximum:
                    return await error(scope, receive, send)
            except ValueError:
                return await JSONResponse({'detail': 'Invalid request size.'}, status_code=400)(scope, receive, send)
        size, exceeded, replied = 0, False, False

        async def bounded_receive():
            nonlocal size, exceeded
            message = await receive()
            size += len(message.get('body', b''))
            if size > maximum:
                exceeded = True
                # Starlette closes any multipart spool files when this exception occurs.
                raise MultiPartException('Upload exceeds the size limit.')
            return message

        async def bounded_send(message):
            nonlocal replied
            if exceeded:
                if not replied:
                    replied = True
                    await error(scope, receive, send)
                return
            await send(message)

        await self.app(scope, bounded_receive, bounded_send)
