"""Pure operator UI selection: recorded authority, bindings and refusals."""
from __future__ import annotations

import builtins
import hashlib
import json
import socket
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from tools.operator_ui_selection import (
    FULL_SURFACES, LITE_PROVIDER_ID, OperatorUISelectionError, ProviderContract,
    RecordedUIChoice, VerifiedProviderFacts, select_operator_ui,
)

COMMIT = "a" * 40
REPO = "https://github.com/example/ui"
FULL_ID = "fixture-neutral-full-ui"  # Synthetic; never a catalogue ID.
ENTRY = "fixture_ui.app:create_app"


def binding(module_id=LITE_PROVIDER_ID, profile="lite", surfaces=frozenset()):
    manifest = {
        "schema": "ellmos.module.v2", "id": module_id, "kind": "ui",
        "category": "runtime", "status": "active", "provides": ["operator.ui"],
        "requires": [], "source_of_truth": {
            "type": "git-repository", "path": ".", "repository": REPO,
        },
    }
    blob = json.dumps(manifest, sort_keys=True).encode()
    contract = ProviderContract(
        module_id, profile, REPO, COMMIT, hashlib.sha256(blob).hexdigest(),
        ENTRY, surfaces,
    )
    actual = VerifiedProviderFacts(module_id, REPO, COMMIT, blob, ENTRY, surfaces)
    return contract, actual


def choice(*, full=False, providers=(LITE_PROVIDER_ID,), enabled=True):
    return RecordedUIChoice("recorded-fixture-decision", enabled, full, providers)


def reject(code, decision=None, contracts=None, facts=None, full_id=None):
    contract, actual = binding()
    with pytest.raises(OperatorUISelectionError) as error:
        select_operator_ui(
            decision or choice(), (contract,) if contracts is None else contracts,
            (actual,) if facts is None else facts, full_provider_id=full_id,
        )
    assert error.value.code == code


def test_lite_exact_verified_entry_without_full_candidate():
    contract, actual = binding()
    result = select_operator_ui(choice(), (contract,), (actual,))
    assert result.module_id == LITE_PROVIDER_ID
    assert result.entrypoint == ENTRY
    assert result.commit == COMMIT
    assert result.manifest_sha256 == hashlib.sha256(actual.manifest_bytes).hexdigest()


def test_headless_requires_no_candidates_observations_or_full_identity():
    assert select_operator_ui(
        choice(enabled=False, full=None, providers=()), (), (),
    ) is None


def test_synthetic_full_requires_every_named_full_surface():
    contract, actual = binding(FULL_ID, "full", FULL_SURFACES)
    result = select_operator_ui(
        choice(full=True, providers=(FULL_ID,)), (contract,), (actual,),
        full_provider_id=FULL_ID,
    )
    assert result.module_id == FULL_ID
    assert result.profile == "full"
    assert result.surfaces == FULL_SURFACES


@pytest.mark.parametrize("value", [None, "", " ", 0, False])
def test_recorded_decision_reference_required(value):
    reject("invalid_choice", replace(choice(), decision_id=value))


@pytest.mark.parametrize("value", [None, 0, 1, "", "true"])
def test_ui_enablement_is_an_actual_bool(value):
    reject("invalid_choice", replace(choice(), ui_enabled=value))


@pytest.mark.parametrize("value", [None, 0, 1, "", "all"])
def test_enabled_ui_requires_explicit_full_partial_bool(value):
    reject("invalid_choice", replace(choice(), full_installation=value))


def test_headless_with_provider_refused():
    reject("conflicting_choice", choice(enabled=False))


def test_two_selected_candidates_refused_before_binding():
    reject("ambiguous_choice", choice(providers=(LITE_PROVIDER_ID, FULL_ID)))


def test_required_role_cannot_be_empty():
    reject("required_role_unbound", choice(providers=()))


@pytest.mark.parametrize("providers", [[LITE_PROVIDER_ID], "ellmos-unified-gui", (None,), ("",)])
def test_role_bindings_must_be_immutable_valid_ids(providers):
    reject("invalid_choice", choice(providers=providers))


def test_unknown_selected_id_refused():
    reject("unknown_provider", choice(providers=("unknown-ui",)))


def test_full_missing_actual_manifest_identity_has_no_lite_fallback():
    reject("unresolved_full_provider", choice(full=True))


def test_known_lite_cannot_satisfy_full_choice():
    contract, actual = binding()
    reject("selection_mismatch", choice(full=True), (contract,), (actual,), FULL_ID)


def test_known_full_cannot_satisfy_partial_choice():
    contract, actual = binding(FULL_ID, "full", FULL_SURFACES)
    reject("selection_mismatch", choice(providers=(FULL_ID,)), (contract,), (actual,), FULL_ID)


def test_duplicate_candidate_identity_refused():
    contract, actual = binding()
    reject("ambiguous_binding", contracts=(contract, contract), facts=(actual,))


@pytest.mark.parametrize("facts_count", [0, 2])
def test_exactly_one_verified_fact_for_selected_candidate(facts_count):
    contract, actual = binding()
    reject("source_binding_unavailable", contracts=(contract,), facts=(actual,) * facts_count)


@pytest.mark.parametrize("field,value", [
    ("commit", "b" * 40), ("repository", "https://github.com/other/ui"),
    ("entrypoint", "fixture_ui.other:create_app"), ("manifest_bytes", b"{}"),
])
def test_observation_mismatch_refused(field, value):
    contract, actual = binding()
    code = "manifest_mismatch" if field == "manifest_bytes" else "source_binding_mismatch"
    reject(code, contracts=(contract,), facts=(replace(actual, **{field: value}),))


@pytest.mark.parametrize("field,value", [
    ("commit", "main"), ("commit", "A" * 40), ("manifest_sha256", ""),
    ("manifest_sha256", "A" * 64), ("entrypoint", ""), ("entrypoint", "bad/path"),
    ("repository", ""), ("profile", "activity"),
    ("required_surfaces", ["activity"]),
])
def test_invalid_immutable_contract_refused(field, value):
    contract, actual = binding()
    reject("invalid_provider_contract", contracts=(replace(contract, **{field: value}),), facts=(actual,))


@pytest.mark.parametrize("mutation", [
    {"schema": "other"}, {"id": "wrong"}, {"provides": []},
    {"provides": "operator.ui"}, {"kind": "backend"},
    {"source_of_truth": {"type": "git-repository", "path": ".", "repository": "https://github.com/other/ui"}},
    {"source_of_truth": {"type": "git-repository", "path": "../foreign", "repository": REPO}},
])
def test_manifest_semantics_are_checked_even_when_byte_pin_matches(mutation):
    contract, actual = binding()
    value = json.loads(actual.manifest_bytes)
    value.update(mutation)
    blob = json.dumps(value).encode()
    contract = replace(contract, manifest_sha256=hashlib.sha256(blob).hexdigest())
    reject("invalid_manifest", contracts=(contract,), facts=(replace(actual, manifest_bytes=blob),))


@pytest.mark.parametrize("blob", [
    b"not json", b"[]", b'{"schema":"ellmos.module.v2","schema":"other"}',
    b'{"value":NaN}', b"\xff",
])
def test_malformed_or_ambiguous_manifest_refused(blob):
    contract, actual = binding()
    contract = replace(contract, manifest_sha256=hashlib.sha256(blob).hexdigest())
    reject("invalid_manifest", contracts=(contract,), facts=(replace(actual, manifest_bytes=blob),))


def test_lite_must_preserve_no_required_bach_or_neutral_shell():
    contract, actual = binding()
    value = json.loads(actual.manifest_bytes)
    value["requires"] = ["bach"]
    blob = json.dumps(value).encode()
    contract = replace(contract, manifest_sha256=hashlib.sha256(blob).hexdigest())
    reject("invalid_manifest", contracts=(contract,), facts=(replace(actual, manifest_bytes=blob),))


@pytest.mark.parametrize("missing", sorted(FULL_SURFACES))
def test_activity_or_incomplete_surface_set_never_satisfies_full(missing):
    contract, actual = binding(FULL_ID, "full", FULL_SURFACES)
    reject(
        "missing_capability", choice(full=True, providers=(FULL_ID,)),
        (contract,), (replace(actual, surfaces=FULL_SURFACES - {missing}),), FULL_ID,
    )


def test_full_contract_cannot_weaken_full_surface_requirements():
    contract, actual = binding(FULL_ID, "full", frozenset({"activity"}))
    reject(
        "invalid_provider_contract", choice(full=True, providers=(FULL_ID,)),
        (contract,), (actual,), FULL_ID,
    )


def test_selected_lite_checks_its_own_required_surface_contract():
    contract, actual = binding(surfaces=frozenset({"dashboard"}))
    reject("missing_capability", contracts=(contract,), facts=(replace(actual, surfaces=frozenset()),))


def test_selection_is_pure_deterministic_and_inputs_unchanged(monkeypatch):
    contract, actual = binding()
    decision = choice()
    def forbidden(*args, **kwargs):
        raise AssertionError("selector attempted external action")
    with monkeypatch.context() as guard:
        guard.setattr(builtins, "open", forbidden)
        guard.setattr(Path, "read_bytes", forbidden)
        guard.setattr(Path, "exists", forbidden)
        guard.setattr(subprocess, "Popen", forbidden)
        guard.setattr(socket, "socket", forbidden)
        first = select_operator_ui(decision, (contract,), (actual,))
        second = select_operator_ui(decision, (contract,), (actual,))
    assert first == second
    assert decision == choice()
    assert contract == binding()[0]
    assert actual == binding()[1]

@pytest.mark.parametrize("profile", [[], {}, None, 0])
def test_malformed_profile_keeps_structured_refusal(profile):
    contract, actual = binding()
    reject("invalid_provider_contract", contracts=(replace(contract, profile=profile),), facts=(actual,))


def test_more_than_two_catalogue_candidates_refused():
    contract, actual = binding()
    full, _ = binding(FULL_ID, "full", FULL_SURFACES)
    other, _ = binding("fixture-extra-ui", "full", FULL_SURFACES)
    reject("invalid_provider_contract", contracts=(contract, full, other), facts=(actual,))
