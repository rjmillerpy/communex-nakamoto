from fastapi import Request, Response, FastAPI
from starlette.middleware.base import BaseHTTPMiddleware

from keylimiter import KeyLimiter, TokenBucketLimiter

from typing import Callable, Awaitable

Callback = Callable[[Request], Awaitable[Response]]

class IpLimiterMiddleware(BaseHTTPMiddleware):
    def __init__(
            self,
            app: FastAPI,
            limiter: KeyLimiter | None = None,
    ):
        '''
        :param app: FastAPI instance
        :param limiter: KeyLimiter instance OR None
        
        If limiter is None, then a default TokenBucketLimiter is used with the following config:
        bucket_size=200, refill_rate=15
        '''
        super().__init__(app)
        
        # fallback to default limiter
        self._limiter = limiter or TokenBucketLimiter(bucket_size=200, refill_rate=15)

    async def dispatch(self, request: Request, call_next: Callback) -> Response:
        assert request.client is not None, "request is invalid"
        assert request.client.host, "request is invalid."
        
        ip = request.client.host
        
        is_allowed = self._limiter.allow(ip)

        
        if not is_allowed:
            response = Response(status_code=400, headers={"X-RateLimit-Remaining": str(self._limiter.remaining(ip))})
            return response
        
        response = await call_next(request)
        
        return response
    
    