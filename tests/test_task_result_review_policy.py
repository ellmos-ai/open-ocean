"""Contract tests for the pure result-review policy."""
from __future__ import annotations

import hashlib

import pytest

from tools.task_result_review_policy import (
    DECISION_SCHEMA,
    PRODUCER_ISSUER,
    PRODUCER_SCHEMA,
    REVIEWER_SCHEMA,
    SCOPE_SCHEMA,
    SERVICE_ISSUER,
    TARGET_SCHEMA,
    evaluate_service_review,
)


def _identity():
    return {
        "schema": REVIEWER_SCHEMA,
        "service_id": "reviewer-service-1",
        "issuer_id": SERVICE_ISSUER,
        "principal_id": "reviewer-principal",
        "generation": "reviewer-generation",
        "revision": 3,
        "status": "active",
    }


def _scope(*entries):
    return {
        "schema": SCOPE_SCHEMA,
        "service_id": "reviewer-service-1",
        "revision": 3,
        "entries": list(entries),
    }


def _task(*, category="docs", result=True, generation="worker-generation"):
    if not result:
        return {
            "schema": TARGET_SCHEMA, "task_id": 17, "category": category,
            "result_id": None, "result_sha256": None, "generation": None,
            "fence": None, "task_version": None,
        }
    digest = hashlib.sha256(b"original").hexdigest()
    return {
        "schema": TARGET_SCHEMA, "task_id": 17, "category": category,
        "result_id": 9, "result_sha256": digest, "generation": generation,
        "fence": 4, "task_version": hashlib.sha256(b"task").hexdigest(),
    }


def _producer(task=None, **changes):
    task = task or _task()
    value = {
        "schema": PRODUCER_SCHEMA,
        "issuer_id": PRODUCER_ISSUER,
        "task_id": task["task_id"],
        "result_id": task["result_id"],
        "result_sha256": task["result_sha256"],
        "generation": task["generation"],
        "fence": task["fence"],
        "task_version": task["task_version"],
        "producer_principal": "worker-principal",
    }
    value.update(changes)
    return value


_MISSING = object()


def _evaluate(*, scope=None, task=None, producer=_MISSING, reviewer=None, action="accept"):
    task = task or _task()
    if producer is _MISSING:
        producer = _producer(task) if task["result_id"] is not None else None
    return evaluate_service_review(
        scope or _scope({"action": action, "task_id": task["task_id"]}),
        task,
        producer,
        reviewer or _identity(),
        action,
    )


def _assert_decision(decision, allowed, reason):
    assert decision == {
        "schema": DECISION_SCHEMA,
        "allowed": allowed,
        "reason_code": reason,
    }


@pytest.mark.parametrize("action", ["read", "history", "accept", "correction"])
def test_exact_task_scope_allows_only_the_named_action(action):
    _assert_decision(_evaluate(action=action), True, "allow")


def test_category_scope_matches_casefolded_category_and_is_or_with_task_scope():
    task = _task(category="Documentation")
    scope = _scope(
        {"action": "read", "task_id": 99},
        {"action": "accept", "category": "documentation"},
    )
    _assert_decision(_evaluate(scope=scope, task=task, action="accept"), True, "allow")


def test_action_scopes_are_not_implied():
    scope = _scope({"action": "read", "task_id": 17})
    _assert_decision(_evaluate(scope=scope, action="history"), False, "scope_denied")


def test_scope_for_another_task_or_category_denies():
    scope = _scope({"action": "accept", "task_id": 18})
    _assert_decision(_evaluate(scope=scope), False, "scope_denied")


@pytest.mark.parametrize("bad_entry", [
    {"action": "accept", "task_id": 17, "category": "docs"},
    {"action": "accept", "category": "*"},
    {"action": "accept", "category": "all"},
    {"action": "accept", "task_id": True},
    {"action": "accept", "task_id": 0},
    {"action": "admin", "task_id": 17},
    {"action": "accept", "task_id": 17, "extra": "value"},
    {"action": [], "task_id": 17},
])
def test_malformed_or_global_scope_is_rejected(bad_entry):
    _assert_decision(_evaluate(scope=_scope(bad_entry)), False, "invalid_request")


def test_service_identity_and_revision_bind_scope():
    reviewer = {**_identity(), "revision": 4}
    _assert_decision(_evaluate(reviewer=reviewer), False, "invalid_request")
    scope = {**_scope({"action": "accept", "task_id": 17}), "service_id": "other"}
    _assert_decision(_evaluate(scope=scope), False, "invalid_request")


def test_revoked_service_is_denied():
    reviewer = {**_identity(), "status": "revoked"}
    _assert_decision(_evaluate(reviewer=reviewer), False, "service_revoked")


def test_missing_or_mismatched_producer_binding_fails_closed():
    _assert_decision(_evaluate(producer=None), False, "producer_binding_missing")
    task = _task()
    mismatch = _producer(task, result_sha256="0" * 64)
    _assert_decision(_evaluate(task=task, producer=mismatch), False, "producer_binding_missing")


def test_same_producer_principal_is_not_allowed_to_self_review():
    task = _task()
    producer = _producer(task, producer_principal="REVIEWER-PRINCIPAL")
    _assert_decision(_evaluate(task=task, producer=producer), False, "self_review")


def test_same_result_generation_is_not_allowed_to_self_review():
    task = _task(generation="reviewer-generation")
    _assert_decision(_evaluate(task=task, producer=_producer(task)), False, "self_review")


def test_distinct_trusted_producer_can_review_with_matching_scope():
    task = _task()
    _assert_decision(_evaluate(task=task, producer=_producer(task)), True, "allow")


@pytest.mark.parametrize("action", ["read", "history"])
def test_empty_task_snapshot_can_be_read_without_producer_binding(action):
    task = _task(result=False)
    scope = _scope({"action": action, "task_id": task["task_id"]})
    _assert_decision(_evaluate(task=task, producer=None, scope=scope, action=action), True, "allow")


@pytest.mark.parametrize("action", ["accept", "correction"])
def test_empty_task_snapshot_cannot_be_accepted_or_corrected(action):
    task = _task(result=False)
    scope = _scope({"action": action, "task_id": task["task_id"]})
    _assert_decision(_evaluate(task=task, producer=None, scope=scope, action=action), False, "invalid_request")


@pytest.mark.parametrize("field,value", [
    ("task_id", True),
    ("result_id", False),
    ("fence", True),
])
def test_bool_is_not_accepted_as_an_integer(field, value):
    task = _task()
    task[field] = value
    _assert_decision(_evaluate(task=task), False, "invalid_request")


def test_unknown_action_or_extra_reviewer_fields_are_rejected():
    _assert_decision(_evaluate(action="admin"), False, "invalid_request")
    reviewer = {**_identity(), "token": "must-not-be-an-input"}
    _assert_decision(_evaluate(reviewer=reviewer), False, "invalid_request")
    _assert_decision(_evaluate(reviewer={**_identity(), "status": []}), False, "invalid_request")


def test_malformed_unhashable_action_is_denied_without_exception():
    _assert_decision(_evaluate(action=[]), False, "invalid_request")


def test_producer_boolean_fence_cannot_match_integer_fence():
    task = _task()
    producer = _producer(task, fence=True)
    _assert_decision(_evaluate(task=task, producer=producer), False, "producer_binding_missing")


def test_nul_in_scope_category_is_rejected():
    scope = _scope({"action": "read", "category": "docs\x00private"})
    _assert_decision(_evaluate(scope=scope), False, "invalid_request")
