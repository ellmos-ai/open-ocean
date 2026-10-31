"""Deterministic pytest nodeid sharding without external state files (#2195, #3494).

Formula:
    shard(nodeid) = int(sha256(nodeid)[:8], 16) % K
"""
from __future__ import annotations

import hashlib
from typing import Iterable, List, Sequence, TypeVar

T = TypeVar("T")


def shard_for_nodeid(nodeid: str, shard_count: int) -> int:
    """Return the deterministic shard index in [0, shard_count) for a pytest nodeid."""
    if type(shard_count) is not int or shard_count < 1:
        raise ValueError(f"shard_count must be a positive integer, got {shard_count!r}")
    if not isinstance(nodeid, str) or not nodeid:
        raise ValueError("nodeid must be a non-empty string")
    digest_prefix = hashlib.sha256(nodeid.encode("utf-8")).hexdigest()[:8]
    return int(digest_prefix, 16) % shard_count


def filter_items_for_shard(
    items: Sequence[T],
    shard_index: int,
    shard_count: int,
) -> List[T]:
    """Filter pytest items (or objects with a `.nodeid` attribute / strings) for one shard."""
    if type(shard_count) is not int or shard_count < 1:
        raise ValueError(f"shard_count must be >= 1, got {shard_count!r}")
    if type(shard_index) is not int or not (0 <= shard_index < shard_count):
        raise ValueError(f"shard_index must be in [0, {shard_count}), got {shard_index!r}")
    selected: List[T] = []
    for item in items:
        nodeid = item if isinstance(item, str) else getattr(item, "nodeid")
        if shard_for_nodeid(nodeid, shard_count) == shard_index:
            selected.append(item)
    return selected
