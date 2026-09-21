"""Read-only OCEAN adapter for System Explorer's native coverage APIs."""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
import tempfile
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

from tools.fetch_place import FetchError, verify_bound_provider
from tools.ocean_lifecycle import INSTALL_STATE
from tools.resolve_bundles import DEFAULT_COMPONENT_BINDINGS, ResolveError, load_component_bindings


INSPECT_SCHEMA = "ellmos.open-ocean-inspect.v1"
PROVIDER_BINDING_REF = "module:software-endpoint-registry"
PROVIDER_ID = "system-explorer"
PROVIDER_PACKAGE = "system_explorer"
PROVIDER_CLI = "system-explorer"
DEFAULT_PROVIDER_VERSION = "0.4.0"
PRESENTATION_OMISSIONS = (
    "functions[].function.created_at",
    "functions[].carriers[].created_at",
    "functions[].desired[].created_at",
    "functions[].actual[].created_at",
)


class InspectError(RuntimeError):
    """Stable Ocean-level rejection without reclassifying native findings."""

    def __init__(self, code: str, message: str, *, exit_code: int = 2) -> None:
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code


@dataclass(frozen=True)
class FileSnapshot:
    path: Path
    sha256: str


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _snapshot(path: Path, label: str) -> FileSnapshot:
    candidate = Path(path).expanduser().resolve()
    try:
        source = candidate.read_bytes()
    except OSError as exc:
        raise InspectError("input-unreadable", f"{label} ist nicht lesbar: {exc}") from exc
    if not candidate.is_file():
        raise InspectError("input-unreadable", f"{label} ist keine reguläre Datei")
    return FileSnapshot(candidate, _sha256_bytes(source))


def _assert_snapshots_unchanged(snapshots: list[FileSnapshot]) -> None:
    for snapshot in snapshots:
        try:
            observed = _sha256_bytes(snapshot.path.read_bytes())
        except OSError as exc:
            raise InspectError(
                "input-changed-during-inspection",
                f"Eingabe wurde während der Prüfung unlesbar: {exc}",
            ) from exc
        if observed != snapshot.sha256:
            raise InspectError(
                "input-changed-during-inspection",
                "Eingabe wurde während der Prüfung verändert",
            )


def _normalise_evaluated_at(value: str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InspectError(
            "invalid-evaluation-time",
            "--evaluated-at muss ein ISO-8601-Zeitpunkt mit Zeitzone sein",
        ) from exc
    if parsed.tzinfo is None:
        raise InspectError(
            "invalid-evaluation-time",
            "--evaluated-at muss eine Zeitzone enthalten",
        )
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json_snapshot(snapshot: FileSnapshot, label: str) -> dict[str, Any]:
    try:
        value = json.loads(snapshot.path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InspectError("input-invalid", f"{label} ist kein lesbares JSON-Objekt: {exc}") from exc
    if not isinstance(value, dict):
        raise InspectError("input-invalid", f"{label} muss ein JSON-Objekt sein")
    return value


def _same_path(left: str | Path, right: Path) -> bool:
    try:
        return Path(left).expanduser().resolve() == right.resolve()
    except (OSError, RuntimeError, TypeError, ValueError):
        return False


def _provider_from_install(
    workspace: Path,
    component_bindings: Path,
) -> tuple[Path, dict[str, Any], dict[str, Any], list[FileSnapshot]]:
    workspace = Path(workspace).expanduser().resolve()
    install_snapshot = _snapshot(workspace / INSTALL_STATE, "OCEAN-Installationsstand")
    bindings_snapshot = _snapshot(component_bindings, "Komponenten-Binding")
    install = _read_json_snapshot(install_snapshot, "OCEAN-Installationsstand")
    if install.get("schema") != "ellmos.open-ocean-install-state.v1":
        raise InspectError("install-state-invalid", "Nicht unterstützter OCEAN-Installationsstand")
    if not _same_path(install.get("workspace", ""), workspace):
        raise InspectError("install-state-invalid", "Installationsstand gehört zu einem anderen Workspace")
    try:
        bindings = load_component_bindings(bindings_snapshot.path)
    except ResolveError as exc:
        raise InspectError("provider-binding-invalid", str(exc)) from exc
    binding = (bindings.get("bindings") or {}).get(PROVIDER_BINDING_REF)
    if not isinstance(binding, dict):
        raise InspectError(
            "provider-binding-missing",
            f"Binding {PROVIDER_BINDING_REF!r} fehlt",
        )
    if binding.get("catalog_id") != PROVIDER_ID:
        raise InspectError(
            "provider-binding-invalid",
            f"Binding-Alias {PROVIDER_BINDING_REF!r} verweist nicht auf {PROVIDER_ID!r}",
        )

    transaction = ((install.get("plan") or {}).get("transaction") or {})
    components = transaction.get("components")
    fetches = transaction.get("fetch")
    if not isinstance(components, list) or not isinstance(fetches, list):
        raise InspectError("install-state-invalid", "Installationsstand enthält keinen Transaktionsbeleg")
    matched = [item for item in components if isinstance(item, dict) and item.get("ref") == PROVIDER_BINDING_REF]
    if len(matched) != 1:
        raise InspectError(
            "provider-installation-unproven",
            f"Installationsstand muss genau eine Komponente {PROVIDER_BINDING_REF!r} belegen",
        )
    recorded_binding = ((matched[0].get("detail") or {}).get("binding") or {})
    for field, expected in binding.items():
        if recorded_binding.get(field) != expected:
            raise InspectError(
                "provider-installation-drift",
                f"Installierter Provider weicht im Binding-Feld {field!r} ab",
            )
    provider_root = workspace / "modules" / str(binding["placement_id"])
    matching_fetches = [
        item for item in fetches
        if isinstance(item, dict) and item.get("ref") == PROVIDER_BINDING_REF
    ]
    if len(matching_fetches) != 1:
        raise InspectError("provider-installation-unproven", "Provider-Fetchbeleg fehlt oder ist mehrdeutig")
    fetch = matching_fetches[0]
    if fetch.get("action") not in {"fetched", "present-pinned-provider"}:
        raise InspectError("provider-installation-unproven", "Provider wurde nicht gepinnt bereitgestellt")
    if not _same_path((fetch.get("detail") or {}).get("dest", ""), provider_root):
        raise InspectError("provider-installation-drift", "Provider-Fetchbeleg zeigt auf einen anderen Pfad")
    return provider_root, binding, bindings, [install_snapshot, bindings_snapshot]


def _verify_provider_identity(
    provider_root: Path,
    binding: dict[str, Any],
    expected_version: str,
) -> tuple[dict[str, Any], FileSnapshot]:
    try:
        proof = verify_bound_provider(provider_root, binding)
    except FetchError as exc:
        raise InspectError("provider-verification-failed", str(exc)) from exc
    manifest_snapshot = _snapshot(provider_root / binding["provider_manifest"], "Provider-Manifest")
    manifest = _read_json_snapshot(manifest_snapshot, "Provider-Manifest")
    entrypoints = manifest.get("entrypoints") or {}
    if (
        proof.get("provider_id") != PROVIDER_ID
        or manifest.get("id") != PROVIDER_ID
        or manifest.get("package") != PROVIDER_PACKAGE
        or not str(entrypoints.get("cli") or "").startswith(PROVIDER_CLI + " ")
    ):
        raise InspectError(
            "provider-identity-mismatch",
            "Binding-Alias löst nicht auf die erwartete System-Explorer-Repo-/Paket-/CLI-Identität auf",
        )
    observed_version = manifest.get("version")
    if observed_version != expected_version:
        raise InspectError(
            "provider-version-mismatch",
            f"System-Explorer-Version {observed_version!r} entspricht nicht {expected_version!r}",
        )
    return manifest, manifest_snapshot


@contextmanager
def _native_provider_api(provider_root: Path) -> Iterator[SimpleNamespace]:
    source_root = (provider_root / "src").resolve()
    package_root = (source_root / PROVIDER_PACKAGE).resolve()
    if not package_root.is_dir():
        raise InspectError("provider-api-missing", "System-Explorer-Paket fehlt im geprüften Checkout")
    existing = {
        name: module
        for name, module in sys.modules.items()
        if name == PROVIDER_PACKAGE or name.startswith(PROVIDER_PACKAGE + ".")
    }
    for module in existing.values():
        module_file = getattr(module, "__file__", None)
        if module_file is None or not Path(module_file).resolve().is_relative_to(package_root):
            raise InspectError(
                "provider-import-conflict",
                "Ein nicht zum geprüften Checkout gehörendes System-Explorer-Modul ist bereits geladen",
            )
    original_path = list(sys.path)
    loaded_before = set(sys.modules)
    original_dont_write_bytecode = sys.dont_write_bytecode
    try:
        # The verified checkout is a read-only provider input.  Protect it at
        # the import boundary even when the outer `ocean` process was not
        # started with `-B` or PYTHONDONTWRITEBYTECODE.
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(source_root))
        actual_self = importlib.import_module("system_explorer.actual_self")
        coverage = importlib.import_module("system_explorer.coverage")
        receipt_trust = importlib.import_module("system_explorer.receipt_trust")
        resolution_bridge = importlib.import_module("system_explorer.resolution_bridge")
        store = importlib.import_module("system_explorer.store")
        modules = (actual_self, coverage, receipt_trust, resolution_bridge, store)
        if any(
            not Path(str(module.__file__)).resolve().is_relative_to(package_root)
            for module in modules
        ):
            raise InspectError("provider-import-conflict", "Native API wurde nicht aus dem geprüften Checkout geladen")
        api = SimpleNamespace(
            import_actual_self_receipt=actual_self.import_actual_self_receipt,
            coverage_report=coverage.coverage_report,
            load_receipt_trust_store=receipt_trust.load_receipt_trust_store,
            import_resolution=resolution_bridge.import_resolution,
            Store=store.Store,
        )
        yield api
    except InspectError:
        raise
    except (AttributeError, ImportError, ModuleNotFoundError) as exc:
        raise InspectError("provider-api-missing", f"Native System-Explorer-API fehlt: {exc}") from exc
    finally:
        sys.dont_write_bytecode = original_dont_write_bytecode
        sys.path[:] = original_path
        for name in list(sys.modules):
            if (
                name not in loaded_before
                and (name == PROVIDER_PACKAGE or name.startswith(PROVIDER_PACKAGE + "."))
            ):
                sys.modules.pop(name, None)


def _coverage_presentation(raw: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Drop only provider Store bookkeeping timestamps from documented records."""
    view = deepcopy(raw)
    removed = 0
    rows = view.get("functions")
    if not isinstance(rows, list):
        raise InspectError("native-provider-contract-error", "Native Coverage enthält keine Funktionsliste")
    for row in rows:
        if not isinstance(row, dict):
            raise InspectError("native-provider-contract-error", "Native Coverage enthält einen ungültigen Funktionssatz")
        function = row.get("function")
        if isinstance(function, dict) and "created_at" in function:
            function.pop("created_at")
            removed += 1
        for key in ("carriers", "desired", "actual"):
            records = row.get(key)
            if not isinstance(records, list):
                raise InspectError("native-provider-contract-error", f"Native Coverage enthält kein gültiges Feld {key!r}")
            for record in records:
                if isinstance(record, dict) and "created_at" in record:
                    record.pop("created_at")
                    removed += 1
    return view, removed


def _trust_key_snapshots(trust_store: Any) -> list[FileSnapshot]:
    snapshots = []
    for signer in trust_store.signers.values():
        key_path = (trust_store.path.parent / str(signer["public_key_path"])).resolve()
        snapshots.append(_snapshot(key_path, "Vertrauensschlüssel"))
    return snapshots


def inspect_workspace(
    *,
    workspace: Path,
    resolution: Path,
    receipts: list[Path],
    trust_store: Path,
    trust_store_sha256: str,
    expected_instance_id: str,
    expected_host_id: str,
    evaluated_at: str | None = None,
    expected_provider_version: str = DEFAULT_PROVIDER_VERSION,
    component_bindings: Path = DEFAULT_COMPONENT_BINDINGS,
) -> dict[str, Any]:
    """Verify one installed provider and return its read-only native coverage."""
    evaluation_time = _normalise_evaluated_at(evaluated_at)
    provider_root, binding, bindings, stable_snapshots = _provider_from_install(
        workspace, component_bindings
    )
    manifest, manifest_snapshot = _verify_provider_identity(
        provider_root, binding, expected_provider_version
    )
    stable_snapshots.append(manifest_snapshot)

    resolution_snapshot = _snapshot(resolution, "Resolution")
    receipt_snapshots = [_snapshot(path, "Actual-Self-Receipt") for path in receipts]
    trust_snapshot = _snapshot(trust_store, "Receipt-Trust-Store")
    all_input_snapshots = stable_snapshots + [resolution_snapshot, trust_snapshot, *receipt_snapshots]
    resolution_value = _read_json_snapshot(resolution_snapshot, "Resolution")
    system = resolution_value.get("system") or {}
    instance = resolution_value.get("instance") or {}
    if instance.get("instance_id") != expected_instance_id or instance.get("host_id") != expected_host_id:
        raise InspectError(
            "resolution-scope-mismatch",
            "Resolution entspricht nicht der erwarteten Instanz-/Host-Bindung",
        )

    with _native_provider_api(provider_root) as api:
        try:
            native_trust = api.load_receipt_trust_store({
                "_base": str(trust_snapshot.path.parent),
                "receipt_trust_store": trust_snapshot.path.name,
                "receipt_trust_store_sha256": trust_store_sha256,
            })
            key_snapshots = _trust_key_snapshots(native_trust)
            all_input_snapshots.extend(key_snapshots)
            ordered_receipts = sorted(receipt_snapshots, key=lambda item: (item.sha256, str(item.path)))
            with tempfile.TemporaryDirectory(prefix="ocean-inspect-") as temporary:
                with api.Store(Path(temporary) / "system-explorer.db") as store:
                    store.begin_immediate()
                    try:
                        api.import_resolution(resolution_snapshot.path, store, defer_commit=True)
                        for receipt in ordered_receipts:
                            api.import_actual_self_receipt(
                                receipt.path,
                                resolution_value,
                                store,
                                evaluated_at=evaluation_time,
                                trust_store=native_trust,
                                defer_commit=True,
                            )
                        store.commit()
                    except Exception:
                        store.rollback()
                        raise
                    raw_coverage = api.coverage_report(store)
        except InspectError:
            raise
        except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise InspectError(
                "native-provider-rejected",
                f"System Explorer hat die Eingabe abgewiesen ({type(exc).__name__}: {exc})",
            ) from exc

    _assert_snapshots_unchanged(all_input_snapshots)
    try:
        verify_bound_provider(provider_root, binding)
    except FetchError as exc:
        raise InspectError("provider-changed-during-inspection", str(exc)) from exc
    coverage, omitted_count = _coverage_presentation(raw_coverage)
    hard_gaps = ((coverage.get("desired_summary") or {}).get("hard_gaps"))
    if not isinstance(hard_gaps, int) or isinstance(hard_gaps, bool):
        raise InspectError("native-provider-contract-error", "Native Coverage enthält keine gültige Hard-Gap-Zahl")
    status = "valid-with-required-gaps" if hard_gaps else "valid-no-required-gaps"
    receipt_hashes = sorted(snapshot.sha256 for snapshot in receipt_snapshots)
    return {
        "schema": INSPECT_SCHEMA,
        "status": status,
        "evaluated_at": evaluation_time,
        "scope": {
            "system_id": system.get("id"),
            "instance_id": expected_instance_id,
            "host_id": expected_host_id,
        },
        "provider": {
            "binding_ref": PROVIDER_BINDING_REF,
            "binding_manifest_content_hash": bindings.get("content_hash"),
            "provider_id": PROVIDER_ID,
            "package": PROVIDER_PACKAGE,
            "cli": PROVIDER_CLI,
            "version": manifest["version"],
            "repository": binding["repository"],
            "commit": binding["commit"],
            "manifest_sha256": manifest_snapshot.sha256,
        },
        "inputs": {
            "resolution_sha256": resolution_snapshot.sha256,
            "receipt_sha256": receipt_hashes,
            "trust_store_sha256": trust_snapshot.sha256,
        },
        "presentation": {
            "kind": "native-coverage-presentation-view",
            "native_function": "system_explorer.coverage.coverage_report",
            "omitted_store_fields": list(PRESENTATION_OMISSIONS),
            "omitted_field_count": omitted_count,
        },
        "coverage": coverage,
    }


def rejection_report(error: InspectError, evaluated_at: str | None) -> dict[str, Any]:
    report_time = evaluated_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "schema": INSPECT_SCHEMA,
        "status": "rejected",
        "evaluated_at": report_time,
        "error": {"code": error.code, "message": str(error)},
    }
