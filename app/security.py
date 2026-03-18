import time
from collections import defaultdict, deque
from typing import Optional

from fastapi import HTTPException, Request, status
from redis.asyncio import Redis

from .auth import AuthIdentity, verify_user_api_key


class InMemoryRateLimiter:
    def __init__(self, max_requests: int, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def is_allowed(self, key: str, max_requests: int | None = None) -> tuple[bool, int]:
        effective_limit = max_requests if max_requests is not None else self.max_requests
        now = time.time()
        window_start = now - self.window_seconds
        bucket = self._events[key]

        while bucket and bucket[0] < window_start:
            bucket.popleft()

        if len(bucket) >= effective_limit:
            retry_after = max(1, int(self.window_seconds - (now - bucket[0])))
            return (False, retry_after)

        bucket.append(now)
        return (True, 0)


class RedisRateLimiter:
    def __init__(self, redis_url: str, prefix: str = "brainapi:ratelimit") -> None:
        self.redis = Redis.from_url(redis_url, decode_responses=True)
        self.prefix = prefix

    async def is_allowed(self, key: str, max_requests: int, window_seconds: int = 60) -> tuple[bool, int]:
        now = time.time()
        window_start = now - window_seconds
        redis_key = f"{self.prefix}:{key}"

        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(redis_key, 0, window_start)
            pipe.zadd(redis_key, {str(now): now})
            pipe.zcard(redis_key)
            pipe.expire(redis_key, window_seconds + 2)
            _, _, count, _ = await pipe.execute()

        count_int = int(count)
        if count_int > max_requests:
            oldest = await self.redis.zrange(redis_key, 0, 0, withscores=True)
            if oldest:
                oldest_ts = float(oldest[0][1])
                retry_after = max(1, int(window_seconds - (now - oldest_ts)))
            else:
                retry_after = 1
            return (False, retry_after)

        return (True, 0)


# ============================================
# API KEY AUTHENTICATION
# ============================================

def extract_api_key_from_request(request: Request) -> Optional[str]:
    """Extract API key from Authorization header or X-API-Key header."""
    
    # Check Authorization: Bearer <token>
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:]
    
    # Check X-API-Key header
    return request.headers.get("x-api-key")


async def require_api_key(request: Request) -> AuthIdentity:
    """Dependency that requires API key authentication on protected endpoints."""
    
    api_key = extract_api_key_from_request(request)
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide it via Authorization header (Bearer <token>) or X-API-Key header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    identity = verify_user_api_key(api_key)
    
    if not identity:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Attach identity to request state for use in endpoints
    request.state.auth_identity = identity
    
    return identity
