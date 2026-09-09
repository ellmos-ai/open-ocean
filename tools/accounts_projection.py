#!/usr/bin/env python3
"""Verify and read the minimal accounts-core projection without writing state."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Sequence


CONTRACT_NAME = "accounts-balance-projection.v1"
CONTRACT_ID = "org.ellmos.accounts.balance-projection"
ACCOUNT_COLUMNS = (
    "record_ref",
    "name",
    "account_type",
    "balance",
    "balance_date",
    "iban_masked",
)


class AccountProjectionError(RuntimeError):
    """Raised when the verified file cannot be consumed without ambiguity."""


def read_accounts_projection(
    database: str | Path,
    *,
    consumer_id: str,
    minimum_offline_seconds: int,
    previous_checkpoint: int | None = None,
) -> dict[str, Any]:
    """Return allowlisted balance rows from one unchanged, verified projection.

    The sqlite-transit-sync verifier owns schema, privacy, provenance,
    checkpoint, loop, and tombstone checks. OCEAN then opens the same closed
    file immutable/read-only and selects only the six consumer fields. It does
    not persist a consumer checkpoint or modify either database.
    """
    path = Path(database).expanduser()
    before = _sha256(path)
    _reject_sidecars(path)

    try:
        from sqlite_transit_sync import verify_projection_database
    except ImportError as error:
        raise AccountProjectionError(
            "sqlite-transit-sync with the accounts projection contract is required"
        ) from error

    report = verify_projection_database(
        path,
        CONTRACT_NAME,
        consumer_id=consumer_id,
        minimum_offline_seconds=minimum_offline_seconds,
        previous_checkpoint=previous_checkpoint,
    )
    after_verification = _sha256(path)
    if after_verification != before:
        raise AccountProjectionError("Projection changed while it was being verified")
    _reject_sidecars(path)

    verification = _report_dict(report)
    if verification.get("contract_id") != CONTRACT_ID:
        raise AccountProjectionError("Verifier returned the wrong account projection contract")
    if verification.get("read_only") is not True:
        raise AccountProjectionError("Verifier did not confirm read-only projection access")
    row_counts = verification.get("row_counts")
    if not isinstance(row_counts, dict) or type(row_counts.get("account_balances")) is not int:
        raise AccountProjectionError("Verifier returned an invalid account row count")

    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(
            f"file:{path.resolve().as_posix()}?mode=ro&immutable=1",
            uri=True,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        columns = ", ".join(f'"{name}"' for name in ACCOUNT_COLUMNS)
        rows = [
            dict(row)
            for row in connection.execute(
                f'SELECT {columns} FROM "account_balances" ORDER BY "record_ref"'
            ).fetchall()
        ]
    except sqlite3.Error as error:
        raise AccountProjectionError(
            f"Verified account projection could not be read: {error}"
        ) from error
    finally:
        if connection is not None:
            connection.close()

    after_read = _sha256(path)
    if after_read != before:
        raise AccountProjectionError("Projection changed while OCEAN was reading it")
    _reject_sidecars(path)

    if row_counts["account_balances"] != len(rows):
        raise AccountProjectionError("Verified account row count changed before consumption")
    return {
        "status": "verified-read-only-account-projection",
        "contract_id": CONTRACT_ID,
        "database_sha256": before,
        "verification": verification,
        "accounts": rows,
        "read_only": True,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise AccountProjectionError(f"Cannot read account projection: {error}") from error
    return digest.hexdigest()


def _reject_sidecars(path: Path) -> None:
    sidecars = [Path(f"{path}{suffix}") for suffix in ("-journal", "-wal", "-shm")]
    present = [candidate.name for candidate in sidecars if candidate.exists()]
    if present:
        raise AccountProjectionError(f"Account projection is not closed: {present}")


def _report_dict(report: Any) -> dict[str, Any]:
    value = report.as_dict() if hasattr(report, "as_dict") else report
    if not isinstance(value, dict):
        raise AccountProjectionError("Verifier returned an invalid report")
    return dict(value)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify and read a closed accounts-core projection without writing state."
    )
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--consumer-id", required=True)
    parser.add_argument("--minimum-offline-seconds", required=True, type=int)
    parser.add_argument("--previous-checkpoint", type=int)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = read_accounts_projection(
            args.database,
            consumer_id=args.consumer_id,
            minimum_offline_seconds=args.minimum_offline_seconds,
            previous_checkpoint=args.previous_checkpoint,
        )
    except Exception as error:
        print(
            json.dumps(
                {"ok": False, "error": str(error), "error_type": type(error).__name__},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
