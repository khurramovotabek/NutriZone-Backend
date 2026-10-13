"""
Redis distributed locking.

This is the cross-process locking primitive for coordination that
cannot be expressed as a single PostgreSQL `SELECT ... FOR UPDATE`
(Database Blueprint §10) -- e.g. a multi-step saga step, a scheduled
job that must not run concurrently across multiple Celery Beat/worker
replicas, or coordinating across two different aggregate roots in two
different schemas. It is deliberately NOT a substitute for the
DB-level pessimistic locking Inventory/Wallet mutation already use
(Enterprise Database Blueprint §10) -- those keep using
`select_for_update()` at the repository layer; RedisLock is for
cross-process/cross-service coordination *around* those transactions,
not a replacement for the transactional guarantee itself.

Implementation: the classic "set NX with a random token + TTL, release
via a Lua script that checks the token before deleting" pattern, which
prevents a lock holder that has outlived its own TTL (e.g. paused by
GC, or killed) from accidentally releasing a lock now held by a
different owner -- this is the deadlock-prevention / auto-release
mechanism the mission requires.
"""
from __future__ import annotations

import contextlib
import time
import uuid
from typing import Iterator

from core.caching.redis_client import cache_key, get_redis_client

_RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

_EXTEND_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("pexpire", KEYS[1], ARGV[2])
else
    return 0
end
"""


class LockAcquisitionTimeout(RuntimeError):
    """Raised when a lock could not be acquired within the given timeout."""


class RedisLock:
    """
    A single named distributed lock.

    Usage:
        with RedisLock("inventory:stock_item:<id>", ttl_seconds=10) as lock:
            ...critical section...

    `ttl_seconds` is the auto-release safety net (the "Auto release"
    requirement) -- if the process holding the lock crashes without
    releasing it, the lock disappears on its own after this many
    seconds rather than deadlocking every future acquirer forever.
    """

    def __init__(
        self,
        name: str,
        ttl_seconds: float = 10.0,
        acquire_timeout_seconds: float = 5.0,
        retry_interval_seconds: float = 0.05,
        namespace: str = "lock",
    ) -> None:
        self._client = get_redis_client()
        self._key = cache_key(name, namespace=namespace)
        self._ttl_ms = int(ttl_seconds * 1000)
        self._acquire_timeout_seconds = acquire_timeout_seconds
        self._retry_interval_seconds = retry_interval_seconds
        self._token: str | None = None

    def acquire(self, blocking: bool = True) -> bool:
        token = str(uuid.uuid4())
        deadline = time.monotonic() + self._acquire_timeout_seconds

        while True:
            acquired = self._client.set(self._key, token, nx=True, px=self._ttl_ms)
            if acquired:
                self._token = token
                return True
            if not blocking:
                return False
            if time.monotonic() >= deadline:
                return False
            time.sleep(self._retry_interval_seconds)

    def release(self) -> bool:
        if self._token is None:
            return False
        released = bool(self._client.eval(_RELEASE_SCRIPT, 1, self._key, self._token))
        self._token = None
        return released

    def extend(self, additional_seconds: float) -> bool:
        """Extends the TTL of a lock this instance currently holds (heartbeat for long-running critical sections)."""
        if self._token is None:
            return False
        additional_ms = int(additional_seconds * 1000)
        return bool(self._client.eval(_EXTEND_SCRIPT, 1, self._key, self._token, additional_ms))

    @property
    def is_held(self) -> bool:
        return self._token is not None

    def __enter__(self) -> "RedisLock":
        if not self.acquire(blocking=True):
            raise LockAcquisitionTimeout(f"Could not acquire lock '{self._key}' within {self._acquire_timeout_seconds}s")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


@contextlib.contextmanager
def distributed_mutex(
    name: str,
    ttl_seconds: float = 10.0,
    acquire_timeout_seconds: float = 5.0,
) -> Iterator[RedisLock]:
    """
    Function-style alias for `RedisLock` used as a context manager --
    reads slightly better at call sites that want the "DistributedMutex"
    vocabulary from the mission statement:

        with distributed_mutex("wallet:credit:<wallet_id>"):
            ...
    """
    lock = RedisLock(name, ttl_seconds=ttl_seconds, acquire_timeout_seconds=acquire_timeout_seconds)
    with lock:
        yield lock


# Named constructors for the three concrete future use cases the
# mission calls out -- these are still generic (no business logic),
# just pre-scoped key namespaces so every future module locks the same
# resource identity the same way rather than each inventing its own
# key format.
def inventory_reservation_lock(stock_item_id: object, ttl_seconds: float = 10.0) -> RedisLock:
    return RedisLock(f"stock_item:{stock_item_id}", ttl_seconds=ttl_seconds, namespace="lock:inventory")


def wallet_transaction_lock(wallet_id: object, ttl_seconds: float = 10.0) -> RedisLock:
    return RedisLock(f"wallet:{wallet_id}", ttl_seconds=ttl_seconds, namespace="lock:wallet")


def coupon_redemption_lock(coupon_id: object, ttl_seconds: float = 5.0) -> RedisLock:
    return RedisLock(f"coupon:{coupon_id}", ttl_seconds=ttl_seconds, namespace="lock:coupons")
