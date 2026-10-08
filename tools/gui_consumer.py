# SPDX-License-Identifier: MIT
"""Read-only verifier for the pinned ellmos-system-gui release archive.

It never extracts files, launches a server, or treats an archive as an installed
Ocean capability. A separate, device-authorized backend adapter is required.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from dataclasses import dataclass, replace
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
from types import MappingProxyType
from typing import Mapping
import zipfile

PIN_SCHEMA = "ellmos.open-ocean.gui-consumer.v1"
DIST_SCHEMA = "ellmos-system-gui.dist.v1"
REPORT_SCHEMA = "ellmos.open-ocean.gui-inspection.v1"
DEFAULT_PIN = Path(__file__).resolve().parents[1] / "architecture" / "gui-consumer.v1.json"
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_MEMBER_BYTES = 16 * 1024 * 1024
MAX_MEMBERS = 1000
HEX_40 = re.compile(r"[0-9a-f]{40}")
HEX_64 = re.compile(r"[0-9a-f]{64}")
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")


class InspectionError(ValueError):
    def __init__(self, reason: str, exit_code: int = 3):
        super().__init__(reason)
        self.reason = reason
        self.exit_code = exit_code


def _safe_name(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and "\\" not in name and ":" not in name and not path.is_absolute() and all(
        part not in {"", ".", ".."} and not part.endswith((".", " "))
        and not any(ord(char) < 32 for char in part)
        and part.split(".", 1)[0].upper() not in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
        for part in name.split("/")
    )


def _read_pin(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        source = data["source"]
        if not (
            data.get("schema") == PIN_SCHEMA
            and data.get("id") == "ellmos-system-gui"
            and data.get("status") == "pinned_artifact_only"
            and data.get("activation_ready") is False
            and isinstance(data.get("version"), str) and VERSION.fullmatch(data["version"])
            and isinstance(source, dict)
            and source.get("repository") == "ellmos-ai/ellmos-system-gui"
            and isinstance(source.get("commit"), str) and HEX_40.fullmatch(source["commit"])
            and isinstance(source.get("archive_sha256"), str) and HEX_64.fullmatch(source["archive_sha256"])
            and source.get("dist_manifest_schema") == DIST_SCHEMA
            and data.get("required_backend_routes") == [
                "/api/gui/brand", "/api/gui/backend-origin", "/api/gui/capabilities"
            ]
        ):
            raise InspectionError("pin_invalid")
        return data
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, AttributeError) as exc:
        raise InspectionError("pin_unavailable_or_invalid") from exc


MANIFEST = "dist/dist-manifest.json"
RECEIPT = ".ocean-gui-release.json"
INSTALLED_ARCHIVE = ".ocean-gui-release.zip"
MAX_BYTES = MAX_ARCHIVE_BYTES
MAX_FILES = MAX_MEMBERS
GuiReleaseError = InspectionError


def _sha(data: bytes) -> str:
    return sha256(data).hexdigest()


@dataclass(frozen=True)
class VerifiedGuiRelease:
    source_commit: str
    archive_sha256: str
    payload: Mapping[str, bytes]
    archive_bytes: bytes
    installed_verified: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))

    def receipt(self) -> dict:
        return {"schema": "ellmos.open-ocean.gui-release.v1",
                "source_commit": self.source_commit, "archive_sha256": self.archive_sha256,
                "files": {name: _sha(data) for name, data in sorted(self.payload.items())}}


def _read_small_member(archive: zipfile.ZipFile, member: zipfile.ZipInfo, maximum: int) -> bytes:
    if member.file_size < 0 or member.file_size > maximum:
        raise InspectionError("archive_member_too_large", 2)
    try:
        with archive.open(member, "r") as stream:
            data = stream.read(maximum + 1)
    except (RuntimeError, OSError, EOFError, zipfile.BadZipFile) as exc:
        raise InspectionError("archive_member_unreadable", 2) from exc
    if len(data) != member.file_size or len(data) > maximum:
        raise InspectionError("archive_member_size_mismatch", 2)
    return data


def verify_gui_archive(archive: Path, source_commit: str, archive_sha256: str) -> VerifiedGuiRelease:
    """Verify one bounded byte snapshot for inspection, placement and serving."""
    if not isinstance(source_commit, str) or not HEX_40.fullmatch(source_commit) or not isinstance(archive_sha256, str) or not HEX_64.fullmatch(archive_sha256):
        raise InspectionError("pin_invalid")
    try:
        with Path(archive).open("rb") as stream:
            raw = stream.read(MAX_ARCHIVE_BYTES + 1)
    except OSError as exc:
        raise InspectionError("archive_unavailable_or_too_large") from exc
    if len(raw) > MAX_ARCHIVE_BYTES:
        raise InspectionError("archive_unavailable_or_too_large")
    if _sha(raw) != archive_sha256:
        raise InspectionError("archive_hash_mismatch", 2)
    try:
        with zipfile.ZipFile(io.BytesIO(raw), "r") as source:
            members = source.infolist()
            if len(members) > MAX_MEMBERS or sum(member.file_size for member in members) > MAX_ARCHIVE_BYTES:
                raise InspectionError("archive_member_count_invalid", 2)
            names = [member.filename for member in members]
            if len({name.casefold() for name in names}) != len(names) or any(
                not _safe_name(name) or member.is_dir() or stat.S_ISLNK(member.external_attr >> 16) or member.flag_bits & 1
                for name, member in zip(names, members)
            ):
                raise InspectionError("archive_member_path_invalid", 2)
            by_name = dict(zip(names, members))
            manifest_member = by_name.get(MANIFEST)
            if manifest_member is None or manifest_member.file_size > 1024 * 1024:
                raise InspectionError("dist_manifest_missing_or_large", 2)
            try:
                manifest_bytes = _read_small_member(source, manifest_member, 1024 * 1024)
                manifest = json.loads(manifest_bytes.decode("utf-8"))
            except (UnicodeError, ValueError) as exc:
                raise InspectionError("dist_manifest_invalid", 2) from exc
            files = manifest.get("files") if isinstance(manifest, dict) else None
            if not (
                isinstance(manifest, dict) and manifest.get("schema") == DIST_SCHEMA
                and manifest.get("source_commit") == source_commit and isinstance(files, dict)
                and files and "index.html" in files
                and all(isinstance(name, str) and _safe_name(name) and name != "dist-manifest.json"
                        and name.split("/", 1)[0].casefold() not in {"api", "login", "logout", "register"}
                        and isinstance(digest, str) and HEX_64.fullmatch(digest) for name, digest in files.items())
                and len({name.casefold() for name in files}) == len(files)
            ):
                raise InspectionError("dist_manifest_mismatch", 2)
            expected = {"LICENSE", MANIFEST} | {"dist/" + name for name in files}
            if set(names) != expected:
                raise InspectionError("archive_file_set_mismatch", 2)
            if by_name["LICENSE"].file_size <= 0 or by_name["LICENSE"].file_size > 1024 * 1024:
                raise InspectionError("license_missing_or_large", 2)
            payload = {name: _read_small_member(source, member, MAX_MEMBER_BYTES) for name, member in by_name.items()}
            if any(_sha(payload["dist/" + name]) != digest for name, digest in files.items()):
                raise InspectionError("dist_file_hash_mismatch", 2)
    except (OSError, RuntimeError, EOFError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise InspectionError("archive_unreadable", 2) from exc
    return VerifiedGuiRelease(source_commit, archive_sha256, payload, raw)


def _verify_installed_payload(root: Path, payload: dict[str, bytes], *, extra: set[str] | None = None) -> int:
    """Read back every declared byte and reject links and undeclared local files."""
    if root.is_symlink() or not root.is_dir():
        raise InspectionError("install_path_escape", 2)
    root = root.resolve(strict=True)
    paths = list(root.rglob("*"))
    if any(path.is_symlink() for path in paths):
        raise InspectionError("install_path_escape", 2)
    if {path.relative_to(root).as_posix() for path in paths if path.is_file()} != set(payload) | (extra or set()):
        raise InspectionError("install_file_set_mismatch", 2)
    for name, expected in payload.items():
        path = root / name
        if not path.resolve(strict=True).is_relative_to(root):
            raise InspectionError("install_path_escape", 2)
        with path.open("rb") as stream:
            data = stream.read(MAX_MEMBER_BYTES + 1)
        if data != expected:
            raise InspectionError("install_file_hash_mismatch", 2)
    return len(payload)


def inspect_archive(archive_path: Path, pin_path: Path = DEFAULT_PIN) -> dict:
    """Return only non-secret evidence; never return local paths or file content."""
    report = {
        "schema": REPORT_SCHEMA,
        "source": "pinned_archive_inspection",
        "release_version": None,
        "archive_verified": False,
        "dist_verified": False,
        "source_commit_verified": False,
        "dist_files_verified": 0,
        "installed": False,
        "backend_capabilities": "not_probed",
        "activation_ready": False,
        "reason_code": "not_checked",
    }
    try:
        pin = _read_pin(pin_path)
        report["release_version"] = pin["version"]
        release = verify_gui_archive(archive_path, pin["source"]["commit"], pin["source"]["archive_sha256"])
        report["archive_verified"] = True
        report["source_commit_verified"] = True
        report["dist_verified"] = True
        report["dist_files_verified"] = len(json.loads(release.payload[MANIFEST])["files"])
        report["reason_code"] = "archive_verified_adapter_not_attested"
    except InspectionError as exc:
        report["reason_code"] = exc.reason
        report["exit_code"] = exc.exit_code
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile):
        report["reason_code"] = "archive_unreadable"
        report["exit_code"] = 2
    return report


INSTALL_RECEIPT_SCHEMA = "ellmos.open-ocean.gui-install-receipt.v1"


def inspect_installation(dist_root: Path | None, receipt_path: Path | None, archive_path: Path, pin_path: Path = DEFAULT_PIN) -> dict:
    """Verify a recorded local installation; never infer installation from a ZIP."""
    result = {"installed": False, "reason_code": "install_receipt_unavailable", "files_verified": 0}
    if dist_root is None and receipt_path is None:
        return result
    if dist_root is None or receipt_path is None:
        result["reason_code"] = "install_receipt_or_dist_missing"
        return result
    try:
        pin = _read_pin(pin_path)
        release = verify_gui_archive(archive_path, pin["source"]["commit"], pin["source"]["archive_sha256"])
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if not isinstance(receipt, dict) or (
            receipt.get("schema") != INSTALL_RECEIPT_SCHEMA
            or receipt.get("kit_id") != pin["id"]
            or receipt.get("version") != pin["version"]
            or receipt.get("source_commit") != pin["source"]["commit"]
            or receipt.get("archive_sha256") != pin["source"]["archive_sha256"]
        ):
            raise InspectionError("install_receipt_mismatch", 2)
        manifest_bytes = release.payload[MANIFEST]
        files = json.loads(manifest_bytes)["files"]
        if receipt.get("manifest_sha256") != _sha(manifest_bytes) or receipt.get("file_count") != len(files):
            raise InspectionError("install_receipt_mismatch", 2)
        dist_payload = {name.removeprefix("dist/"): data for name, data in release.payload.items() if name.startswith("dist/")}
        _verify_installed_payload(dist_root, dist_payload)
        result["files_verified"] = len(files)
        result["installed"] = True
        result["reason_code"] = "receipt_and_dist_hashes_verified"
    except (OSError, ValueError, TypeError, UnicodeError, KeyError, zipfile.BadZipFile, InspectionError) as exc:
        result["installed"] = False
        result["files_verified"] = 0
        result["reason_code"] = exc.reason if isinstance(exc, InspectionError) else "install_unavailable_or_invalid"
    return result


def verify_installed_gui(root: Path, source_commit: str | None = None, archive_sha256: str | None = None) -> VerifiedGuiRelease:
    """Validate every installed byte; a receipt alone is not installed evidence."""
    if root.is_symlink() or not root.is_dir():
        raise GuiReleaseError("GUI-Installation ist kein reguläres Verzeichnis.")
    try:
        record = json.loads((root / RECEIPT).read_text(encoding="utf-8"))
        commit = record["source_commit"]
        digest = record["archive_sha256"]
        hashes = record["files"]
        if record.get("schema") != "ellmos.open-ocean.gui-release.v1" or not re.fullmatch(r"[0-9a-f]{40}", commit) or not re.fullmatch(r"[0-9a-f]{64}", digest) or not isinstance(hashes, dict):
            raise GuiReleaseError("GUI-Installationsbeleg ist ungültig.")
        if source_commit is not None and commit != source_commit or archive_sha256 is not None and digest != archive_sha256:
            raise GuiReleaseError("GUI-Installation passt nicht zu den erwarteten Pins.")
        original = verify_gui_archive(root / INSTALLED_ARCHIVE, commit, digest)
        if hashes != original.receipt()["files"]:
            raise GuiReleaseError("GUI-Installationsbeleg passt nicht zum gepinnten Originalarchiv.")
        _verify_installed_payload(root, original.payload, extra={RECEIPT, INSTALLED_ARCHIVE})
        return replace(original, installed_verified=True)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        if isinstance(exc, GuiReleaseError):
            raise
        raise GuiReleaseError("GUI-Installation ist nicht verifizierbar.") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect the pinned Ocean GUI archive without installing it")
    parser.add_argument("command", choices=["inspect"])
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = inspect_archive(args.archive)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(f"GUI archive: {report['reason_code']}; installed={report['installed']}; "
              f"backend={report['backend_capabilities']}")
    return int(report.get("exit_code", 0))


if __name__ == "__main__":
    raise SystemExit(main())
