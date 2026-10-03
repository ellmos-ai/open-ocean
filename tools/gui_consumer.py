# SPDX-License-Identifier: MIT
"""Read-only verifier for the pinned ellmos-system-gui release archive.

It never extracts files, launches a server, or treats an archive as an installed
Ocean capability. A separate, device-authorized backend adapter is required.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys
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


class InspectionError(Exception):
    def __init__(self, reason: str, exit_code: int = 3):
        super().__init__(reason)
        self.reason = reason
        self.exit_code = exit_code


def _safe_name(name: str) -> bool:
    if (not isinstance(name, str) or "\\" in name or not name or name.startswith("/")
            or ":" in name or any(ord(char) < 32 for char in name)):
        return False
    parts = PurePosixPath(name).parts
    return bool(parts) and all(part not in {"", ".", ".."} for part in parts) and PurePosixPath(name).as_posix() == name


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


def _archive_digest(path: Path) -> str:
    try:
        if not path.is_file() or path.stat().st_size > MAX_ARCHIVE_BYTES:
            raise InspectionError("archive_unavailable_or_too_large")
        digest = sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError as exc:
        raise InspectionError("archive_unavailable_or_too_large") from exc


def _member_digest(archive: zipfile.ZipFile, member: zipfile.ZipInfo) -> str:
    if member.file_size < 0 or member.file_size > MAX_MEMBER_BYTES:
        raise InspectionError("archive_member_too_large", 2)
    digest = sha256()
    count = 0
    try:
        with archive.open(member, "r") as stream:
            while chunk := stream.read(1024 * 1024):
                count += len(chunk)
                if count > MAX_MEMBER_BYTES:
                    raise InspectionError("archive_member_too_large", 2)
                digest.update(chunk)
    except (RuntimeError, OSError, EOFError, zipfile.BadZipFile) as exc:
        raise InspectionError("archive_member_unreadable", 2) from exc
    if count != member.file_size:
        raise InspectionError("archive_member_size_mismatch", 2)
    return digest.hexdigest()


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
        if _archive_digest(archive_path) != pin["source"]["archive_sha256"]:
            raise InspectionError("archive_hash_mismatch", 2)
        report["archive_verified"] = True
        with zipfile.ZipFile(archive_path, "r") as archive:
            members = archive.infolist()
            if len(members) > MAX_MEMBERS or sum(member.file_size for member in members) > MAX_ARCHIVE_BYTES:
                raise InspectionError("archive_member_count_invalid", 2)
            names = [member.filename for member in members]
            if len(names) != len(set(names)) or any(
                not _safe_name(name) or member.is_dir() or stat.S_ISLNK(member.external_attr >> 16)
                for name, member in zip(names, members)
            ):
                raise InspectionError("archive_member_path_invalid", 2)
            by_name = dict(zip(names, members))
            manifest_member = by_name.get("dist/dist-manifest.json")
            if manifest_member is None or manifest_member.file_size > 1024 * 1024:
                raise InspectionError("dist_manifest_missing_or_large", 2)
            try:
                manifest = json.loads(_read_small_member(archive, manifest_member, 1024 * 1024).decode("utf-8"))
            except (UnicodeError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
                raise InspectionError("dist_manifest_invalid", 2) from exc
            files = manifest.get("files") if isinstance(manifest, dict) else None
            if not (
                isinstance(manifest, dict)
                and manifest.get("schema") == DIST_SCHEMA
                and manifest.get("source_commit") == pin["source"]["commit"]
                and isinstance(files, dict) and files
                and all(
                    isinstance(name, str) and _safe_name(name) and name != "dist-manifest.json"
                    and isinstance(digest, str) and HEX_64.fullmatch(digest)
                    for name, digest in files.items()
                )
            ):
                raise InspectionError("dist_manifest_mismatch", 2)
            report["source_commit_verified"] = True
            expected = {"LICENSE", "dist/dist-manifest.json"} | {"dist/" + name for name in files}
            if set(names) != expected:
                raise InspectionError("archive_file_set_mismatch", 2)
            if by_name["LICENSE"].file_size <= 0 or by_name["LICENSE"].file_size > 1024 * 1024:
                raise InspectionError("license_missing_or_large", 2)
            for name, digest in files.items():
                if _member_digest(archive, by_name["dist/" + name]) != digest:
                    raise InspectionError("dist_file_hash_mismatch", 2)
            report["dist_files_verified"] = len(files)
            report["dist_verified"] = True
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
        if not inspect_archive(archive_path, pin_path)["dist_verified"]:
            raise InspectionError("archive_unverified", 2)
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if not isinstance(receipt, dict) or (
            receipt.get("schema") != INSTALL_RECEIPT_SCHEMA
            or receipt.get("kit_id") != pin["id"]
            or receipt.get("version") != pin["version"]
            or receipt.get("source_commit") != pin["source"]["commit"]
            or receipt.get("archive_sha256") != pin["source"]["archive_sha256"]
        ):
            raise InspectionError("install_receipt_mismatch", 2)
        if dist_root.is_symlink():
            raise InspectionError("install_path_escape", 2)
        root = dist_root.resolve(strict=True)
        if not root.is_dir():
            raise InspectionError("install_dist_unavailable", 2)
        manifest_path = root / "dist-manifest.json"
        if manifest_path.is_symlink() or not manifest_path.is_file() or manifest_path.stat().st_size > 1024 * 1024:
            raise InspectionError("install_manifest_unavailable", 2)
        manifest_bytes = manifest_path.read_bytes()
        with zipfile.ZipFile(archive_path) as archive:
            expected_manifest_hash = sha256(archive.read("dist/dist-manifest.json")).hexdigest()
        if sha256(manifest_bytes).hexdigest() != expected_manifest_hash:
            raise InspectionError("install_manifest_mismatch", 2)
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        files = manifest.get("files") if isinstance(manifest, dict) else None
        if not (
            isinstance(manifest, dict)
            and manifest.get("schema") == DIST_SCHEMA
            and manifest.get("source_commit") == pin["source"]["commit"]
            and isinstance(files, dict) and files
            and all(isinstance(name, str) and _safe_name(name)
                    and isinstance(digest, str) and HEX_64.fullmatch(digest)
                    for name, digest in files.items())
        ):
            raise InspectionError("install_manifest_mismatch", 2)
        if receipt.get("manifest_sha256") != sha256(manifest_path.read_bytes()).hexdigest():
            raise InspectionError("install_receipt_mismatch", 2)
        if receipt.get("file_count") != len(files):
            raise InspectionError("install_receipt_mismatch", 2)
        for name, digest in files.items():
            file_path = root.joinpath(*PurePosixPath(name).parts)
            if not file_path.resolve(strict=True).is_relative_to(root):
                raise InspectionError("install_path_escape", 2)
            cursor = file_path
            while cursor != root:
                if cursor.is_symlink():
                    raise InspectionError("install_path_escape", 2)
                cursor = cursor.parent
            if not file_path.is_file() or _archive_digest(file_path) != digest:
                raise InspectionError("install_file_hash_mismatch", 2)
            result["files_verified"] += 1
        result["installed"] = True
        result["reason_code"] = "receipt_and_dist_hashes_verified"
    except (OSError, ValueError, TypeError, UnicodeError, KeyError, zipfile.BadZipFile, InspectionError) as exc:
        result["installed"] = False
        result["files_verified"] = 0
        result["reason_code"] = exc.reason if isinstance(exc, InspectionError) else "install_unavailable_or_invalid"
    return result


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
