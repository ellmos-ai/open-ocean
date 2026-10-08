"""Read-only verification of a pinned ellmos-system-gui distribution."""
from __future__ import annotations

import hashlib
import io
import json
import re
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

MANIFEST = "dist/dist-manifest.json"
RECEIPT = ".ocean-gui-release.json"
INSTALLED_ARCHIVE = ".ocean-gui-release.zip"
MAX_BYTES = 64 * 1024 * 1024
MAX_FILES = 4096


class GuiReleaseError(ValueError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_name(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and "\\" not in name and ":" not in name and not path.is_absolute() and all(
        part not in {"", ".", ".."} and not part.endswith((".", " "))
        and not any(ord(char) < 32 for char in part)
        and part.split(".", 1)[0].upper() not in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
        for part in name.split("/")
    )


def _manifest(data: bytes, commit: str) -> dict[str, str]:
    try:
        record = json.loads(data)
    except (ValueError, UnicodeError) as exc:
        raise GuiReleaseError("GUI-Manifest ist ungültig.") from exc
    if not isinstance(record, dict) or record.get("schema") != "ellmos-system-gui.dist.v1" or record.get("source_commit") != commit:
        raise GuiReleaseError("GUI-Manifest passt nicht zum Quellenpin.")
    files = record.get("files")
    if not isinstance(files, dict) or not files or "index.html" not in files:
        raise GuiReleaseError("GUI-Dateimanifest ist leer oder enthält keine Startseite.")
    for name, digest in files.items():
        if not isinstance(name, str) or not _safe_name(name) or name == "dist-manifest.json" or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise GuiReleaseError("GUI-Dateimanifest enthält einen ungültigen Pfad oder Hash.")
        # APIs/auth remain owned by the native provider, never by a static release.
        if name.split("/", 1)[0] in {"api", "login", "logout", "register"}:
            raise GuiReleaseError("GUI-Artefakt darf keine Anbieterroute überdecken.")
    if len({name.casefold() for name in files}) != len(files):
        raise GuiReleaseError("GUI-Dateimanifest enthält kollidierende Dateinamen.")
    return files


@dataclass(frozen=True)
class VerifiedGuiRelease:
    source_commit: str
    archive_sha256: str
    payload: dict[str, bytes]
    archive_bytes: bytes

    def receipt(self) -> dict:
        return {
            "schema": "ellmos.open-ocean.gui-release.v1",
            "source_commit": self.source_commit,
            "archive_sha256": self.archive_sha256,
            "files": {name: _sha(data) for name, data in sorted(self.payload.items())},
        }


def verify_gui_archive(archive: Path, source_commit: str, archive_sha256: str) -> VerifiedGuiRelease:
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit or "") or not re.fullmatch(r"[0-9a-f]{64}", archive_sha256 or ""):
        raise GuiReleaseError("GUI benötigt einen vollständigen Commit- und Archivpin.")
    if archive.stat().st_size > MAX_BYTES:
        raise GuiReleaseError("GUI-Archiv überschreitet die Größenbegrenzung.")
    raw = archive.read_bytes()
    if _sha(raw) != archive_sha256:
        raise GuiReleaseError("GUI-Archivhash stimmt nicht mit dem Pin überein.")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as source:
            infos = source.infolist()
            if len(infos) > MAX_FILES or sum(info.file_size for info in infos) > MAX_BYTES:
                raise GuiReleaseError("GUI-Archiv überschreitet die Entpackgrenzen.")
            names = [info.filename for info in infos]
            if len({name.casefold() for name in names}) != len(names):
                raise GuiReleaseError("GUI-Archiv enthält doppelte Dateinamen.")
            for info in infos:
                if not _safe_name(info.filename) or info.is_dir() or stat.S_ISLNK(info.external_attr >> 16) or info.flag_bits & 1:
                    raise GuiReleaseError("GUI-Archiv enthält einen unsicheren Eintrag.")
            payload = {info.filename: source.read(info) for info in infos}
    except (zipfile.BadZipFile, RuntimeError) as exc:
        raise GuiReleaseError("GUI-Archiv ist nicht lesbar.") from exc
    if MANIFEST not in payload or not payload.get("LICENSE"):
        raise GuiReleaseError("GUI-Archiv benötigt dist/dist-manifest.json und LICENSE.")
    files = _manifest(payload[MANIFEST], source_commit)
    if set(payload) != {MANIFEST, "LICENSE", *("dist/" + name for name in files)}:
        raise GuiReleaseError("GUI-Archiv enthält fehlende oder nicht deklarierte Dateien.")
    for name, digest in files.items():
        if _sha(payload["dist/" + name]) != digest:
            raise GuiReleaseError("GUI-Dateihash stimmt nicht mit dem Manifest überein.")
    return VerifiedGuiRelease(source_commit, archive_sha256, payload, raw)


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
        paths = list(root.rglob("*"))
        if any(path.is_symlink() for path in paths):
            raise GuiReleaseError("GUI-Installation enthält einen symbolischen Link.")
        actual = {path.relative_to(root).as_posix() for path in paths if path.is_file()}
        if actual != {*hashes, RECEIPT, INSTALLED_ARCHIVE} or len(actual) > MAX_FILES + 2:
            raise GuiReleaseError("GUI-Installationsdateien passen nicht zum Beleg.")
        payload = {}
        for name, expected in hashes.items():
            if not isinstance(name, str) or not _safe_name(name) or not isinstance(expected, str):
                raise GuiReleaseError("GUI-Installationsbeleg enthält ungültige Dateien.")
            path = root / name
            if path.stat().st_size > MAX_BYTES:
                raise GuiReleaseError("GUI-Installationsdatei ist zu groß.")
            data = path.read_bytes()
            if _sha(data) != expected:
                raise GuiReleaseError("GUI-Installation wurde nachträglich verändert.")
            payload[name] = data
        if sum(map(len, payload.values())) > MAX_BYTES or MANIFEST not in payload or not payload.get("LICENSE"):
            raise GuiReleaseError("GUI-Installation ist unvollständig.")
        files = _manifest(payload[MANIFEST], commit)
        if set(payload) != {MANIFEST, "LICENSE", *("dist/" + name for name in files)} or any(_sha(payload["dist/" + name]) != value for name, value in files.items()):
            raise GuiReleaseError("GUI-Installation passt nicht zum Dateimanifest.")
        return original
    except (OSError, ValueError, TypeError, KeyError) as exc:
        if isinstance(exc, GuiReleaseError):
            raise
        raise GuiReleaseError("GUI-Installation ist nicht verifizierbar.") from exc
