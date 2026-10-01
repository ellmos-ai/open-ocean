"""Choose one operator UI from already verified, immutable input metadata."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

LITE_PROVIDER_ID = "ellmos-unified-gui"
FULL_SURFACES = frozenset({
    "activity", "agents-board", "tasks-board", "skills-board", "chat",
    "settings", "assets", "navigation", "authorization", "errors",
})


class OperatorUISelectionError(ValueError):
    """A recorded choice or a provider binding cannot be used."""
    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(detail)


@dataclass(frozen=True)
class RecordedUIChoice:
    decision_id: str
    ui_enabled: bool
    full_installation: bool | None
    providers: tuple[str, ...]


@dataclass(frozen=True)
class ProviderContract:
    module_id: str
    profile: str
    repository: str
    commit: str
    manifest_sha256: str
    entrypoint: str
    required_surfaces: frozenset[str]


@dataclass(frozen=True)
class VerifiedProviderFacts:
    module_id: str
    repository: str
    commit: str
    manifest_bytes: bytes
    entrypoint: str
    surfaces: frozenset[str]


@dataclass(frozen=True)
class SelectedOperatorUI:
    decision_id: str
    module_id: str
    profile: str
    repository: str
    commit: str
    manifest_sha256: str
    entrypoint: str
    surfaces: frozenset[str]


def _refuse(code: str, detail: str):
    raise OperatorUISelectionError(code, detail)


def _text(value):
    return type(value) is str and bool(value.strip()) and value == value.strip()


def _repository(value):
    if not _text(value):
        return None
    value = value.rstrip("/")
    if value.startswith("git@github.com:"):
        value = "https://github.com/" + value.removeprefix("git@github.com:")
    value = value.removesuffix(".git")
    if not re.fullmatch(r"https://[^/\\\s?#]+/[^\\\s?#]+", value):
        return None
    return value.casefold()


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate manifest key")
        result[key] = value
    return result


def _manifest(candidate, observed):
    if type(observed.manifest_bytes) is not bytes:
        _refuse("invalid_manifest", "Verified manifest bytes are unavailable.")
    if hashlib.sha256(observed.manifest_bytes).hexdigest() != candidate.manifest_sha256:
        _refuse("manifest_mismatch", "Observed manifest differs from its immutable pin.")
    try:
        manifest = json.loads(
            observed.manifest_bytes.decode("utf-8"),
            object_pairs_hook=_json_object,
            parse_constant=lambda value: _refuse("invalid_manifest", "Invalid JSON constant."),
        )
    except (UnicodeError, ValueError) as exc:
        raise OperatorUISelectionError("invalid_manifest", "Manifest is not unambiguous UTF-8 JSON.") from exc
    if type(manifest) is not dict:
        _refuse("invalid_manifest", "Manifest must be an object.")
    provides = manifest.get("provides")
    requires = manifest.get("requires")
    source = manifest.get("source_of_truth")
    if (
        manifest.get("schema") != "ellmos.module.v2"
        or manifest.get("id") != candidate.module_id
        or manifest.get("kind") != "ui"
        or manifest.get("category") != "runtime"
        or manifest.get("status") != "active"
        or type(provides) is not list
        or not all(_text(item) for item in provides)
        or len(set(provides)) != len(provides)
        or "operator.ui" not in provides
        or type(requires) is not list
        or not all(_text(item) for item in requires)
        or (candidate.profile == "lite" and requires != [])
        or type(source) is not dict
        or source.get("type") != "git-repository"
        or _repository(source.get("repository")) != _repository(candidate.repository)
    ):
        _refuse("invalid_manifest", "Manifest does not bind the selected UI provider.")
    relative = source.get("path")
    if (
        not _text(relative)
        or "\\" in relative
        or relative.startswith("/")
        or ":" in relative
        or (relative != "." and any(part in {"", ".", ".."} for part in relative.split("/")))
    ):
        _refuse("invalid_manifest", "Manifest source path is not a portable module-relative path.")


def select_operator_ui(
    choice: RecordedUIChoice,
    candidates: tuple[ProviderContract, ...],
    facts: tuple[VerifiedProviderFacts, ...],
    *,
    full_provider_id: str | None = None,
) -> SelectedOperatorUI | None:
    """Validate recorded choices against verifier facts without external actions.

    The caller supplies observations from the existing source/entry verifier.
    Equal strings are not a new checkout, installation, or runtime proof.
    No entrypoint is imported, called, or mounted here.
    """
    if (
        type(choice) is not RecordedUIChoice
        or not _text(choice.decision_id)
        or type(choice.ui_enabled) is not bool
        or (choice.full_installation is not None and type(choice.full_installation) is not bool)
        or (choice.ui_enabled and type(choice.full_installation) is not bool)
        or type(choice.providers) is not tuple
        or not all(_text(item) for item in choice.providers)
    ):
        _refuse("invalid_choice", "An explicit recorded UI/full/partial decision is required.")
    if len(choice.providers) > 1:
        _refuse("ambiguous_choice", "operator.ui permits at most one selected provider.")
    if not choice.ui_enabled:
        if choice.providers:
            _refuse("conflicting_choice", "A headless composition cannot select a UI provider.")
        return None
    if not choice.providers:
        _refuse("required_role_unbound", "The explicitly required operator.ui role is unbound.")
    if choice.full_installation and (
        not _text(full_provider_id) or full_provider_id == LITE_PROVIDER_ID
    ):
        _refuse("unresolved_full_provider", "The authoritative Full provider identity is unresolved.")
    if (
        type(candidates) is not tuple
        or len(candidates) > 2
        or not all(type(c) is ProviderContract for c in candidates)
    ):
        _refuse("invalid_provider_contract", "Candidates must be immutable provider contracts.")
    ids = [c.module_id for c in candidates]
    if not all(_text(module_id) for module_id in ids):
        _refuse("invalid_provider_contract", "Candidate identities must be explicit.")
    if len(set(ids)) != len(ids):
        _refuse("ambiguous_binding", "A provider identity has more than one contract.")
    selected = choice.providers[0]
    matches = [candidate for candidate in candidates if candidate.module_id == selected]
    if not matches:
        _refuse("unknown_provider", "The selected provider is not an allowed candidate.")
    candidate = matches[0]
    expected_id = full_provider_id if choice.full_installation else LITE_PROVIDER_ID
    profile = "full" if choice.full_installation else "lite"
    if type(candidate.profile) is not str:
        _refuse("invalid_provider_contract", "Provider profile must be explicit text.")
    if selected != expected_id or candidate.profile != profile:
        # Unknown profile is a malformed contract, rather than a valid other profile.
        if candidate.profile not in {"lite", "full"}:
            _refuse("invalid_provider_contract", "Unsupported provider profile.")
        _refuse("selection_mismatch", "The selected provider contradicts the recorded installation.")
    if (
        _repository(candidate.repository) is None
        or type(candidate.commit) is not str
        or re.fullmatch(r"[0-9a-f]{40}", candidate.commit) is None
        or type(candidate.manifest_sha256) is not str
        or re.fullmatch(r"[0-9a-f]{64}", candidate.manifest_sha256) is None
        or type(candidate.entrypoint) is not str
        or re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*", candidate.entrypoint) is None
        or type(candidate.required_surfaces) is not frozenset
        or not all(_text(surface) for surface in candidate.required_surfaces)
        or (profile == "full" and not FULL_SURFACES <= candidate.required_surfaces)
    ):
        _refuse("invalid_provider_contract", "Provider pins, entrypoint, or surface contract are invalid.")
    if type(facts) is not tuple or not all(type(f) is VerifiedProviderFacts for f in facts):
        _refuse("source_binding_unavailable", "Verified immutable provider facts are unavailable.")
    observations = [f for f in facts if f.module_id == selected]
    if len(observations) != 1:
        _refuse("source_binding_unavailable", "Exactly one verifier observation is required.")
    observed = observations[0]
    if (
        _repository(observed.repository) != _repository(candidate.repository)
        or observed.commit != candidate.commit
        or observed.entrypoint != candidate.entrypoint
    ):
        _refuse("source_binding_mismatch", "Observed source or entrypoint differs from the accepted contract.")
    _manifest(candidate, observed)
    if (
        type(observed.surfaces) is not frozenset
        or not all(_text(surface) for surface in observed.surfaces)
        or not candidate.required_surfaces <= observed.surfaces
    ):
        _refuse("missing_capability", "A required accepted provider surface is unavailable.")
    return SelectedOperatorUI(
        choice.decision_id, candidate.module_id, profile, candidate.repository,
        candidate.commit, candidate.manifest_sha256, candidate.entrypoint,
        observed.surfaces,
    )
