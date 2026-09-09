from __future__ import annotations

import hashlib
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.accounts_projection import AccountProjectionError, main, read_accounts_projection


class _Report:
    def as_dict(self):
        return {
            "contract_id": "org.ellmos.accounts.balance-projection",
            "source_checkpoint": 7,
            "row_counts": {"account_balances": 1},
            "read_only": True,
        }


def _database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE account_balances (
                record_ref TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                account_type TEXT,
                balance TEXT,
                balance_date TEXT,
                iban_masked TEXT
            )
            """
        )
        connection.execute(
            "INSERT INTO account_balances VALUES (?, ?, ?, ?, ?, ?)",
            (
                "a" * 64,
                "Haushalt ******************3000",
                "girokonto",
                "1234.50",
                "2026-09-09",
                "******************3000",
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _verifier(monkeypatch: pytest.MonkeyPatch, function) -> None:
    monkeypatch.setitem(
        sys.modules,
        "sqlite_transit_sync",
        SimpleNamespace(verify_projection_database=function),
    )


def test_consumer_verifies_then_reads_only_the_allowlisted_fields(monkeypatch, tmp_path):
    database = tmp_path / "accounts.sqlite"
    _database(database)
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    calls = []

    def verify(path, contract, **kwargs):
        calls.append((Path(path), contract, kwargs))
        return _Report()

    _verifier(monkeypatch, verify)
    result = read_accounts_projection(
        database,
        consumer_id="ocean-accounts-consumer",
        minimum_offline_seconds=2592000,
        previous_checkpoint=5,
    )

    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    assert calls == [
        (
            database,
            "accounts-balance-projection.v1",
            {
                "consumer_id": "ocean-accounts-consumer",
                "minimum_offline_seconds": 2592000,
                "previous_checkpoint": 5,
            },
        )
    ]
    assert result["status"] == "verified-read-only-account-projection"
    assert result["read_only"] is True
    assert set(result["accounts"][0]) == {
        "record_ref",
        "name",
        "account_type",
        "balance",
        "balance_date",
        "iban_masked",
    }
    assert result["accounts"][0]["iban_masked"] == "******************3000"


def test_consumer_rejects_a_projection_changed_by_the_verification_step(monkeypatch, tmp_path):
    database = tmp_path / "accounts.sqlite"
    _database(database)

    def verify(path, _contract, **_kwargs):
        connection = sqlite3.connect(path)
        try:
            connection.execute("UPDATE account_balances SET balance = '9999.99'")
            connection.commit()
        finally:
            connection.close()
        return _Report()

    _verifier(monkeypatch, verify)
    with pytest.raises(AccountProjectionError, match="changed while it was being verified"):
        read_accounts_projection(
            database,
            consumer_id="ocean-accounts-consumer",
            minimum_offline_seconds=2592000,
        )


def test_consumer_rejects_a_sidecar_created_after_verification(monkeypatch, tmp_path):
    database = tmp_path / "accounts.sqlite"
    _database(database)

    def verify(path, _contract, **_kwargs):
        Path(f"{path}-wal").write_bytes(b"not-closed")
        return _Report()

    _verifier(monkeypatch, verify)
    with pytest.raises(AccountProjectionError, match="not closed"):
        read_accounts_projection(
            database,
            consumer_id="ocean-accounts-consumer",
            minimum_offline_seconds=2592000,
        )


def test_cli_emits_json_after_the_same_read_only_gate(monkeypatch, tmp_path, capsys):
    database = tmp_path / "accounts.sqlite"
    _database(database)
    _verifier(monkeypatch, lambda *_args, **_kwargs: _Report())

    assert (
        main(
            [
                "--database",
                str(database),
                "--consumer-id",
                "ocean-accounts-consumer",
                "--minimum-offline-seconds",
                "2592000",
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert captured.err == ""
    assert '"ok": true' in captured.out
    assert '"balance": "1234.50"' in captured.out
