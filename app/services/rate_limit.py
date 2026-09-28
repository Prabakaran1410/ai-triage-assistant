"""Per-tenant rate limiting, counted in Redis.

Why Redis rather than a counter in the process: Render can run more than one
instance, and a limit each instance enforces separately is not the limit you
configured - it is that number multiplied by however many instances happen to
be running.

Why it matters here specifically: every /triage call spends provider quota.
Google's free tier allows 15 requests per minute per model, so one caller in
a retry loop can exhaust the quota for every tenant, and the symptom is
everyone else's replies escalating with "LLM provider unavailable".

Fixed window rather than a sliding one. A fixed window allows a burst across
a boundary - up to twice the limit either side of the minute mark - which is
the honest cost of two commands per check instead of a sorted set. The limit
here exists to stop runaway usage, not to shape traffic precisely, and the
boundary burst is still bounded.

Fails OPEN. If Redis is unreachable the request is allowed and the failure is
logged. A rate limiter is a protection against excess, not a correctness
guarantee, and taking the product down because the thing that counts requests
is unavailable trades a small problem for a large one.
"""
import logging
import time
from dataclasses import dataclass

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_client = None
_initialised = False


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    # Seconds until the current window ends; what a caller should wait.
    retry_after: int


def get_redis():
    """The shared Redis client, or None when none is configured."""
    global _client, _initialised
    if _initialised:
        return _client
    _initialised = True

    settings = get_settings()
    if not settings.redis_url:
        logger.info("REDIS_URL not set - rate limiting disabled")
        return None

    try:
        from redis.asyncio import from_url

        _client = from_url(settings.redis_url, decode_responses=True)
    except Exception:
        logger.exception("Could not create the Redis client - rate limiting disabled")
        _client = None
    return _client


def reset_redis() -> None:
    """Forget the cached client (tests, and settings changes)."""
    global _client, _initialised
    _client = None
    _initialised = False


async def check_rate_limit(
    key: str, *, limit: int, window_seconds: int = 60
) -> RateLimitDecision:
    """Count one request against `key` and say whether it is allowed."""
    if limit <= 0:
        return RateLimitDecision(True, limit, 0, 0)

    client = get_redis()
    if client is None:
        return RateLimitDecision(True, limit, limit, 0)

    window = int(time.time()) // window_seconds
    redis_key = f"ratelimit:{key}:{window}"

    try:
        pipeline = client.pipeline()
        pipeline.incr(redis_key)
        # Expiry is set on every call rather than only the first: a key whose
        # EXPIRE was lost (a failure between the two commands) would otherwise
        # live forever and block that caller until Redis was cleared by hand.
        pipeline.expire(redis_key, window_seconds)
        count, _ = await pipeline.execute()
    except Exception:
        logger.exception("Rate limit check failed for %s - allowing the request", key)
        return RateLimitDecision(True, limit, limit, 0)

    used = int(count)
    elapsed = int(time.time()) % window_seconds
    return RateLimitDecision(
        allowed=used <= limit,
        limit=limit,
        remaining=max(0, limit - used),
        retry_after=max(1, window_seconds - elapsed),
    )


async def close_redis() -> None:
    """Release the connection pool on shutdown."""
    global _client, _initialised
    if _client is not None:
        try:
            await _client.aclose()
        except Exception:
            logger.exception("Closing Redis failed")
    _client = None
    _initialised = False
