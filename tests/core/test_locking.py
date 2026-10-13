from __future__ import annotations

import pytest

from core.locking import (
    LockAcquisitionTimeout,
    RedisLock,
    coupon_redemption_lock,
    distributed_mutex,
    inventory_reservation_lock,
    wallet_transaction_lock,
)

pytestmark = pytest.mark.unit


def test_acquire_and_release_cycle():
    lock = RedisLock("resource-1", ttl_seconds=5)
    assert lock.acquire() is True
    assert lock.is_held is True
    assert lock.release() is True
    assert lock.is_held is False


def test_second_acquire_blocks_while_held(monkeypatch):
    lock_a = RedisLock("resource-2", ttl_seconds=5)
    lock_b = RedisLock("resource-2", ttl_seconds=5, acquire_timeout_seconds=0.1, retry_interval_seconds=0.01)
    assert lock_a.acquire() is True
    assert lock_b.acquire(blocking=False) is False
    lock_a.release()
    assert lock_b.acquire(blocking=False) is True
    lock_b.release()


def test_context_manager_releases_on_exit():
    with RedisLock("resource-3", ttl_seconds=5) as lock:
        assert lock.is_held
    assert not lock.is_held


def test_context_manager_raises_on_timeout():
    holder = RedisLock("resource-4", ttl_seconds=5)
    assert holder.acquire() is True
    contender = RedisLock("resource-4", ttl_seconds=5, acquire_timeout_seconds=0.1, retry_interval_seconds=0.01)
    with pytest.raises(LockAcquisitionTimeout):
        with contender:
            pass
    holder.release()


def test_release_without_holding_returns_false():
    lock = RedisLock("resource-5", ttl_seconds=5)
    assert lock.release() is False


def test_release_does_not_release_another_owners_lock():
    """Token-checked release: a lock instance can never release a lock it doesn't hold, even under the same key."""
    lock_a = RedisLock("resource-6", ttl_seconds=1)
    assert lock_a.acquire() is True
    lock_a._token = "forged-token"  # simulate a stale/incorrect token
    assert lock_a.release() is False


def test_extend_refreshes_ttl_for_current_holder():
    lock = RedisLock("resource-7", ttl_seconds=1)
    assert lock.acquire() is True
    assert lock.extend(additional_seconds=5) is True
    lock.release()


def test_extend_fails_when_not_holding():
    lock = RedisLock("resource-8", ttl_seconds=1)
    assert lock.extend(additional_seconds=5) is False


def test_distributed_mutex_context_manager():
    with distributed_mutex("resource-9", ttl_seconds=5) as lock:
        assert lock.is_held


def test_named_constructors_produce_distinct_namespaces():
    inv = inventory_reservation_lock("stock-1")
    wallet = wallet_transaction_lock("wallet-1")
    coupon = coupon_redemption_lock("coupon-1")
    assert inv._key != wallet._key != coupon._key


def test_locks_on_different_resource_names_do_not_conflict():
    lock_a = RedisLock("resource-a", ttl_seconds=5)
    lock_b = RedisLock("resource-b", ttl_seconds=5)
    assert lock_a.acquire() is True
    assert lock_b.acquire() is True
    lock_a.release()
    lock_b.release()
