from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from copy import deepcopy
from pathlib import Path

import pytest

from tools.ocean_inspect import (
    DEFAULT_PROVIDER_VERSION,
    PRESENTATION_OMISSIONS,
    PROVIDER_BINDING_REF,
    InspectError,
    _coverage_presentation,
    inspect_workspace,
    rejection_report,
)
from tools.resolve_bundles import DEFAULT_COMPONENT_BINDINGS


REPO_ROOT = Path(__file__).resolve().parents[1]
PINNED_PROVIDER = "ec50c92319ba8fc262d695b86818fc85666feff7"
EVALUATED_AT = "2026-07-30T20:00:00Z"
EXPIRES_AT = "2026-07-30T22:00:00Z"
REGISTRY_HASH = "d" * 64


def _canonical_bytes(value: dict, *, signed: bool = False) -> bytes:
    payload = deepcopy(value)
    payload.pop("content_hash", None)
    if signed:
        payload.pop("signature", None)
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _with_content_hash(value: dict) -> dict:
    result = deepcopy(value)
    result["content_hash"] = hashlib.sha256(_canonical_bytes(result)).hexdigest()
    return result


def _sign_receipt(value: dict, private_key, signer_id: str) -> dict:
    result = deepcopy(value)
    result["content_hash"] = hashlib.sha256(
        _canonical_bytes(result, signed=True)
    ).hexdigest()
    signature = private_key.sign(_canonical_bytes(result, signed=True))
    result["signature"] = {
        "algorithm": "ed25519",
        "signer_id": signer_id,
        "value": base64.b64encode(signature).decode("ascii"),
    }
    return result


def _write_json(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _file_hashes(paths: list[Path]) -> dict[str, str]:
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def _diff_paths(left, right, path="$") -> list[str]:
    if type(left) is not type(right):
        return [path]
    if isinstance(left, dict):
        result = []
        for key in sorted(set(left) | set(right)):
            result.extend(_diff_paths(left.get(key), right.get(key), f"{path}.{key}"))
        return result
    if isinstance(left, list):
        result = []
        for index, (a, b) in enumerate(zip(left, right)):
            result.extend(_diff_paths(a, b, f"{path}[{index}]"))
        if len(left) != len(right):
            result.append(f"{path}.length")
        return result
    return [] if left == right else [path]


def test_coverage_presentation_removes_only_documented_store_timestamps():
    raw = {
        "summary": {"full": 1},
        "discovery_summary": {"functions": 1},
        "desired_summary": {"functions": 1, "hard_gaps": 0},
        "functions": [{
            "function": {"id": "function:a", "created_at": "volatile", "metadata": {"created_at": "keep"}},
            "carriers": [{"id": "carrier:a", "created_at": "volatile", "metadata": {"observed_at": "keep"}}],
            "desired": [{"id": "edge:d", "created_at": "volatile", "effective_at": "keep"}],
            "actual": [{"id": "edge:a", "created_at": "volatile", "metadata": {"expires_at": "keep"}}],
        }],
    }

    view, count = _coverage_presentation(raw)

    assert count == 4
    assert raw["functions"][0]["function"]["created_at"] == "volatile"
    assert view["functions"][0]["function"]["metadata"]["created_at"] == "keep"
    assert view["functions"][0]["carriers"][0]["metadata"]["observed_at"] == "keep"
    assert view["functions"][0]["desired"][0]["effective_at"] == "keep"
    assert view["functions"][0]["actual"][0]["metadata"]["expires_at"] == "keep"
    assert sorted(_diff_paths(raw, view)) == sorted([
        "$.functions[0].function.created_at",
        "$.functions[0].carriers[0].created_at",
        "$.functions[0].desired[0].created_at",
        "$.functions[0].actual[0].created_at",
    ])


def test_documented_presentation_paths_are_intentionally_narrow():
    assert PRESENTATION_OMISSIONS == (
        "functions[].function.created_at",
        "functions[].carriers[].created_at",
        "functions[].desired[].created_at",
        "functions[].actual[].created_at",
    )


@pytest.fixture(scope="module")
def native_checkout() -> Path:
    raw = os.environ.get("OCEAN_SYSTEM_EXPLORER_CHECKOUT")
    if not raw:
        pytest.skip("set OCEAN_SYSTEM_EXPLORER_CHECKOUT for the pinned native-provider acceptance")
    checkout = Path(raw).expanduser().resolve()
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=checkout, capture_output=True, text=True, check=True
    ).stdout.strip()
    if head != PINNED_PROVIDER:
        pytest.skip(f"native provider is {head}, expected {PINNED_PROVIDER}")
    return checkout


@pytest.fixture()
def native_case(tmp_path: Path, native_checkout: Path) -> dict:
    crypto = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
    serialization = pytest.importorskip("cryptography.hazmat.primitives.serialization")
    private_key = crypto.Ed25519PrivateKey.generate()
    workspace = tmp_path / "workspace"
    provider = workspace / "modules" / "software-endpoint-registry"
    provider.parent.mkdir(parents=True)
    subprocess.run(
        ["git", "clone", "--no-hardlinks", str(native_checkout), str(provider)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "checkout", "--detach", PINNED_PROVIDER],
        cwd=provider,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "remote", "set-url", "origin", "https://github.com/ellmos-ai/system-explorer.git"],
        cwd=provider,
        check=True,
    )

    bindings = json.loads(DEFAULT_COMPONENT_BINDINGS.read_text(encoding="utf-8"))
    binding = bindings["bindings"][PROVIDER_BINDING_REF]
    install = {
        "schema": "ellmos.open-ocean-install-state.v1",
        "recorded_at": "2026-07-30T19:00:00Z",
        "workspace": str(workspace.resolve()),
        "plan": {
            "transaction": {
                "components": [{
                    "ref": PROVIDER_BINDING_REF,
                    "detail": {"binding": deepcopy(binding)},
                }],
                "fetch": [{
                    "ref": PROVIDER_BINDING_REF,
                    "action": "present-pinned-provider",
                    "detail": {"dest": str(provider.resolve())},
                }],
            }
        },
        "projection": {},
    }
    install_path = _write_json(workspace / "ocean.install.json", install)

    resolution = json.loads(
        (provider / "tests" / "fixtures" / "resolution.v1.json").read_text(encoding="utf-8")
    )
    component = resolution["bundles"][0]["components"][0]
    component["provides"] = ["function.required"]
    component["consumes"] = []
    component["registry_resolution"] = {
        "class": "native-binding",
        "source": "module-registry",
        "record_id": "required-provider",
    }
    resolution["bundles"][0]["components"] = [component]
    resolution["functions"] = ["function.required"]
    resolution["component_registry"] = {
        "schema": "ellmos.component-registry-bindings.v1",
        "id": "fixture-component-registry",
        "version": "1.0.0",
        "content_hash": REGISTRY_HASH,
        "activation": {},
        "source_verification": "verified",
    }
    resolution = _with_content_hash(resolution)
    resolution_path = _write_json(tmp_path / "resolution.json", resolution)

    public_key_path = tmp_path / "producer.pem"
    public_key_path.write_bytes(private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    signer_id = "signer:controlcenter-test-host"
    trust = _with_content_hash({
        "schema": "system-explorer.receipt-trust-store.v1",
        "version": "1.0.0",
        "signers": [{
            "signer_id": signer_id,
            "algorithm": "ed25519",
            "public_key_path": public_key_path.name,
            "public_key_sha256": hashlib.sha256(public_key_path.read_bytes()).hexdigest(),
            "allowed_receipt_schemas": ["ellmos.actual-self-component-receipt.v1"],
            "allowed_actor_refs": ["access_surface:controlcenter"],
            "allowed_adapter_ids": ["controlcenter.native-list-tools.v1"],
            "allowed_host_ids": ["TEST-HOST"],
            "allowed_authority_types": [],
            "allowed_delegation_refs": [],
            "max_ttl_seconds": 10800,
        }],
    })
    trust_path = _write_json(tmp_path / "receipt-trust.json", trust)

    base_receipt = {
        "schema": "ellmos.actual-self-component-receipt.v1",
        "receipt_id": "receipt-module-required-provider",
        "component_ref": "module:required-provider",
        "component_type": "module",
        "scope": {
            "system_id": resolution["system"]["id"],
            "instance_id": resolution["instance"]["instance_id"],
            "host_id": resolution["instance"]["host_id"],
        },
        "registry_binding": {
            "registry_content_hash": REGISTRY_HASH,
            "source": "module-registry",
            "record_id": "required-provider",
        },
        "producer": {
            "ref": "access_surface:controlcenter",
            "adapter_id": "controlcenter.native-list-tools.v1",
            "signer_id": signer_id,
            "host_id": "TEST-HOST",
            "probe_kind": "native-runtime-readback",
        },
        "observed_at": "2026-07-30T19:55:00Z",
        "expires_at": EXPIRES_AT,
        "functions": [{
            "id": "function.required",
            "status": "full",
            "probe_id": "controlcenter.list-tools.v1",
            "readback_sha256": "1" * 64,
        }],
    }

    def write_receipt(name: str, mutate=None, *, key=private_key) -> Path:
        value = deepcopy(base_receipt)
        if mutate:
            mutate(value)
        return _write_json(tmp_path / name, _sign_receipt(value, key, signer_id))

    receipt_path = write_receipt("valid.actual.json")
    return {
        "workspace": workspace,
        "provider": provider,
        "resolution": resolution_path,
        "receipt": receipt_path,
        "trust": trust_path,
        "trust_sha256": hashlib.sha256(trust_path.read_bytes()).hexdigest(),
        "public_key": public_key_path,
        "install": install_path,
        "write_receipt": write_receipt,
        "base_receipt": base_receipt,
        "private_key": private_key,
        "signer_id": signer_id,
    }


def _inspect(case: dict, *, receipts: list[Path] | None = None, **overrides):
    arguments = {
        "workspace": case["workspace"],
        "resolution": case["resolution"],
        "receipts": [case["receipt"]] if receipts is None else receipts,
        "trust_store": case["trust"],
        "trust_store_sha256": case["trust_sha256"],
        "expected_instance_id": "fixture-development-system@TEST-HOST",
        "expected_host_id": "TEST-HOST",
        "evaluated_at": EVALUATED_AT,
        "expected_provider_version": DEFAULT_PROVIDER_VERSION,
    }
    arguments.update(overrides)
    return inspect_workspace(**arguments)


def _nested_resolution(case: dict, tmp_path: Path) -> Path:
    value = json.loads(case["resolution"].read_text(encoding="utf-8"))
    child = deepcopy(value)
    child.pop("instance", None)
    child["system"] = {**child["system"], "id": "fixture-child-system"}
    child["subsystems"] = []
    child = _with_content_hash(child)
    value["subsystems"] = [{
        "role": "child-service",
        "profile": "default",
        "source_ref": {"path": "systems/child.json", "version": "1.0.0"},
        "resolution": child,
    }]
    return _write_json(tmp_path / "nested-resolution.json", _with_content_hash(value))


def _native_raw_coverage(case: dict, output: Path) -> dict:
    script = output.with_suffix(".py")
    script.write_text(
        """import json, sys
from pathlib import Path
provider, resolution, receipt, trust, trust_sha, output = map(Path, sys.argv[1:7])
sys.path.insert(0, str(provider / 'src'))
from system_explorer.actual_self import import_actual_self_receipt
from system_explorer.coverage import coverage_report
from system_explorer.receipt_trust import load_receipt_trust_store
from system_explorer.resolution_bridge import import_resolution
from system_explorer.store import Store
trust_store = load_receipt_trust_store({'_base': str(trust.parent), 'receipt_trust_store': trust.name, 'receipt_trust_store_sha256': trust_sha.name})
resolution_value = json.loads(resolution.read_text(encoding='utf-8'))
with Store(output.with_suffix('.db')) as store:
    import_resolution(resolution, store)
    import_actual_self_receipt(receipt, resolution_value, store, evaluated_at='2026-07-30T20:00:00Z', trust_store=trust_store)
    value = coverage_report(store)
output.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\\n', encoding='utf-8')
""",
        encoding="utf-8",
    )
    # The script accepts the SHA as a Path solely to avoid shell quoting; `.name` restores the value.
    subprocess.run(
        [
            sys.executable,
            str(script),
            str(case["provider"]),
            str(case["resolution"]),
            str(case["receipt"]),
            str(case["trust"]),
            case["trust_sha256"],
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(output.read_text(encoding="utf-8"))


def test_native_signed_receipt_is_read_only_and_byte_deterministic(native_case: dict, tmp_path: Path):
    inputs = [
        native_case["resolution"],
        native_case["receipt"],
        native_case["trust"],
        native_case["public_key"],
        native_case["install"],
    ]
    before_hashes = _file_hashes(inputs)
    before_status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=native_case["provider"], capture_output=True, text=True, check=True,
    ).stdout
    before_workspace = sorted(str(path.relative_to(native_case["workspace"])) for path in native_case["workspace"].rglob("*"))

    first = _inspect(native_case)
    time.sleep(1.2)
    second = _inspect(native_case)

    assert first["status"] == "valid-no-required-gaps"
    assert first["provider"]["binding_ref"] == "module:software-endpoint-registry"
    assert first["provider"]["provider_id"] == "system-explorer"
    assert first["provider"]["package"] == "system_explorer"
    assert first["provider"]["commit"] == PINNED_PROVIDER
    assert first["resolution_projection"] == {
        "projection_scope": "full",
        "subsystems_omitted": 0,
    }
    assert json.dumps(first, ensure_ascii=False, sort_keys=True, separators=(",", ":")) == json.dumps(
        second, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    assert _file_hashes(inputs) == before_hashes
    assert subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=native_case["provider"], capture_output=True, text=True, check=True,
    ).stdout == before_status == ""
    assert sorted(str(path.relative_to(native_case["workspace"])) for path in native_case["workspace"].rglob("*")) == before_workspace

    raw = _native_raw_coverage(native_case, tmp_path / "raw-coverage.json")
    diff = _diff_paths(raw, first["coverage"])
    assert diff
    assert all(
        re.fullmatch(
            r"\$\.functions\[\d+\]\.(?:function|carriers\[\d+\]|desired\[\d+\]|actual\[\d+\])\.created_at",
            path,
        )
        for path in diff
    )
    assert first["presentation"]["omitted_field_count"] == len(diff)


def test_cli_without_outer_bytecode_guard_does_not_touch_provider_tree(native_case: dict):
    before_tree = sorted(
        str(path.relative_to(native_case["provider"]))
        for path in native_case["provider"].rglob("*")
    )
    env = dict(os.environ)
    env.pop("PYTHONDONTWRITEBYTECODE", None)
    command = [
        sys.executable,
        str(REPO_ROOT / "ocean.py"),
        "inspect",
        "--workspace",
        str(native_case["workspace"]),
        "--resolution",
        str(native_case["resolution"]),
        "--receipt",
        str(native_case["receipt"]),
        "--trust-store",
        str(native_case["trust"]),
        "--trust-store-sha256",
        native_case["trust_sha256"],
        "--expected-instance-id",
        "fixture-development-system@TEST-HOST",
        "--expected-host-id",
        "TEST-HOST",
        "--evaluated-at",
        EVALUATED_AT,
        "--json",
    ]

    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["status"] == "valid-no-required-gaps"
    assert sorted(
        str(path.relative_to(native_case["provider"]))
        for path in native_case["provider"].rglob("*")
    ) == before_tree
    assert subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=native_case["provider"], capture_output=True, text=True, check=True,
    ).stdout == ""


def test_native_subsystem_resolution_requires_explicit_root_only_scope(
    native_case: dict,
    tmp_path: Path,
):
    nested = _nested_resolution(native_case, tmp_path)

    with pytest.raises(InspectError) as raised:
        _inspect(native_case, resolution=nested)

    assert raised.value.code == "native-provider-rejected"
    assert "subsystems are not importable" in str(raised.value)

    report = _inspect(
        native_case,
        resolution=nested,
        root_only_resolution=True,
    )

    assert report["status"] == "valid-no-required-gaps"
    assert report["resolution_projection"] == {
        "projection_scope": "root-only",
        "subsystems_omitted": 1,
    }


def test_cli_subsystem_resolution_requires_explicit_root_only_flag(
    native_case: dict,
    tmp_path: Path,
):
    nested = _nested_resolution(native_case, tmp_path)
    command = [
        sys.executable,
        str(REPO_ROOT / "ocean.py"),
        "inspect",
        "--workspace",
        str(native_case["workspace"]),
        "--resolution",
        str(nested),
        "--receipt",
        str(native_case["receipt"]),
        "--trust-store",
        str(native_case["trust"]),
        "--trust-store-sha256",
        native_case["trust_sha256"],
        "--expected-instance-id",
        "fixture-development-system@TEST-HOST",
        "--expected-host-id",
        "TEST-HOST",
        "--evaluated-at",
        EVALUATED_AT,
        "--json",
    ]

    rejected = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    accepted = subprocess.run(
        [*command[:-1], "--root-only-resolution", "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert rejected.returncode == 2
    assert json.loads(rejected.stderr)["error"]["code"] == "native-provider-rejected"
    assert accepted.returncode == 0, accepted.stderr
    assert json.loads(accepted.stdout)["resolution_projection"] == {
        "projection_scope": "root-only",
        "subsystems_omitted": 1,
    }


def test_cli_rejects_invalid_resolution_object_shape_without_traceback(
    native_case: dict,
    tmp_path: Path,
):
    resolution = json.loads(native_case["resolution"].read_text(encoding="utf-8"))
    resolution["instance"] = ["invalid-object-shape"]
    invalid_resolution = _write_json(tmp_path / "invalid-resolution.json", resolution)
    command = [
        sys.executable,
        str(REPO_ROOT / "ocean.py"),
        "inspect",
        "--workspace",
        str(native_case["workspace"]),
        "--resolution",
        str(invalid_resolution),
        "--receipt",
        str(native_case["receipt"]),
        "--trust-store",
        str(native_case["trust"]),
        "--trust-store-sha256",
        native_case["trust_sha256"],
        "--expected-instance-id",
        "fixture-development-system@TEST-HOST",
        "--expected-host-id",
        "TEST-HOST",
        "--evaluated-at",
        EVALUATED_AT,
        "--json",
    ]

    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert "Traceback" not in completed.stderr
    rejection = json.loads(completed.stderr)
    assert rejection["status"] == "rejected"
    assert rejection["error"]["code"] == "resolution-invalid"


def test_cli_rejects_non_object_component_bindings_without_traceback(
    native_case: dict,
    tmp_path: Path,
):
    invalid_bindings = tmp_path / "invalid-component-bindings.json"
    invalid_bindings.write_text("[]\n", encoding="utf-8")
    command = [
        sys.executable,
        str(REPO_ROOT / "ocean.py"),
        "inspect",
        "--workspace",
        str(native_case["workspace"]),
        "--resolution",
        str(native_case["resolution"]),
        "--receipt",
        str(native_case["receipt"]),
        "--trust-store",
        str(native_case["trust"]),
        "--trust-store-sha256",
        native_case["trust_sha256"],
        "--expected-instance-id",
        "fixture-development-system@TEST-HOST",
        "--expected-host-id",
        "TEST-HOST",
        "--evaluated-at",
        EVALUATED_AT,
        "--component-bindings",
        str(invalid_bindings),
        "--json",
    ]

    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert "Traceback" not in completed.stderr
    rejection = json.loads(completed.stderr)
    assert rejection["status"] == "rejected"
    assert rejection["error"]["code"] == "input-invalid"


@pytest.mark.parametrize(
    "path",
    [
        ("plan",),
        ("plan", "transaction"),
        ("plan", "transaction", "components", 0, "detail"),
        ("plan", "transaction", "components", 0, "detail", "binding"),
        ("plan", "transaction", "fetch", 0, "detail"),
    ],
    ids=("plan", "transaction", "component-detail", "recorded-binding", "fetch-detail"),
)
def test_install_state_object_shapes_fail_closed(native_case: dict, path: tuple):
    install = json.loads(native_case["install"].read_text(encoding="utf-8"))
    cursor = install
    for part in path[:-1]:
        cursor = cursor[part]
    cursor[path[-1]] = ["invalid-object-shape"]
    _write_json(native_case["install"], install)

    with pytest.raises(InspectError) as raised:
        _inspect(native_case)

    assert raised.value.code == "install-state-invalid"


def test_native_no_receipts_is_valid_report_with_required_gap(native_case: dict):
    report = _inspect(native_case, receipts=[])
    assert report["status"] == "valid-with-required-gaps"
    assert report["coverage"]["desired_summary"]["hard_gaps"] == 1


@pytest.mark.parametrize(
    ("name", "mutate"),
    [
        ("expired", lambda value: value.__setitem__("expires_at", "2026-07-30T19:59:59Z")),
        ("wrong-host", lambda value: value["scope"].__setitem__("host_id", "OTHER-HOST")),
        ("wrong-provider", lambda value: value.__setitem__("component_ref", "module:other-provider")),
        ("unknown-field", lambda value: value.__setitem__("unexpected", True)),
    ],
)
def test_native_receipt_rejections(native_case: dict, name: str, mutate):
    path = native_case["write_receipt"](f"{name}.actual.json", mutate)
    with pytest.raises(InspectError) as raised:
        _inspect(native_case, receipts=[path])
    assert raised.value.code == "native-provider-rejected"


def test_native_bad_signature_and_mixed_set_fail_closed(native_case: dict):
    value = json.loads(native_case["receipt"].read_text(encoding="utf-8"))
    value["signature"]["value"] = base64.b64encode(b"0" * 64).decode("ascii")
    forged = _write_json(native_case["receipt"].parent / "forged.actual.json", value)
    protected_inputs = [
        native_case["resolution"],
        native_case["receipt"],
        forged,
        native_case["trust"],
        native_case["public_key"],
        native_case["install"],
    ]
    before_hashes = _file_hashes(protected_inputs)
    before_workspace = sorted(
        str(path.relative_to(native_case["workspace"]))
        for path in native_case["workspace"].rglob("*")
    )
    before_provider_status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=native_case["provider"], capture_output=True, text=True, check=True,
    ).stdout

    for receipts in ([forged], [native_case["receipt"], forged]):
        with pytest.raises(InspectError) as raised:
            _inspect(native_case, receipts=list(receipts))
        assert raised.value.code == "native-provider-rejected"

    assert _file_hashes(protected_inputs) == before_hashes
    assert sorted(
        str(path.relative_to(native_case["workspace"]))
        for path in native_case["workspace"].rglob("*")
    ) == before_workspace
    assert subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=native_case["provider"], capture_output=True, text=True, check=True,
    ).stdout == before_provider_status == ""


def test_native_trust_pin_and_provider_version_mismatch_fail_closed(native_case: dict):
    with pytest.raises(InspectError) as trust_error:
        _inspect(native_case, trust_store_sha256="0" * 64)
    assert trust_error.value.code == "native-provider-rejected"

    with pytest.raises(InspectError) as version_error:
        _inspect(native_case, expected_provider_version="9.9.9")
    assert version_error.value.code == "provider-version-mismatch"


def test_native_resolution_scope_mismatch_fails_before_provider_import(native_case: dict):
    with pytest.raises(InspectError) as raised:
        _inspect(native_case, expected_host_id="OTHER-HOST")
    assert raised.value.code == "resolution-scope-mismatch"


def test_rejection_report_always_records_evaluation_time():
    error = InspectError("test-rejection", "abgewiesen")

    implicit = rejection_report(error, None)
    explicit = rejection_report(error, EVALUATED_AT)

    assert implicit["evaluated_at"].endswith("Z")
    assert explicit["evaluated_at"] == EVALUATED_AT
