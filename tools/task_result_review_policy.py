"""Pure, versioned policy for narrowly scoped BACH result-review services.

This module has no database, credential, HTTP, or filesystem authority. BACH
supplies server-read snapshots and remains the canonical owner of every write.
"""
from __future__ import annotations

import re

INPUT_SCHEMA = "task-result-review-input.v1"
DECISION_SCHEMA = "task-result-service-review-decision.v1"
SCOPE_SCHEMA = "task-result-service-scope.v1"
TARGET_SCHEMA = "bach.task-result-review-target.v1"
PRODUCER_SCHEMA = "bach.task-result-producer-binding.v1"
REVIEWER_SCHEMA = "bach.task-result-service-principal.v1"
SERVICE_ISSUER = "bach.result-service.v1"
PRODUCER_ISSUER = "bach.native-task-lease.v1"
REASON_CODES = frozenset({
    "allow",
    "scope_denied",
    "self_review",
    "producer_binding_missing",
    "service_revoked",
    "invalid_request",
})
_ACTIONS = frozenset({"read", "history", "accept", "correction"})
_HEX_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_GENERATION = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")


def _decision(allowed: bool, reason_code: str) -> dict[str, object]:
    return {
        "schema": DECISION_SCHEMA,
        "allowed": allowed,
        "reason_code": reason_code,
    }


def _nonempty_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and "\x00" not in value


def _valid_identity(value: object) -> bool:
    return _nonempty_text(value) and len(value) <= 256


def _valid_revision(value: object) -> bool:
    return type(value) is int and value > 0


def _valid_target(task: object) -> bool:
    if not isinstance(task, dict) or set(task) != {
        "schema", "task_id", "category", "result_id", "result_sha256",
        "generation", "fence", "task_version",
    }:
        return False
    if task.get("schema") != TARGET_SCHEMA:
        return False
    if type(task.get("task_id")) is not int or task["task_id"] <= 0:
        return False
    category = task.get("category")
    if category is not None and (not _nonempty_text(category) or len(category) > 128):
        return False
    result_id = task.get("result_id")
    if result_id is None:
        return all(task.get(key) is None for key in (
            "result_sha256", "generation", "fence", "task_version"
        ))
    return (
        type(result_id) is int and result_id > 0
        and isinstance(task.get("result_sha256"), str)
        and _HEX_SHA256.fullmatch(task["result_sha256"]) is not None
        and isinstance(task.get("generation"), str)
        and _GENERATION.fullmatch(task["generation"]) is not None
        and type(task.get("fence")) is int and task["fence"] > 0
        and isinstance(task.get("task_version"), str)
        and _HEX_SHA256.fullmatch(task["task_version"]) is not None
    )


def _valid_producer_binding(binding: object, task: dict[str, object]) -> bool:
    if not isinstance(binding, dict) or set(binding) != {
        "schema", "issuer_id", "task_id", "result_id", "result_sha256",
        "generation", "fence", "task_version", "producer_principal",
    }:
        return False
    return (
        binding.get("schema") == PRODUCER_SCHEMA
        and binding.get("issuer_id") == PRODUCER_ISSUER
        and type(binding.get("task_id")) is int
        and binding["task_id"] == task["task_id"]
        and type(binding.get("result_id")) is int
        and binding["result_id"] == task["result_id"]
        and isinstance(binding.get("result_sha256"), str)
        and binding["result_sha256"] == task["result_sha256"]
        and isinstance(binding.get("generation"), str)
        and binding["generation"] == task["generation"]
        and type(binding.get("fence")) is int
        and binding["fence"] == task["fence"]
        and isinstance(binding.get("task_version"), str)
        and binding["task_version"] == task["task_version"]
        and _valid_identity(binding.get("producer_principal"))
    )
def _valid_reviewer(reviewer: object) -> bool:
    if not isinstance(reviewer, dict) or set(reviewer) != {
        "schema", "service_id", "issuer_id", "principal_id",
        "generation", "revision", "status",
    }:
        return False
    return (
        reviewer.get("schema") == REVIEWER_SCHEMA
        and _valid_identity(reviewer.get("service_id"))
        and reviewer.get("issuer_id") == SERVICE_ISSUER
        and _valid_identity(reviewer.get("principal_id"))
        and isinstance(reviewer.get("generation"), str)
        and _GENERATION.fullmatch(reviewer["generation"]) is not None
        and _valid_revision(reviewer.get("revision"))
        and isinstance(reviewer.get("status"), str)
        and reviewer["status"] in {"active", "revoked"}
    )


def _valid_scope(scope: object, reviewer: dict[str, object]) -> bool:
    if not isinstance(scope, dict) or set(scope) != {
        "schema", "service_id", "revision", "entries",
    }:
        return False
    if (scope.get("schema") != SCOPE_SCHEMA
            or scope.get("service_id") != reviewer.get("service_id")
            or scope.get("revision") != reviewer.get("revision")
            or not _valid_revision(scope.get("revision"))
            or not isinstance(scope.get("entries"), list)):
        return False
    for entry in scope["entries"]:
        if not isinstance(entry, dict) or "action" not in entry:
            return False
        keys = set(entry)
        if keys not in ({"action", "task_id"}, {"action", "category"}):
            return False
        if not isinstance(entry.get("action"), str) or entry["action"] not in _ACTIONS:
            return False
        if "task_id" in entry:
            if type(entry["task_id"]) is not int or entry["task_id"] <= 0:
                return False
        else:
            category = entry.get("category")
            if not _nonempty_text(category) or len(category) > 128:
                return False
            if category.strip() in {"*", "all"}:
                return False
    return True


def _scope_matches(scope: dict[str, object], task: dict[str, object], action: str) -> bool:
    """Entries are ORed; each entry binds exactly one action and one target."""
    category = task.get("category")
    for entry in scope["entries"]:
        if entry["action"] != action:
            continue
        if "task_id" in entry and entry["task_id"] == task["task_id"]:
            return True
        if ("category" in entry and isinstance(category, str)
                and entry["category"].strip().casefold() == category.strip().casefold()):
            return True
    return False


def evaluate_service_review(
    scope: object,
    task: object,
    producer_binding: object,
    reviewer_subject: object,
    action: object,
) -> dict[str, object]:
    """Return a strict allow/deny DTO for one server-derived review action.

    Task-ID and category scope entries are ORed, but scopes never imply another
    action. A result-bearing target requires a matching trusted producer binding.
    """
    if (not isinstance(action, str) or action not in _ACTIONS
            or not _valid_target(task) or not _valid_reviewer(reviewer_subject)):
        return _decision(False, "invalid_request")
    if reviewer_subject["status"] != "active":
        return _decision(False, "service_revoked")
    if not _valid_scope(scope, reviewer_subject):
        return _decision(False, "invalid_request")
    if task["result_id"] is None:
        if producer_binding is not None:
            return _decision(False, "producer_binding_missing")
        if action in {"accept", "correction"}:
            return _decision(False, "invalid_request")
    else:
        if not _valid_producer_binding(producer_binding, task):
            return _decision(False, "producer_binding_missing")
        if (producer_binding["producer_principal"].casefold()
                == reviewer_subject["principal_id"].casefold()
                or producer_binding["generation"] == reviewer_subject["generation"]):
            return _decision(False, "self_review")
    if not _scope_matches(scope, task, action):
        return _decision(False, "scope_denied")
    return _decision(True, "allow")
