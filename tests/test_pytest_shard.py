"""Tests for deterministic sha256 pytest sharding (#2195, #3494, #3495, #3496)."""
from __future__ import annotations

import hashlib
import pytest
from tools.pytest_shard import filter_items_for_shard, shard_for_nodeid


def test_shard_formula_matches_canonical_sha256_prefix():
    nodeid = "tests/test_python_packages.py::test_install_rollback"
    expected = int(hashlib.sha256(nodeid.encode("utf-8")).hexdigest()[:8], 16) % 4
    assert shard_for_nodeid(nodeid, 4) == expected


def test_filter_items_partitions_exhaustively_and_disjointly():
    nodeids = [f"tests/test_mod.py::test_case_{i}" for i in range(79)]
    shards = [filter_items_for_shard(nodeids, idx, 4) for idx in range(4)]
    combined = [item for shard in shards for item in shard]
    assert len(combined) == len(nodeids)
    assert set(combined) == set(nodeids)
    for i in range(4):
        for j in range(i + 1, 4):
            assert set(shards[i]).isdisjoint(shards[j])


def test_invalid_shard_arguments_raise_value_error():
    with pytest.raises(ValueError):
        shard_for_nodeid("tests/test_a.py::test_1", 0)
    with pytest.raises(ValueError):
        filter_items_for_shard(["tests/test_a.py::test_1"], 4, 4)
