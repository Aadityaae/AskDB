"""Conservative response headers compatible with the existing local UI."""


class SecurityHeaders:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        async def secured_send(message):
            if message['type'] == 'http.response.start':
                headers = list(message.get('headers', []))
                headers.extend([(b'x-content-type-options', b'nosniff'),
                                (b'referrer-policy', b'strict-origin-when-cross-origin'),
                                (b'x-frame-options', b'DENY')])
                if scope.get('path', '').startswith('/v1/'):
                    headers = [(k, v) for k, v in headers if k.lower() not in {b'cache-control', b'pragma'}]
                    headers.extend([(b'cache-control', b'no-store'), (b'pragma', b'no-cache'),
                                    (b'content-security-policy', b"default-src 'none'; frame-ancestors 'none'")])
                message = {**message, 'headers': headers}
            await send(message)
        await self.app(scope, receive, secured_send)
