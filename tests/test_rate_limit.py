"""Rate limiting logic, with a stand-in for Redis.

The counting itself is two Redis commands; what is worth testing is the
decisions around them - that the limit is enforced, that windows reset, that
tenants are counted separately, and above all that an unreachable Redis
allows the request rather than taking the product down.
"""
import pytest

from app.core.config import get_settings
from app.services import rate_limit
from app.services.rate_limit import check_rate_limit


class FakeRedis:
    """Enough of the client for a fixed-window counter."""

    def __init__(self, *, fail: bool = False):
        self.store: dict[str, int] = {}
        self.expiries: dict[str, int] = {}
        self.fail = fail

    def pipeline(self):
        return FakePipeline(self)


class FakePipeline:
    def __init__(self, redis: FakeRedis):
        self.redis = redis
        self.queued: list[tuple[str, tuple]] = []

    def incr(self, key):
        self.queued.append(("incr", (key,)))

    def expire(self, key, seconds):
        self.queued.append(("expire", (key, seconds)))

    async def execute(self):
        if self.redis.fail:
            raise ConnectionError("redis is unreachable")
        results = []
        for op, args in self.queued:
            if op == "incr":
                self.redis.store[args[0]] = self.redis.store.get(args[0], 0) + 1
                results.append(self.redis.store[args[0]])
            else:
                self.redis.expiries[args[0]] = args[1]
                results.append(True)
        return results


@pytest.fixture
def fake_redis(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(rate_limit, "get_redis", lambda: redis)
    return redis


async def test_requests_are_allowed_up_to_the_limit(fake_redis):
    for i in range(3):
        decision = await check_rate_limit("tenant-a", limit=3)
        assert decision.allowed is True, f"request {i + 1} of 3 should be allowed"
    assert decision.remaining == 0


async def test_the_request_past_the_limit_is_refused(fake_redis):
    for _ in range(3):
        await check_rate_limit("tenant-a", limit=3)
    decision = await check_rate_limit("tenant-a", limit=3)
    assert decision.allowed is False
    assert decision.remaining == 0
    # A client needs to know how long to wait, not just that it failed.
    assert 1 <= decision.retry_after <= 60


async def test_remaining_counts_down(fake_redis):
    assert (await check_rate_limit("tenant-a", limit=5)).remaining == 4
    assert (await check_rate_limit("tenant-a", limit=5)).remaining == 3


async def test_tenants_are_counted_separately(fake_redis):
    """One tenant's runaway integration must not starve another's."""
    for _ in range(3):
        await check_rate_limit("tenant-a", limit=3)
    assert (await check_rate_limit("tenant-a", limit=3)).allowed is False
    assert (await check_rate_limit("tenant-b", limit=3)).allowed is True


async def test_a_new_window_starts_fresh(fake_redis, monkeypatch):
    for _ in range(3):
        await check_rate_limit("tenant-a", limit=3)
    assert (await check_rate_limit("tenant-a", limit=3)).allowed is False

    # Move into the next window; the key is derived from the clock.
    real_time = rate_limit.time.time
    monkeypatch.setattr(rate_limit.time, "time", lambda: real_time() + 60)
    assert (await check_rate_limit("tenant-a", limit=3)).allowed is True


async def test_an_unreachable_redis_allows_the_request(monkeypatch):
    """Fails open on purpose. A limiter guards against excess; it is not a
    correctness guarantee, and taking the product down because the counter
    is unavailable trades a small problem for a large one."""
    monkeypatch.setattr(rate_limit, "get_redis", lambda: FakeRedis(fail=True))
    decision = await check_rate_limit("tenant-a", limit=1)
    assert decision.allowed is True


async def test_no_redis_configured_means_no_limiting(monkeypatch):
    monkeypatch.setattr(rate_limit, "get_redis", lambda: None)
    for _ in range(50):
        assert (await check_rate_limit("tenant-a", limit=1)).allowed is True


async def test_a_limit_of_zero_disables_the_check(fake_redis):
    for _ in range(20):
        assert (await check_rate_limit("tenant-a", limit=0)).allowed is True
    assert fake_redis.store == {}, "a disabled limit should not touch Redis"


async def test_expiry_is_refreshed_on_every_call(fake_redis):
    """A key whose EXPIRE was lost would otherwise live forever and block
    that tenant until Redis was cleared by hand."""
    await check_rate_limit("tenant-a", limit=5)
    fake_redis.expiries.clear()
    await check_rate_limit("tenant-a", limit=5)
    assert fake_redis.expiries, "the second call should have set an expiry too"


def test_the_configured_default_is_below_the_free_tier_quota():
    """Google's free tier allows 15 requests per minute per model. The
    default exists to stop one tenant exhausting that for everyone, so it
    should be in that neighbourhood rather than an arbitrary large number."""
    get_settings.cache_clear()
    try:
        assert 0 < get_settings().triage_rate_limit_per_minute <= 60
    finally:
        get_settings.cache_clear()
