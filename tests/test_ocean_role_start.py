from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import ocean


def _manifest(tmp_path: Path) -> Path:
    prompt = tmp_path / "Rolle mit Umlaut ä.md"
    prompt.write_text("# Rolle", encoding="utf-8")
    starter = tmp_path / "start.sh"
    starter.write_text("#!/bin/sh\n", encoding="utf-8")
    path = tmp_path / "ellmos-module.v2.json"
    path.write_text(json.dumps({
        "id": "example",
        "roles": [{
            "id": "reviewer",
            "label": "REVIEWER",
            "prompt": prompt.name,
            "request": "Prüfe vollständig.",
            "providers": ["codex", "claude"],
            "starter": starter.name,
        }],
    }, ensure_ascii=False), encoding="utf-8")
    return path


def test_role_start_forwards_to_the_same_unified_console_entry(tmp_path):
    manifest = _manifest(tmp_path)
    args = ocean.build_parser().parse_args([
        "start", "reviewer", "--manifest", str(manifest),
        "--provider", "codex", "--model", "gpt-test", "--effort", "high",
        "--cwd", str(tmp_path), "--dry-run",
    ])
    command = ocean._role_console_command(args)
    assert command[:5] == [
        ocean.sys.executable, "-m", "unified_gui.console", "start", "reviewer",
    ]
    assert command[command.index("--manifest") + 1] == str(manifest)
    assert command[-1] == "--dry-run"


def test_role_start_never_enters_runtime_lifecycle(tmp_path, monkeypatch):
    manifest = _manifest(tmp_path)
    run = mock.Mock(return_value=mock.Mock(returncode=0))
    attach = mock.Mock()
    monkeypatch.setattr(ocean.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(ocean.subprocess, "run", run)
    monkeypatch.setattr(ocean, "_attach_stderr_log", attach)
    code = ocean.main([
        "start", "reviewer", "--manifest", str(manifest),
        "--provider", "codex", "--dry-run",
    ])
    assert code == 0
    attach.assert_not_called()
    command = run.call_args.args[0]
    assert command[1:3] == ["-m", "unified_gui.console"]


def test_runtime_start_without_role_still_requires_workspace(monkeypatch, capsys):
    attach = mock.Mock()
    monkeypatch.setattr(ocean, "_attach_stderr_log", attach)
    assert ocean.main(["start"]) == 2
    attach.assert_not_called()
    assert "--workspace" in capsys.readouterr().err


def test_missing_unified_console_falls_back_to_taskplan(tmp_path, monkeypatch):
    manifest = _manifest(tmp_path)

    def find_spec(name):
        return None if name == "unified_gui.console" else object()

    monkeypatch.setattr(ocean.importlib.util, "find_spec", find_spec)
    args = ocean.build_parser().parse_args([
        "start", "example:reviewer", "--manifest", str(manifest),
        "--provider", "codex", "--cwd", str(tmp_path), "--dry-run",
    ])
    run = mock.Mock(return_value=mock.Mock(returncode=0))
    assert ocean._start_role(args, run=run) == 0
    command = run.call_args.args[0]
    assert command[1:4] == ["-m", "taskplan", "launch"]
    assert command[command.index("--prompt-file") + 1].endswith("Rolle mit Umlaut ä.md")
    assert run.call_args.kwargs["env"]["TASKPLAN_STARTER_DRY_RUN"] == "1"


def test_fallback_rejects_unknown_role_before_any_process(tmp_path, monkeypatch):
    manifest = _manifest(tmp_path)
    monkeypatch.setattr(ocean.importlib.util, "find_spec", lambda _name: None)
    args = ocean.build_parser().parse_args([
        "start", "missing", "--manifest", str(manifest), "--provider", "codex",
    ])
    run = mock.Mock()
    try:
        ocean._start_role(args, run=run)
    except ValueError as exc:
        assert "nicht gefunden" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Unbekannte Rolle wurde akzeptiert")
    run.assert_not_called()
