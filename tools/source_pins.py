"""Fail-closed provenance gate for OCEAN's recipe and Skills Registry inputs.

The transaction resolver accepts ordinary paths because it is also useful for
small synthetic tests.  The product lifecycle passes the shipped source-pin
contract through this module before Resolve, and therefore before any Fetch,
Place, or Activate action.  Verification is deliberately local and portable:
no network call and no sibling-repository Python import is required.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

try:  # Script execution adds tools/ directly; package imports use tools.*.
    from resolve_bundles import canonical_hash
except ModuleNotFoundError:  # pragma: no cover - exercised by the package path
    from tools.resolve_bundles import canonical_hash


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_PINS = REPO_ROOT / "architecture" / "ocean-full-dev.source-pins.v1.json"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_PINNED_REPO_URI_RE = re.compile(
    r"^repo://[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}/[^\\]+$"
)


class SourcePinError(RuntimeError):
    """A pinned source is malformed, ambiguous, or different from live input."""


# Keep the verifier body concise without coupling this module to either of the
# two supported import modes of resolve_bundles.py.
ResolveError = SourcePinError


@dataclass(frozen=True)
class SourcePinVerification:
    """Portable receipt plus the exact Registry object whose bytes were verified."""

    receipt: dict[str, Any]
    skills_registry: dict[str, Any]


def _read_json_bytes(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        payload = path.read_bytes()
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ResolveError(f"cannot read {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ResolveError(f"{label} {path} is not a JSON object")
    return value, payload


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise ResolveError(
            f"{label} has invalid fields (missing={missing}, unexpected={unexpected})"
        )


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ResolveError(f"{label} must be an object")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResolveError(f"{label} must be a non-empty string")
    return value


def _sha256_pin(value: Any, label: str) -> str:
    pin = _string(value, label)
    if not _SHA256_RE.fullmatch(pin):
        raise ResolveError(f"{label} must be a lowercase SHA-256")
    return pin


def _git_commit(value: Any, label: str) -> str:
    commit = _string(value, label)
    if not _GIT_SHA_RE.fullmatch(commit):
        raise ResolveError(f"{label} must be a full lowercase Git commit")
    return commit


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _git(repo: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise ResolveError(f"cannot inspect recipe checkout {repo}: {exc}") from exc
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or f"git exited {proc.returncode}"
        raise ResolveError(f"cannot inspect recipe checkout {repo}: {detail}")
    return proc.stdout.strip()


def _normalized_repository(value: str) -> str:
    normalized = value.strip().replace("\\", "/").rstrip("/")
    if normalized.startswith("git@github.com:"):
        normalized = "https://github.com/" + normalized.removeprefix("git@github.com:")
    normalized = normalized.removesuffix(".git")
    return normalized.casefold()


def _recipe_file(recipe_root: Path, relative: str, label: str) -> Path:
    if "\\" in relative:
        raise ResolveError(f"{label} must use portable forward slashes")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise ResolveError(f"{label} must be a safe relative recipe path")
    try:
        root = recipe_root.resolve(strict=True)
        candidate = (root / Path(*pure.parts)).resolve(strict=True)
    except OSError as exc:
        raise ResolveError(f"{label} is unavailable below {recipe_root}: {exc}") from exc
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ResolveError(f"{label} escapes the recipe checkout") from exc
    if not candidate.is_file():
        raise ResolveError(f"{label} is not a file: {candidate}")
    return candidate


def _load_contract(path: Path) -> dict[str, Any]:
    contract, _ = _read_json_bytes(path, "source-pin contract")
    _exact_keys(
        contract,
        {"schema", "id", "version", "authority", "recipe", "skills_registry", "content_hash"},
        "source-pin contract",
    )
    if contract.get("schema") != "ellmos.open-ocean-source-pins.v1":
        raise ResolveError(f"{path} has an unsupported source-pin schema")
    _string(contract.get("id"), "source-pin contract id")
    if contract.get("version") != "1.0.0":
        raise ResolveError(f"{path} has an unsupported source-pin version")
    if contract.get("authority") != {"kind": "integration-pin", "runtime_authority": False}:
        raise ResolveError(f"{path} has invalid source-pin authority")
    declared_hash = _sha256_pin(contract.get("content_hash"), "source-pin content_hash")
    observed_hash = canonical_hash(contract)
    if declared_hash != observed_hash:
        raise ResolveError(
            f"source-pin content_hash mismatch: declared {declared_hash}, observed {observed_hash}"
        )

    recipe = _object(contract.get("recipe"), "source-pin recipe")
    _exact_keys(
        recipe,
        {"repository", "commit", "component_bindings", "skills_crosswalk"},
        "source-pin recipe",
    )
    _string(recipe.get("repository"), "recipe repository")
    _git_commit(recipe.get("commit"), "recipe commit")
    bindings = _object(recipe.get("component_bindings"), "recipe component_bindings")
    _exact_keys(bindings, {"path", "content_hash"}, "recipe component_bindings")
    _string(bindings.get("path"), "component_bindings path")
    _sha256_pin(bindings.get("content_hash"), "component_bindings content_hash")
    crosswalk = _object(recipe.get("skills_crosswalk"), "recipe skills_crosswalk")
    _exact_keys(crosswalk, {"path", "sha256"}, "recipe skills_crosswalk")
    _string(crosswalk.get("path"), "skills_crosswalk path")
    _sha256_pin(crosswalk.get("sha256"), "skills_crosswalk sha256")

    registry = _object(contract.get("skills_registry"), "source-pin skills_registry")
    _exact_keys(registry, {"uri", "sha256"}, "source-pin skills_registry")
    registry_uri = _string(registry.get("uri"), "skills_registry uri")
    if not _PINNED_REPO_URI_RE.fullmatch(registry_uri):
        raise ResolveError(
            "skills_registry uri must pin owner/repository, a full commit, and a repository path"
        )
    _sha256_pin(registry.get("sha256"), "skills_registry sha256")
    return contract


def verify_source_pins(
    source_pins_path: Path,
    bundles_root: Path,
    skills_registry_path: Path,
) -> SourcePinVerification:
    """Verify all pinned source inputs and return a compact receipt.

    The recipe checkout must be the repository root, have the exact immutable
    commit and origin declared by the contract, and be clean.  The provider
    binding and crosswalk are then checked inside that checkout, while the
    caller-supplied Skills Registry is checked byte-for-byte by SHA-256.
    """

    contract = _load_contract(source_pins_path)
    recipe_pin = contract["recipe"]
    registry_pin = contract["skills_registry"]

    try:
        recipe_root = bundles_root.resolve(strict=True)
    except OSError as exc:
        raise ResolveError(f"recipe checkout does not exist: {bundles_root}") from exc
    if not recipe_root.is_dir():
        raise ResolveError(f"recipe checkout is not a directory: {recipe_root}")
    git_root = Path(_git(recipe_root, "rev-parse", "--show-toplevel")).resolve(strict=True)
    if git_root != recipe_root:
        raise ResolveError(
            f"bundles root must be the recipe repository root: got {recipe_root}, Git root is {git_root}"
        )
    dirty = _git(recipe_root, "status", "--porcelain=v1", "--untracked-files=all")
    if dirty:
        first = dirty.splitlines()[0]
        raise ResolveError(f"recipe checkout is not clean (first change: {first})")
    observed_commit = _git(recipe_root, "rev-parse", "HEAD")
    if observed_commit != recipe_pin["commit"]:
        raise ResolveError(
            f"recipe commit mismatch: expected {recipe_pin['commit']}, observed {observed_commit}"
        )
    observed_repository = _git(recipe_root, "remote", "get-url", "origin")
    if _normalized_repository(observed_repository) != _normalized_repository(recipe_pin["repository"]):
        raise ResolveError(
            "recipe origin mismatch: "
            f"expected {recipe_pin['repository']!r}, observed {observed_repository!r}"
        )

    binding_pin = recipe_pin["component_bindings"]
    binding_path = _recipe_file(recipe_root, binding_pin["path"], "component_bindings path")
    binding, _ = _read_json_bytes(binding_path, "provider binding")
    declared_binding_hash = _sha256_pin(
        binding.get("content_hash"), "provider binding content_hash"
    )
    observed_binding_hash = canonical_hash(binding)
    if declared_binding_hash != observed_binding_hash:
        raise ResolveError(
            "provider binding self-hash mismatch: "
            f"declared {declared_binding_hash}, observed {observed_binding_hash}"
        )
    if declared_binding_hash != binding_pin["content_hash"]:
        raise ResolveError(
            "provider binding content_hash mismatch: "
            f"expected {binding_pin['content_hash']}, observed {declared_binding_hash}"
        )
    sources = _object(binding.get("sources"), "provider binding sources")
    skills_source = _object(
        sources.get("registry:skills-components"),
        "provider binding registry:skills-components",
    )
    crosswalk_source = _object(
        sources.get("crosswalk:skills"),
        "provider binding crosswalk:skills",
    )
    if skills_source.get("uri") != registry_pin["uri"]:
        raise ResolveError(
            "provider binding Skills Registry URI mismatch: "
            f"expected {registry_pin['uri']!r}, observed {skills_source.get('uri')!r}"
        )
    if skills_source.get("sha256") != registry_pin["sha256"]:
        raise ResolveError(
            "provider binding Skills Registry SHA-256 mismatch: "
            f"expected {registry_pin['sha256']}, observed {skills_source.get('sha256')!r}"
        )

    crosswalk_pin = recipe_pin["skills_crosswalk"]
    expected_crosswalk_uri = f"repo://{crosswalk_pin['path']}"
    if crosswalk_source.get("uri") != expected_crosswalk_uri:
        raise ResolveError(
            "provider binding skills crosswalk URI mismatch: "
            f"expected {expected_crosswalk_uri!r}, observed {crosswalk_source.get('uri')!r}"
        )
    if crosswalk_source.get("sha256") != crosswalk_pin["sha256"]:
        raise ResolveError(
            "provider binding skills crosswalk SHA-256 mismatch: "
            f"expected {crosswalk_pin['sha256']}, observed {crosswalk_source.get('sha256')!r}"
        )
    crosswalk_path = _recipe_file(recipe_root, crosswalk_pin["path"], "skills_crosswalk path")
    try:
        crosswalk_bytes = crosswalk_path.read_bytes()
    except OSError as exc:
        raise ResolveError(f"cannot read skills crosswalk {crosswalk_path}: {exc}") from exc
    observed_crosswalk_hash = _sha256(crosswalk_bytes)
    if observed_crosswalk_hash != crosswalk_pin["sha256"]:
        raise ResolveError(
            "skills crosswalk SHA-256 mismatch: "
            f"expected {crosswalk_pin['sha256']}, observed {observed_crosswalk_hash}"
        )

    try:
        registry_bytes = skills_registry_path.read_bytes()
    except OSError as exc:
        raise ResolveError(f"cannot read Skills Registry {skills_registry_path}: {exc}") from exc
    observed_registry_hash = _sha256(registry_bytes)
    if observed_registry_hash != registry_pin["sha256"]:
        raise ResolveError(
            "Skills Registry SHA-256 mismatch: "
            f"expected {registry_pin['sha256']}, observed {observed_registry_hash}"
        )
    try:
        verified_registry = json.loads(registry_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ResolveError(f"Skills Registry is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(verified_registry, dict):
        raise ResolveError("Skills Registry is not a JSON object")

    final_dirty = _git(recipe_root, "status", "--porcelain=v1", "--untracked-files=all")
    final_commit = _git(recipe_root, "rev-parse", "HEAD")
    if final_dirty or final_commit != recipe_pin["commit"]:
        raise ResolveError("recipe checkout changed while source pins were being verified")

    receipt = {
        "status": "verified",
        "contract": str(source_pins_path.resolve(strict=True)),
        "content_hash": contract["content_hash"],
        "recipe": {
            "repository": recipe_pin["repository"],
            "commit": recipe_pin["commit"],
            "component_bindings_content_hash": binding_pin["content_hash"],
            "skills_crosswalk_sha256": crosswalk_pin["sha256"],
        },
        "skills_registry": {
            "uri": registry_pin["uri"],
            "sha256": registry_pin["sha256"],
        },
    }
    return SourcePinVerification(receipt=receipt, skills_registry=verified_registry)
