"""
Tests for tools/coordination.py -- distributed atomic leases (CAP-1.1).

Covers the check-then-write race (exactly one winner among N concurrent
claimers), fencing-token behaviour across steal/release, TTL expiry,
and fail-closed handling of defective stores.
"""

from __future__ import annotations

import threading
import time
from dataclasses import FrozenInstanceError

import pytest

from tools.coordination import CoordinationError, Lease, LeaseStore


def _store(tmp_path, name="leases.db") -> LeaseStore:
    return LeaseStore(tmp_path / name)


def test_claim_fresh_db_returns_lease(tmp_path):
    s = _store(tmp_path)
    lease = s.claim("gpu-0", "worker-a", 30.0)
    assert lease is not None
    assert lease.name == "gpu-0"
    assert lease.owner == "worker-a"
    assert lease.token >= 1
    assert lease.created <= lease.expires_at
    assert lease.expires_at > time.time()
    s.close()


def test_second_claim_same_name_returns_none(tmp_path):
    s1 = _store(tmp_path)
    s2 = _store(tmp_path)
    lease = s1.claim("gpu-0", "worker-a", 30.0)
    assert lease is not None
    assert s2.claim("gpu-0", "worker-b", 30.0) is None
    assert s1.owner_of("gpu-0") == "worker-a"
    s1.close()
    s2.close()


def test_claim_race_exactly_one_winner(tmp_path):
    db = tmp_path / "race.db"
    LeaseStore(db).close()  # pre-create schema; the race is about claiming
    n = 8
    barrier = threading.Barrier(n)
    results: list[object] = [None] * n
    errors: list[str] = []

    def worker(i: int) -> None:
        store = LeaseStore(db)
        try:
            barrier.wait(timeout=15)
            results[i] = store.claim("shared", f"worker-{i}", 30.0)
        except Exception as exc:  # surface in assertion below
            errors.append(f"thread {i}: {exc!r}")
        finally:
            store.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not any(t.is_alive() for t in threads), "worker threads stuck"
    assert not errors, f"claim race raised: {errors}"
    winners = [r for r in results if isinstance(r, Lease)]
    assert len(winners) == 1, f"expected exactly one winner, got {results}"

    check = LeaseStore(db)
    try:
        assert check.owner_of("shared") == winners[0].owner
    finally:
        check.close()


def test_expired_lease_can_be_stolen_with_fresh_token(tmp_path):
    s1 = _store(tmp_path)
    s2 = _store(tmp_path)
    first = s1.claim("gpu-0", "owner-a", 0.05)
    assert first is not None
    time.sleep(0.12)
    second = s2.claim("gpu-0", "owner-b", 30.0)
    assert second is not None
    assert second.owner == "owner-b"
    # fencing: the stolen lease carries a strictly larger token...
    assert second.token > first.token
    # ...so the preempted holder can no longer renew or release it
    assert s1.renew("gpu-0", first.token, 30.0) is False
    assert s1.release("gpu-0", first.token) is False
    assert s1.owner_of("gpu-0") == "owner-b"
    s1.close()
    s2.close()


def test_renew_requires_matching_token(tmp_path):
    s = _store(tmp_path)
    lease = s.claim("gpu-0", "owner-a", 30.0)
    assert lease is not None
    assert s.renew("gpu-0", lease.token + 1, 60.0) is False
    assert s.renew("gpu-0", lease.token, 60.0) is True
    s.close()


def test_renew_extends_expiry(tmp_path):
    s = _store(tmp_path)
    lease = s.claim("gpu-0", "owner-a", 0.2)
    assert lease is not None
    assert s.renew("gpu-0", lease.token, 30.0) is True
    time.sleep(0.3)  # beyond the original TTL: only the renew kept it alive
    assert s.owner_of("gpu-0") == "owner-a"
    s.close()


def test_renew_expired_but_uncontested_lease(tmp_path):
    s = _store(tmp_path)
    lease = s.claim("gpu-0", "owner-a", 0.05)
    assert lease is not None
    time.sleep(0.12)
    # token is still the freshest generation, so the holder may renew
    assert s.renew("gpu-0", lease.token, 30.0) is True
    assert s.owner_of("gpu-0") == "owner-a"
    s.close()


def test_release_requires_matching_token_and_refreshes_token(tmp_path):
    s = _store(tmp_path)
    lease = s.claim("gpu-0", "owner-a", 30.0)
    assert lease is not None
    assert s.release("gpu-0", lease.token + 1) is False
    assert s.owner_of("gpu-0") == "owner-a"
    assert s.release("gpu-0", lease.token) is True
    assert s.owner_of("gpu-0") is None
    reclaimed = s.claim("gpu-0", "owner-b", 30.0)
    assert reclaimed is not None
    # AUTOINCREMENT never reuses tokens, even across release/re-claim
    assert reclaimed.token > lease.token
    s.close()


def test_owner_of_filters_expired(tmp_path):
    s = _store(tmp_path)
    assert s.claim("gpu-0", "owner-a", 0.05) is not None
    assert s.owner_of("gpu-0") == "owner-a"
    time.sleep(0.12)
    assert s.owner_of("gpu-0") is None
    assert s.owner_of("never-claimed") is None
    s.close()


def test_prune_expired(tmp_path):
    s = _store(tmp_path)
    assert s.claim("short", "owner-a", 0.05) is not None
    assert s.claim("long", "owner-a", 30.0) is not None
    time.sleep(0.12)
    assert s.prune_expired() == 1
    assert s.prune_expired() == 0
    assert s.owner_of("long") == "owner-a"
    fresh = s.claim("short", "owner-b", 30.0)
    assert fresh is not None
    assert s.owner_of("short") == "owner-b"
    s.close()


def test_lease_is_frozen(tmp_path):
    s = _store(tmp_path)
    lease = s.claim("gpu-0", "owner-a", 30.0)
    assert lease is not None
    with pytest.raises(FrozenInstanceError):
        lease.owner = "other"
    s.close()


@pytest.mark.parametrize("bad_ttl", [0, -1, -0.5, float("nan"), float("inf"), True])
def test_claim_rejects_invalid_ttl(tmp_path, bad_ttl):
    s = _store(tmp_path)
    with pytest.raises(ValueError):
        s.claim("gpu-0", "owner-a", bad_ttl)
    s.close()


@pytest.mark.parametrize("field", ["name", "owner"])
def test_claim_rejects_empty_strings(tmp_path, field):
    s = _store(tmp_path)
    kwargs = {"name": "gpu-0", "owner": "owner-a", "ttl_seconds": 30.0}
    kwargs[field] = "   "
    with pytest.raises(ValueError):
        s.claim(**kwargs)
    s.close()


@pytest.mark.parametrize("bad_token", [0, -3, 1.5, True, None])
def test_renew_release_reject_bad_token_type(tmp_path, bad_token):
    s = _store(tmp_path)
    with pytest.raises(ValueError):
        s.renew("gpu-0", bad_token, 30.0)
    with pytest.raises(ValueError):
        s.release("gpu-0", bad_token)
    s.close()


def test_defective_db_fails_closed(tmp_path):
    bad = tmp_path / "broken.db"
    bad.write_bytes(b"\x00garbage-not-a-sqlite-db" * 8)
    with pytest.raises(CoordinationError):
        LeaseStore(bad)


def test_missing_parent_dir_fails_closed(tmp_path):
    with pytest.raises(CoordinationError):
        LeaseStore(tmp_path / "no-such-dir" / "leases.db")
