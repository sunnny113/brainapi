from __future__ import annotations

import time
from dataclasses import dataclass

from redis.asyncio import Redis


@dataclass(frozen=True)
class TokenLimitResult:
    allowed: bool
    retry_after_seconds: int


class InMemoryTokenRateLimiter:
    def __init__(self) -> None:
        # key -> {window_start_epoch: tokens}
        self._buckets: dict[str, dict[int, int]] = {}

    def is_allowed(self, key: str, tokens: int, max_tokens_per_minute: int) -> TokenLimitResult:
        now = int(time.time())
        window_start = now - (now % 60)

        buckets = self._buckets.setdefault(key, {})

        # Drop old windows
        for ts in list(buckets.keys()):
            if ts < window_start - 60:
                buckets.pop(ts, None)

        used = buckets.get(window_start, 0)
        if used + tokens > max_tokens_per_minute:
            retry_after = max(1, (window_start + 60) - now)
            return TokenLimitResult(False, retry_after)

        buckets[window_start] = used + tokens
        return TokenLimitResult(True, 0)


class RedisTokenRateLimiter:
    def __init__(self, redis_url: str, prefix: str = "brainapi:tokenlimit") -> None:
        self.redis = Redis.from_url(redis_url, decode_responses=True)
        self.prefix = prefix

    async def is_allowed(self, key: str, tokens: int, max_tokens_per_minute: int) -> TokenLimitResult:
        now = int(time.time())
        window_start = now - (now % 60)
        redis_key = f"{self.prefix}:{key}:{window_start}"

        used = await self.redis.incrby(redis_key, tokens)
        await self.redis.expire(redis_key, 120)

        if int(used) > max_tokens_per_minute:
            retry_after = max(1, (window_start + 60) - now)
            return TokenLimitResult(False, retry_after)

        return TokenLimitResult(True, 0)
