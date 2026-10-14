"""Physical synthetic wheels in disposable environments; no native adoption."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import importlib.util
import json
import marshal
import os
import platform
import subprocess
import struct
import sys
import time
import venv
import zipfile
from pathlib import Path

import pytest

from tools import python_packages as packages


def wheel(root: Path, name: str, version: str, *, requires=(), entry_points=True,
          console_script=False, extra_files=None) -> dict:
    info = f"{name}-{version}.dist-info"
    files = {
        f"{name}/__init__.py": f"VALUE = {version!r}\ndef create_provider(): return VALUE\n".encode(),
        info + "/METADATA": (f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
                               + "".join(f"Requires-Dist: {item}\n" for item in requires)).encode(),
        info + "/WHEEL": b"Wheel-Version: 1.0\nGenerator: synthetic-test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    if entry_points:
        files[info + "/entry_points.txt"] = f"[ellmos.report_providers]\n{name} = {name}:create_provider\n".encode()
    if console_script:
        files[info + "/entry_points.txt"] = files.get(info + "/entry_points.txt", b"") + (
            f"[console_scripts]\n{name}-cli = {name}:create_provider\n".encode())
    files.update(extra_files or {})
    record = io.StringIO()
    writer = csv.writer(record, lineterminator="\n")
    for path, data in sorted(files.items()):
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
        writer.writerow([path, "sha256=" + digest, str(len(data))])
    writer.writerow([info + "/RECORD", "", ""])
    files[info + "/RECORD"] = record.getvalue().encode()
    path = root / f"{name}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, data in files.items():
            archive.writestr(filename, data)
    return {"filename": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "distribution": name, "version": version, "component_ref": "module:alpha",
            "source_repository": "https://example.invalid/synthetic-module",
            "source_commit": "1" * 40, "source_kind": "module-build"}


@pytest.fixture
def environment(tmp_path, monkeypatch):
    target = tmp_path / "isolated-venv"
    venv.EnvBuilder(with_pip=True, symlinks=os.name != "nt").create(target)
    artifacts = tmp_path / "wheelhouse"
    artifacts.mkdir()
    interpreter = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    profile = {"schema": packages.PROFILE_SCHEMA, "id": "synthetic-qa-only", "host": platform.node(),
               "interpreter": str(interpreter), "venv": str(target), "artifact_root": str(artifacts)}
    profiles = tmp_path / "configured-profiles"
    profiles.mkdir()
    path = profiles / (profile["id"] + ".json")
    path.write_text(json.dumps(profile), encoding="utf-8")
    monkeypatch.setenv("OCEAN_PYTHON_PROFILES_ROOT", str(profiles))
    def request(*items, required=True):
        points = ([{"distribution": "alpha", "group": "ellmos.report_providers", "name": "alpha",
                    "value": "alpha:create_provider"}] if required else [])
        return {"profile_id": profile["id"], "profile_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "wheels": list(items), "required_entry_points": points}
    return target, artifacts, path, request


def test_plan_is_native_offline_closure_and_does_not_mutate_target(environment):
    target, artifacts, _, request = environment
    item = wheel(artifacts, "alpha", "1.0")
    first = packages.prepare_package_plan(request(item), {"module:alpha"})
    before = packages.package_target_state(first)
    assert packages.validate_package_plan(first, {"module:alpha"}) == first
    assert packages.package_target_state(first) == before
    assert set(first["checks"]) == packages.CHECKS
    assert set(first["checks"].values()) == {"SUCCESS"}
    assert first["environment"]["venv"] == str(target)
    assert first["environment"]["scheme_authority"].startswith("derived-venv-scheme")
    assert first["environment"]["measurement"] == "isolated-no-site-interpreter-and-config-bytes"


def test_environment_uses_supported_stdlib_scheme_inside_bound_venv(environment):
    target, _, path, _ = environment
    profile = json.loads(path.read_bytes())
    measured = packages._environment(profile)
    expected = "venv" if sys.version_info[:2] >= (3, 11) else ("nt" if os.name == "nt" else "posix_prefix")
    assert measured["install_scheme"] == expected
    if sys.version_info[:2] == (3, 10):
        assert measured["stdlib_default_scheme"] == expected
    assert measured["version"][:2] == list(sys.version_info[:2])
    assert measured["venv"] == str(target)
    assert all(Path(value).is_relative_to(target) for value in measured["paths"].values())
    assert Path(measured["paths"]["purelib"]).is_dir()
    assert measured["measurement"] == "isolated-no-site-interpreter-and-config-bytes"


def test_pip_wrappers_use_bound_original_executor_specs(environment, monkeypatch):
    target, _, path, _ = environment
    measured = packages._environment(json.loads(path.read_bytes()))
    before = packages.target_metadata(measured)
    monkeypatch.setenv("ENSUREPIP_OPTIONS", "altinstall")
    rows, _ = packages._inventory(measured)
    pip = next(row for row in rows if row["distribution"] == "pip")
    projection = pip["pip_console_projection"]
    assert projection["python_version"] == measured["version"]
    assert projection["ensurepip_options"] == "default-not-inherited"
    major, minor = measured["version"][:2]
    assert {point["name"] for point in projection["points"]} == {"pip", f"pip{major}", f"pip{major}.{minor}"}
    assert len(projection["producer_sha256"]) == 64
    assert any(point["name"] == "pip" for point in pip["entry_points"])
    assert packages.target_metadata(measured) == before
    assert Path(measured["venv"]) == target


@pytest.mark.parametrize("kind", ["missing-file", "missing-record"])
def test_pip_current_wrapper_requires_physical_complete_record(environment, kind):
    _, _, path, _ = environment
    measured = packages._environment(json.loads(path.read_bytes()))
    major, minor = measured["version"][:2]
    point = {"name": f"pip{major}.{minor}"}
    scripts = [script for script in packages._script_paths(measured, point) if script.is_file()]
    assert scripts
    if kind == "missing-file":
        for script in scripts:
            script.unlink()
    else:
        info = next(Path(measured["paths"]["purelib"]).glob("pip-*.dist-info"))
        record = info / "RECORD"
        removed = {script.relative_to(Path(measured["venv"])).as_posix() for script in scripts}
        rows = [row for row in csv.reader(io.StringIO(record.read_text()))
                if packages._relative(info.parent / row[0], Path(measured["venv"])) not in removed]
        output = io.StringIO()
        csv.writer(output, lineterminator="\n").writerows(rows)
        record.write_text(output.getvalue())
    before = packages.target_metadata(measured)
    with pytest.raises(packages.PackageError, match="missing file|script RECORD"):
        packages._inventory(measured)
    assert packages.target_metadata(measured) == before


def test_pip_producer_drift_cannot_execute_changed_target_source(environment, tmp_path, monkeypatch):
    _, _, path, _ = environment
    measured = packages._environment(json.loads(path.read_bytes()))
    producer = Path(measured["paths"]["purelib"]) / "pip/_internal/operations/install/wheel.py"
    sentinel = tmp_path / "foreign-producer-executed"
    original_run = packages._run
    changed = []

    def replace_after_capture(command, **kwargs):
        if any("get_console_script_specs" in argument for argument in command) and not changed:
            producer.write_text(f"from pathlib import Path\nPath({str(sentinel)!r}).touch()\nraise RuntimeError('changed')\n")
            changed.append(packages.target_metadata(measured))
        return original_run(command, **kwargs)

    monkeypatch.setattr(packages, "_run", replace_after_capture)
    with pytest.raises(packages.PackageError, match="original pip/target changed"):
        packages._inventory(measured)
    assert len(changed) == 1 and not sentinel.exists()
    assert packages.target_metadata(measured) == changed[0]


@pytest.mark.parametrize("kind", ["missing", "skip"])
def test_inventory_requires_recorded_pip_even_without_outer_prepare(environment, tmp_path, monkeypatch, kind):
    _, _, path, _ = environment
    measured = packages._environment(json.loads(path.read_bytes()))
    info = next(Path(measured["paths"]["purelib"]).glob("pip-*.dist-info"))
    skipped = {info.relative_to(Path(measured["venv"])).as_posix()}
    if kind == "missing":
        info.rename(tmp_path / "retired-pip.dist-info")
        skipped = set()
    before = packages.target_metadata(measured)

    def never_consume_unrecorded_executor(*args, **kwargs):
        raise AssertionError("unrecorded pip reached subprocess consumption")

    monkeypatch.setattr(packages, "_run", never_consume_unrecorded_executor)
    with pytest.raises(packages.PackageError, match="existing recorded pip executor required"):
        packages._inventory(measured, skip=skipped)
    assert packages.target_metadata(measured) == before


@pytest.mark.parametrize("kind", ["modern", "legacy", "both"])
def test_archive_digest_accepts_only_explicit_consistent_sha256(kind):
    digest = "a" * 64
    info = {}
    if kind in {"modern", "both"}:
        info["hashes"] = {"sha256": digest}
    if kind in {"legacy", "both"}:
        info["hash"] = "sha256=" + digest
    assert packages._archive_sha256(info) == digest


@pytest.mark.parametrize("info", [
    None, {}, {"hash": "md5=" + "a" * 32}, {"hash": "sha256=short"},
    {"hashes": {}}, {"hashes": {"sha256": "short"}},
    {"hashes": None, "hash": "sha256=" + "a" * 64},
    {"hashes": {"sha256": "a" * 64}, "hash": "sha256=" + "b" * 64},
    {"hashes": {"sha256": "a" * 64}, "hash": None},
    {"hash": "sha256=" + "A" * 64},
])
def test_archive_digest_rejects_missing_unsafe_and_ambiguous_metadata(info):
    with pytest.raises(packages.PackageError, match="native archive"):
        packages._archive_sha256(info)


@pytest.mark.parametrize("kind", ["unrecorded", "unchecked-recorded"])
def test_original_executor_ignores_valid_target_pip_bytecode(environment, tmp_path, kind):
    _, artifacts, path, request = environment
    profile = json.loads(path.read_bytes())
    measured = packages._environment(profile)
    source = Path(measured["paths"]["purelib"]) / "pip/__init__.py"
    marker = tmp_path / "target-pip-bytecode-executed"
    raw = source.read_bytes()
    code = compile(raw.decode() + f"\nfrom pathlib import Path\nPath({str(marker)!r}).touch()\n", str(source), "exec")
    metadata = source.stat()
    cache = Path(importlib.util.cache_from_source(str(source)))
    cache.parent.mkdir(exist_ok=True)
    cache.write_bytes(importlib.util.MAGIC_NUMBER + struct.pack("<III", 0, int(metadata.st_mtime), len(raw))
                      + marshal.dumps(code))
    info = next(Path(measured["paths"]["purelib"]).glob("pip-*.dist-info"))
    record = info / "RECORD"
    relative = cache.relative_to(Path(measured["venv"])).as_posix()
    rows = [row for row in csv.reader(io.StringIO(record.read_text()))
            if packages._relative(info.parent / row[0], Path(measured["venv"])) != relative]
    if kind == "unchecked-recorded":
        rows.append([os.path.relpath(cache, info.parent).replace(os.sep, "/"), "", ""])
    output = io.StringIO()
    csv.writer(output, lineterminator="\n").writerows(rows)
    record.write_text(output.getvalue())
    before = packages.target_metadata(measured)
    value = request(wheel(artifacts, "alpha", "1.0"))
    plan = packages.prepare_package_plan(value, {"module:alpha"})
    assert set(plan["checks"].values()) == {"SUCCESS"}
    assert not marker.exists() and packages.target_metadata(measured) == before


def test_added_snapshot_bytecode_is_rejected_before_original_child(environment, tmp_path, monkeypatch):
    _, _, path, _ = environment
    measured = packages._environment(json.loads(path.read_bytes()))
    before = packages.target_metadata(measured)
    marker = tmp_path / "snapshot-bytecode-executed"
    original_run = packages._run
    injected = []

    def inject_before_actual_run(command, **kwargs):
        if any("get_console_script_specs" in argument for argument in command) and not injected:
            snapshot = next(iter(packages._HELD.pip_sources.values()))["snapshot"]
            source = snapshot / "pip/__init__.py"
            raw = source.read_bytes()
            code = compile(raw.decode() + f"\nfrom pathlib import Path\nPath({str(marker)!r}).touch()\n", str(source), "exec")
            state = source.stat()
            cache = Path(importlib.util.cache_from_source(str(source)))
            cache.parent.mkdir()
            cache.write_bytes(importlib.util.MAGIC_NUMBER + struct.pack("<III", 0, int(state.st_mtime), len(raw))
                              + marshal.dumps(code))
            injected.append(True)
        return original_run(command, **kwargs)

    monkeypatch.setattr(packages, "_run", inject_before_actual_run)
    with pytest.raises(packages.PackageError, match="snapshot tree changed"):
        packages._inventory(measured)
    assert injected == [True] and not marker.exists()
    assert packages.target_metadata(measured) == before


@pytest.mark.parametrize("kind", ["legacy", "modern", "conflicting"])
def test_native_resolution_rejects_changed_archive_digest(environment, monkeypatch, kind):
    _, artifacts, path, request = environment
    item = wheel(artifacts, "alpha", "1.0")
    measured = packages._environment(json.loads(path.read_bytes()))
    before = packages.target_metadata(measured)
    original_run = packages._run
    observed = []

    def alter_actual_report(command, **kwargs):
        raw = original_run(command, **kwargs)
        if "--report" in command:
            report = json.loads(raw)
            wrong = "f" * 64
            assert wrong != item["sha256"]
            info = ({"hash": "sha256=" + wrong} if kind == "legacy" else {"hashes": {"sha256": wrong}})
            if kind == "conflicting":
                info["hash"] = "sha256=" + item["sha256"]
            report["install"][0]["download_info"]["archive_info"] = info
            observed.append(True)
            return json.dumps(report)
        return raw

    monkeypatch.setattr(packages, "_run", alter_actual_report)
    with pytest.raises(packages.PackageError, match="resolution differs|fields disagree"):
        packages.prepare_package_plan(request(item), {"module:alpha"})
    assert observed == [True] and packages.target_metadata(measured) == before


def test_real_apply_verify_and_paired_dependency_rollback(environment, tmp_path):
    target, artifacts, _, request = environment
    old = packages.prepare_package_plan(request(wheel(artifacts, "alpha", "0.1")), {"module:alpha"})
    packages.apply_package_plan(old, tmp_path / "old-receipt.json", {"module:alpha"})
    upgrade = wheel(artifacts, "alpha", "1.0", requires=["beta>=1.0"])
    dependency = wheel(artifacts, "beta", "1.0", entry_points=False)
    dependency.update(source_kind="distribution-release", source_commit=None,
                      source_repository="https://example.invalid/beta-1.0-py3-none-any.whl")
    plan = packages.prepare_package_plan(request(upgrade, dependency), {"module:alpha"})
    receipt = tmp_path / "transaction.json"
    assert packages.apply_package_plan(plan, receipt, {"module:alpha"})["state"] == "applied"
    checked = packages.verify_package_receipt(plan, receipt, {"module:alpha"})
    assert checked["status"] == "verified" and checked["runtime_verified"] is False
    assert {row["distribution"] for row in checked["installed"]} == {"alpha", "beta"}
    assert packages.rollback_package_plan(plan, receipt, {"module:alpha"})["beforestate_restored"] is True
    assert "0.1" in (Path(plan["environment"]["paths"]["purelib"]) / "alpha/__init__.py").read_text()
    assert not (Path(plan["environment"]["paths"]["purelib"]) / "beta").exists()
    assert target.is_dir()


@pytest.mark.parametrize("kind", ["fifo", "oversize", "identity-drift"])
def test_direct_url_replacement_after_inventory_fails_before_parse(environment, tmp_path, monkeypatch, kind):
    if kind == "fifo" and os.name == "nt":
        pytest.skip("physical FIFO requires POSIX")
    target, artifacts, _, request = environment
    plan = packages.prepare_package_plan(request(wheel(artifacts, "alpha", "1.0")), {"module:alpha"})
    receipt = tmp_path / "transaction.json"
    packages.apply_package_plan(plan, receipt, {"module:alpha"})
    original_receipt = receipt.read_bytes()
    source = Path(plan["environment"]["paths"]["purelib"]) / "alpha-1.0.dist-info/direct_url.json"
    source_relative = source.relative_to(target).as_posix()
    footprint = set(plan["before"]["files"]) - {source_relative}
    original_inventory = packages._inventory
    changed = []

    def identity():
        value = source.lstat()
        return value.st_dev, value.st_ino, value.st_mode, value.st_size, value.st_mtime_ns

    def capture_then_replace(*args, **kwargs):
        result = original_inventory(*args, **kwargs)
        if sys._getframe(1).f_code.co_name == "_complete_afterstate" and not changed:
            original = source.read_bytes()
            previous_identity = source.stat().st_ino
            if kind == "fifo":
                source.unlink()
                os.mkfifo(source)
            elif kind == "oversize":
                source.write_bytes(original + b" " * (packages._MAX_METADATA_BYTES + 1))
            else:
                replacement = source.with_suffix(".replacement")
                value = json.loads(original)
                value["synthetic_fixture_drift"] = True
                replacement.write_text(json.dumps(value))
                os.replace(replacement, source)
                assert source.stat().st_ino != previous_identity
            changed.append((identity(), packages._file_state(target, footprint)))
        return result

    def no_later_wheel_validation(*args, **kwargs):
        raise AssertionError("changed provenance reached later wheel validation")

    monkeypatch.setattr(packages, "_inventory", capture_then_replace)
    monkeypatch.setattr(packages, "_wheel", no_later_wheel_validation)
    started = time.monotonic()
    with pytest.raises(packages.PackageError, match=(
            "unsupported or oversized technical input|installed wheel provenance changed after inventory capture")):
        packages.verify_package_receipt(plan, receipt, {"module:alpha"})
    assert time.monotonic() - started < 10
    assert len(changed) == 1
    assert identity() == changed[0][0]
    assert packages._file_state(target, footprint) == changed[0][1]
    assert receipt.read_bytes() == original_receipt
    assert "alpha" not in sys.modules


def test_root_repro_missing_old_console_record_is_rejected_before_mutation(environment, tmp_path):
    _, artifacts, _, request = environment
    old = packages.prepare_package_plan(request(wheel(artifacts, "alpha", "0.1", console_script=True)), {"module:alpha"})
    packages.apply_package_plan(old, tmp_path / "old.json", {"module:alpha"})
    script = Path(old["environment"]["paths"]["scripts"]) / ("alpha-cli.exe" if os.name == "nt" else "alpha-cli")
    original = script.read_bytes()
    record = Path(old["environment"]["paths"]["purelib"]) / "alpha-0.1.dist-info/RECORD"
    rows = [row for row in csv.reader(io.StringIO(record.read_text())) if "alpha-cli" not in row[0]]
    output = io.StringIO()
    csv.writer(output, lineterminator="\n").writerows(rows)
    record.write_text(output.getvalue())
    before = packages.package_target_state(old)
    with pytest.raises(packages.PackageError, match="script RECORD"):
        packages.prepare_package_plan(request(wheel(artifacts, "alpha", "1.0")), {"module:alpha"})
    assert packages.package_target_state(old) == before
    assert script.read_bytes() == original


def test_complete_console_record_is_restored_byte_exactly(environment, tmp_path):
    _, artifacts, _, request = environment
    old = packages.prepare_package_plan(request(wheel(artifacts, "alpha", "0.1", console_script=True)), {"module:alpha"})
    packages.apply_package_plan(old, tmp_path / "old.json", {"module:alpha"})
    script = Path(old["environment"]["paths"]["scripts"]) / ("alpha-cli.exe" if os.name == "nt" else "alpha-cli")
    original = script.read_bytes()
    plan = packages.prepare_package_plan(request(wheel(artifacts, "alpha", "1.0")), {"module:alpha"})
    packages.apply_package_plan(plan, tmp_path / "new.json", {"module:alpha"})
    assert not script.exists()
    packages.rollback_package_plan(plan, tmp_path / "new.json", {"module:alpha"})
    assert script.read_bytes() == original


def test_root_repro_unselected_reverse_dependency_blocks_upgrade(environment, tmp_path):
    _, artifacts, _, request = environment
    consumer = wheel(artifacts, "consumer", "1.0", requires=["alpha<1"], entry_points=False)
    old = packages.prepare_package_plan(request(wheel(artifacts, "alpha", "0.1"), consumer,
                                                required=False), {"module:alpha"})
    packages.apply_package_plan(old, tmp_path / "old.json", {"module:alpha"})
    _, profile = packages._profile(old["request"]["profile_id"], old["request"]["profile_sha256"])
    with packages._venv_mutex(profile):
        native_check = packages._pip(old["environment"], profile, [], dry_run=False)
        native_check = native_check[:native_check.index("install")] + ["check"]
        packages._run(native_check)
    before = packages.package_target_state(old)
    with pytest.raises(packages.PackageError):
        packages.prepare_package_plan(request(wheel(artifacts, "alpha", "1.0")), {"module:alpha"})
    assert packages.package_target_state(old) == before
    with packages._venv_mutex(profile):
        native_check = packages._pip(old["environment"], profile, [], dry_run=False, check=True)
        packages._run(native_check)


def test_mutex_is_shared_across_distinct_profiles_and_journals(environment, tmp_path):
    _, artifacts, profile_path, request = environment
    value = request(wheel(artifacts, "alpha", "1.0"))
    profile = json.loads(profile_path.read_bytes())
    other = {**profile, "id": "other-synthetic-profile"}
    other_path = profile_path.with_name(other["id"] + ".json")
    other_path.write_text(json.dumps(other))
    value.update(profile_id=other["id"], profile_sha256=hashlib.sha256(other_path.read_bytes()).hexdigest())
    code = ("import sys,json;sys.path.insert(0,sys.argv[1]);from tools import python_packages as p;"
            "\ntry:p.prepare_package_plan(json.loads(sys.argv[2]),{'module:alpha'})"
            "\nexcept p.PackageError:print(json.dumps({'blocked':True}))"
            "\nelse:print(json.dumps({'blocked':False}))")
    with packages._venv_mutex(profile):
        run = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", code,
                              str(Path(__file__).resolve().parents[1]), json.dumps(value)],
                             capture_output=True, timeout=15)
        assert run.returncode == 0 and json.loads(run.stdout)["blocked"] is True
    assert packages.prepare_package_plan(value, {"module:alpha"})["request"]["profile_id"] == other["id"]


@pytest.mark.parametrize("state", ["applying", "applied"])
def test_physical_crash_uses_one_authoritative_journal_without_log_hash_window(environment, tmp_path, state):
    _, artifacts, _, request = environment
    plan = packages.prepare_package_plan(request(wheel(artifacts, "alpha", "1.0")), {"module:alpha"})
    before = packages.package_target_state(plan)
    source = tmp_path / "plan.json"
    source.write_text(json.dumps(plan))
    log = tmp_path / "activation.json"
    code = ("import sys,os,json;sys.path.insert(0,sys.argv[1]);from pathlib import Path;"
            "from tools import python_packages as p; original=p._store_receipt;"
            "\ndef store(path,value,**kw):"
            "\n original(path,value,**kw)"
            "\n if value['state']==sys.argv[4]:os._exit(93)"
            "\np._store_receipt=store;"
            "p.apply_package_plan(json.loads(Path(sys.argv[2]).read_bytes()),Path(sys.argv[3]),"
            "{'module:alpha'},activation_log=True)")
    run = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", code,
                          str(Path(__file__).resolve().parents[1]), str(source), str(log), state],
                         capture_output=True, timeout=120)
    assert run.returncode == 93
    stored = json.loads(log.read_bytes())["entries"]
    assert len(stored) == 1 and stored[0]["transaction"]["state"] == state
    assert "receipt_sha256" not in stored[0] and "receipt" not in stored[0]
    if state == "applied":
        assert packages.verify_package_receipt(plan, log, {"module:alpha"})["status"] == "verified"
        assert packages.rollback_package_plan(plan, log, {"module:alpha"})["beforestate_restored"] is True
    else:
        current = packages.package_target_state(plan)
        with pytest.raises(packages.PackageError, match="interrupted"):
            packages.rollback_package_plan(plan, log, {"module:alpha"})
        assert packages.package_target_state(plan) == current == before


@pytest.mark.parametrize("kind", ["file", "snapshot"])
def test_rollback_rejects_afterstate_or_snapshot_drift_without_mutation(environment, tmp_path, kind):
    _, artifacts, _, request = environment
    plan = packages.prepare_package_plan(request(wheel(artifacts, "alpha", "1.0")), {"module:alpha"})
    receipt = tmp_path / "transaction.json"
    packages.apply_package_plan(plan, receipt, {"module:alpha"})
    if kind == "file":
        path = Path(plan["environment"]["paths"]["purelib"]) / "alpha/__init__.py"
        path.write_text("FOREIGN_CHANGE = True\n")
    else:
        value = json.loads(receipt.read_text())
        # Add a corrupted snapshot for a formerly absent package path.
        value["before"]["files"]["foreign"] = {"sha256": "0" * 64, "mode": 0o600}
        value["backup"]["foreign"] = base64.b64encode(b"bad").decode()
        receipt.write_text(json.dumps(packages._with_hash({key: item for key, item in value.items()
                                                         if key != "content_hash"})))
    before = packages.package_target_state(plan)
    with pytest.raises(packages.PackageError):
        packages.rollback_package_plan(plan, receipt, {"module:alpha"})
    assert packages.package_target_state(plan) == before


@pytest.mark.parametrize("kind", ["closure", "entry-point", "scope", "artifact", "free-target"])
def test_invalid_package_requests_fail_before_install(environment, kind):
    _, artifacts, _, request = environment
    item = wheel(artifacts, "alpha", "1.0", requires=["missing_dependency>=1"] if kind == "closure" else [])
    value = request(item)
    if kind == "entry-point":
        value["required_entry_points"][0]["value"] = "alpha:does_not_exist"
    elif kind == "scope":
        item["component_ref"] = "module:unapproved"
    elif kind == "artifact":
        (artifacts / item["filename"]).write_bytes(b"tampered")
    elif kind == "free-target":
        value["venv"] = "/untrusted/request/path"
    with pytest.raises(packages.PackageError):
        packages.prepare_package_plan(value, {"module:alpha"})


def test_site_hooks_pythonpath_and_pip_configuration_are_not_executed(environment, tmp_path, monkeypatch):
    _, artifacts, _, request = environment
    item = wheel(artifacts, "alpha", "1.0")
    plan = packages.prepare_package_plan(request(item), {"module:alpha"})
    site = Path(plan["environment"]["paths"]["purelib"])
    sentinel = tmp_path / "HOSTILE_CODE_RAN"
    text = f"import pathlib; pathlib.Path({str(sentinel)!r}).write_text('executed')\n"
    (site / "sitecustomize.py").write_text(text)
    (site / "hostile.pth").write_text("import sitecustomize\n")
    foreign = tmp_path / "foreign-pythonpath"
    foreign.mkdir()
    (foreign / "sitecustomize.py").write_text(text)
    monkeypatch.setenv("PYTHONPATH", str(foreign))
    config = tmp_path / "pip.conf"
    config.write_text("[install]\ntarget = " + str(tmp_path / "unapproved-target") + "\n")
    monkeypatch.setenv("PIP_CONFIG_FILE", str(config))
    monkeypatch.setenv("PIP_TARGET", str(tmp_path / "unapproved-target"))
    plan = packages.prepare_package_plan(request(item), {"module:alpha"})
    packages.apply_package_plan(plan, tmp_path / "safe-receipt.json", {"module:alpha"})
    assert not sentinel.exists()
    assert not (tmp_path / "unapproved-target").exists()


@pytest.mark.parametrize("kind", ["missing-root", "unknown-id", "profile-drift", "legacy-variable"])
def test_profile_authority_is_only_configured_root_id_and_raw_hash(environment, kind, monkeypatch):
    target, artifacts, profile_path, request = environment
    value = request(wheel(artifacts, "alpha", "1.0"))
    if kind == "unknown-id":
        value["profile_id"] = "other-profile"
    elif kind == "profile-drift":
        profile_path.write_bytes(profile_path.read_bytes() + b"\n")
    else:
        monkeypatch.delenv("OCEAN_PYTHON_PROFILES_ROOT")
        if kind == "legacy-variable":
            monkeypatch.setenv("OCEAN_PYTHON_ENVIRONMENT_PROFILE", str(profile_path))
    assert not (target / "lib" / "alpha").exists()
    with pytest.raises((packages.PackageError, OSError)):
        packages.prepare_package_plan(value, {"module:alpha"})


def test_actual_ocean_core_uses_one_package_log_for_verify_and_rollback(environment, tmp_path):
    from tools.ocean_dev import main
    from tools.resolve_bundles import canonical_hash

    target, artifacts, _, request = environment
    item = wheel(artifacts, "alpha", "1.0")
    plan = packages.prepare_package_plan(request(item), {"module:alpha"})
    recipe = tmp_path / "recipe"
    bundle_dir = recipe / "manifests" / "bundles" / "synthetic-package"
    bundle_dir.mkdir(parents=True)
    bundle = {"schema": "ellmos.bundle.v1", "id": "synthetic-package", "version": "1.0.0",
              "components": [{"type": "module", "ref": {"ref": "module:alpha", "version": "1.0"},
                              "role": "synthetic-qa", "requirement": "required",
                              "provides": ["synthetic.package"], "consumes": []}], "choice_groups": []}
    bundle["content_hash"] = canonical_hash(bundle)
    (bundle_dir / "bundle.v1.json").write_text(json.dumps(bundle))
    system = tmp_path / "system.json"
    system.write_text(json.dumps({"schema": "ellmos.system.v1", "id": "synthetic-package",
                                 "authority": {"runtime_authority": False},
                                 "bundle_refs": [{"ref": bundle["id"], "content_hash": bundle["content_hash"]}]}))
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"modules": [{"id": "alpha", "source_of_truth": {
        "type": "git-repository", "repository": item["source_repository"]},
        "version": "1.0", "commit_sha": item["source_commit"], "provides": ["synthetic.package"]}]}))
    bindings = {"schema": "ellmos.open-ocean-component-bindings.v1", "id": "synthetic-package",
                "version": "1.0.0", "authority": {"kind": "integration-overlay", "runtime_authority": False},
                "bindings": {"module:alpha": {"component_type": "module", "catalog_id": "alpha",
                    "repository": item["source_repository"], "commit": item["source_commit"],
                    "placement_id": "alpha", "required_provides": ["synthetic.package"],
                    "provider_manifest": "ellmos-module.v2.json"}}}
    bindings["content_hash"] = canonical_hash(bindings)
    binding_path = tmp_path / "bindings.json"
    binding_path.write_text(json.dumps(bindings))
    skills = tmp_path / "skills.json"
    skills.write_text(json.dumps({"components": []}))
    workspace = tmp_path / "workspace"
    log = tmp_path / "activation.json"
    common = ["--workspace", str(workspace), "--expected-components-json", '["module:alpha"]',
              "--python-package-plan-json", json.dumps(plan)]
    operation = ["--bundles-root", str(recipe), "--system-manifest", str(system),
                 "--modules-catalog", str(catalog), "--skills-registry", str(skills),
                 "--component-bindings", str(binding_path), "--activation-log", str(log), "--json"]
    before = packages.package_target_state(plan)
    assert main(common + operation) == 0
    assert packages.package_target_state(plan) == before and not workspace.exists() and not log.exists()
    assert main(common + operation + ["--apply"]) == 0
    assert not (workspace / "modules" / "alpha").exists()
    entries = json.loads(log.read_bytes())["entries"]
    assert len(entries) == 1 and entries[0]["type"] == "python-packages"
    assert main(common + ["--verify-python-packages", str(log)]) == 0
    installed = packages.package_target_state(plan)
    assert main(common + operation + ["--apply"]) != 0
    assert packages.package_target_state(plan) == installed
    assert main(common + ["--rollback", str(log)]) == 0
    assert target.exists() and not (Path(plan["environment"]["paths"]["purelib"]) / "alpha").exists()


@pytest.mark.parametrize("kind", ["shared-owner", "legacy", "unrecorded-dist-info", "headers",
                                  "egg-link", "easy-install", "pep660-finder", "pep660-metadata"])
def test_unsupported_or_shared_old_footprints_fail_before_mutation(environment, tmp_path, kind):
    _, artifacts, _, request = environment
    old = packages.prepare_package_plan(request(wheel(artifacts, "alpha", "0.1"),
                                                wheel(artifacts, "consumer", "1.0", entry_points=False),
                                                required=False), {"module:alpha"})
    packages.apply_package_plan(old, tmp_path / "old.json", {"module:alpha"})
    site = Path(old["environment"]["paths"]["purelib"])
    if kind == "shared-owner":
        record = site / "consumer-1.0.dist-info/RECORD"
        with record.open("a", newline="") as file:
            csv.writer(file).writerow(["alpha/__init__.py", "", ""])
    elif kind == "legacy":
        (site / "legacy.egg-info").mkdir()
    elif kind == "unrecorded-dist-info":
        (site / "alpha-0.1.dist-info/foreign-metadata").write_bytes(b"preserve")
    elif kind == "egg-link":
        (site / "legacy.egg-link").write_text("synthetic external editable")
    elif kind == "easy-install":
        (site / "easy-install.pth").write_text("synthetic external editable")
    elif kind == "pep660-finder":
        (site / "__editable___legacy_finder.py").write_text("# unsupported editable")
    elif kind == "pep660-metadata":
        source = site / "alpha-0.1.dist-info/direct_url.json"
        source.write_text(json.dumps({"dir_info": {"editable": True}}))
    item = wheel(artifacts, "alpha", "1.0", extra_files=(
        {"alpha-1.0.data/headers/alpha.h": b"unsupported"} if kind == "headers" else None))
    before = packages.package_target_state(old)
    with pytest.raises(packages.PackageError):
        packages.prepare_package_plan(request(item), {"module:alpha"})
    assert packages.package_target_state(old) == before


def test_native_hash_fragment_rejects_wrong_digest_without_target_mutation(environment):
    _, artifacts, profile_path, request = environment
    item = wheel(artifacts, "alpha", "1.0")
    profile = json.loads(profile_path.read_bytes())
    measured = packages._environment(profile)
    validated = packages._wheel(item, profile, measured)
    before = packages.target_metadata(measured)
    with packages._venv_mutex(profile), packages._frozen_wheels(profile, [validated], measured) as frozen:
        command = packages._pip(measured, frozen, [validated], dry_run=False)
        expected_uri = (Path(frozen["artifact_root"]) / item["filename"]).as_uri()
        assert command[-1] == expected_uri + "#sha256=" + item["sha256"]
        assert item["sha256"] != "f" * 64
        command[-1] = expected_uri + "#sha256=" + "f" * 64
        with pytest.raises(packages.PackageError, match="pinned package executor failed"):
            packages._run(command)
    assert packages.target_metadata(measured) == before


def test_executor_consumes_frozen_wheel_bytes_even_if_original_changes(environment):
    _, artifacts, profile_path, request = environment
    item = wheel(artifacts, "alpha", "1.0")
    value = request(item)
    _, profile = packages._profile(value["profile_id"], value["profile_sha256"])
    measured = packages._environment(profile)
    validated = packages._wheel(item, profile, measured)
    before = packages.target_metadata(measured)
    with packages._venv_mutex(profile), packages._frozen_wheels(profile, [validated], measured) as frozen:
        (artifacts / item["filename"]).write_bytes(b"concurrent external change")
        report = json.loads(packages._run(packages._pip(measured, frozen, [validated], dry_run=True)))
        assert packages._archive_sha256(report["install"][0]["download_info"]["archive_info"]) == item["sha256"]
    assert packages.target_metadata(measured) == before
    with pytest.raises(packages.PackageError, match="immutable artifact"):
        packages.prepare_package_plan(value, {"module:alpha"})


@pytest.mark.parametrize("kind", ["read-bytes", "expanded", "member-count"])
def test_real_input_and_zip_bounds(environment, monkeypatch, kind):
    _, artifacts, profile_path, request = environment
    item = wheel(artifacts, "alpha", "1.0")
    if kind == "read-bytes":
        with pytest.raises(packages.PackageError, match="oversized"):
            packages._read_bytes(artifacts / item["filename"], limit=8)
        return
    value = request(item)
    _, profile = packages._profile(value["profile_id"], value["profile_sha256"])
    measured = packages._environment(profile)
    monkeypatch.setattr(packages, "_MAX_EXPANDED_BYTES" if kind == "expanded" else "_MAX_FILES", 1)
    with pytest.raises(packages.PackageError, match="bound|oversized"):
        packages._wheel(item, profile, measured)


@pytest.mark.skipif(os.name == "nt", reason="POSIX special-file check")
def test_special_file_read_fails_without_waiting_for_a_writer(tmp_path):
    pipe = tmp_path / "unsupported-pipe"
    os.mkfifo(pipe)
    started = time.monotonic()
    with pytest.raises(packages.PackageError, match="unsupported"):
        packages._read_bytes(pipe)
    assert time.monotonic() - started < 2


@pytest.mark.parametrize("kind", ["timeout", "output"])
def test_real_process_and_output_bounds_stop_child_before_delayed_mutation(tmp_path, monkeypatch, kind):
    marker = tmp_path / "late-mutation"
    grandchild = f"import time,pathlib;time.sleep(2);pathlib.Path({str(marker)!r}).touch()"
    code = (f"import subprocess,sys,time;subprocess.Popen([sys.executable,'-I','-S','-B','-c',{grandchild!r}]);"
            + ("time.sleep(30)" if kind == "timeout" else "sys.stdout.write('x'*2000000);sys.stdout.flush();time.sleep(30)"))
    monkeypatch.setattr(packages, "_MAX_OUTPUT_BYTES", 4096)
    with pytest.raises(packages.PackageError, match="terminated"):
        packages._run([sys.executable, "-I", "-S", "-B", "-c", code], timeout=.4)
    time.sleep(2.1)
    assert not marker.exists()


@pytest.mark.skipif(os.name != "nt", reason="physical Windows Job process-tree evidence")
@pytest.mark.parametrize("exit_kind", ["normal", "failed", "timeout"])
def test_windows_job_terminates_quiet_grandchild_and_confirms_zero_active_processes(
    tmp_path, monkeypatch, exit_kind
):
    import ctypes
    from ctypes import wintypes
    pid_path = tmp_path / "grandchild.pid"
    marker = tmp_path / "late-grandchild-mutation"
    grandchild = f"import pathlib,time;time.sleep(10);pathlib.Path({str(marker)!r}).touch()"
    code = ("import subprocess,sys,pathlib,time;"
            f"p=subprocess.Popen([sys.executable,'-I','-S','-B','-c',{grandchild!r}],"
            "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);"
            f"pathlib.Path({str(pid_path)!r}).write_text(str(p.pid));"
            + {"normal": "pass", "failed": "raise SystemExit(7)", "timeout": "time.sleep(30)"}[exit_kind])
    actual = packages._WindowsJob
    confirmed = []
    pre_resume = []
    class ObservedJob(actual):
        def resume(self, pid):
            pre_resume.append(self.active())
            super().resume(pid)
        def terminate(self):
            super().terminate()
            confirmed.append(self.active())
    monkeypatch.setattr(packages, "_WindowsJob", ObservedJob)
    if exit_kind == "normal":
        packages._run([sys.executable, "-I", "-S", "-B", "-c", code], timeout=5)
    else:
        with pytest.raises(packages.PackageError):
            packages._run([sys.executable, "-I", "-S", "-B", "-c", code], timeout=5)
    assert pid_path.is_file() and confirmed and set(confirmed) == {0}
    assert pre_resume == [1]
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    api.GetExitCodeProcess.restype = wintypes.BOOL
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = api.OpenProcess(0x1000, False, int(pid_path.read_text()))
    if handle:
        try:
            status = wintypes.DWORD()
            assert api.GetExitCodeProcess(handle, ctypes.byref(status)) and status.value != 259
        finally:
            api.CloseHandle(handle)
    time.sleep(10.1)
    assert not marker.exists()


def crash_after_native_pip(plan, tmp_path, label):
    source = tmp_path / (label + ".plan.json")
    source.write_text(json.dumps(plan))
    journal = tmp_path / (label + ".journal.json")
    code = (
        "import sys,os,json;sys.path.insert(0,sys.argv[1]);from pathlib import Path;"
        "from tools import python_packages as p;real=p._run;"
        "\ndef run(command,**kw):"
        "\n value=real(command,**kw)"
        "\n if 'install' in command and '--dry-run' not in command:os._exit(93)"
        "\n return value"
        "\np._run=run;"
        "p.apply_package_plan(json.loads(Path(sys.argv[2]).read_bytes()),Path(sys.argv[3]),"
        "{'module:alpha'},activation_log=True)"
    )
    run = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", code,
                          str(Path(__file__).resolve().parents[1]), str(source), str(journal)],
                         capture_output=True, timeout=120)
    assert run.returncode == 93
    assert json.loads(journal.read_bytes())["entries"][0]["transaction"]["state"] == "applying"
    return journal


def test_crash_after_real_pip_before_receipt_is_reconciled_without_pip_replay(environment, tmp_path, monkeypatch):
    _, artifacts, _, request = environment
    old = packages.prepare_package_plan(request(wheel(artifacts, "alpha", "0.1")), {"module:alpha"})
    packages.apply_package_plan(old, tmp_path / "old.json", {"module:alpha"})
    plan = packages.prepare_package_plan(request(wheel(artifacts, "alpha", "1.0")), {"module:alpha"})
    journal = crash_after_native_pip(plan, tmp_path, "after-pip")
    evidence = packages.inspect_package_recovery(plan, journal, {"module:alpha"})
    assert evidence["complete_afterstate"] is not None
    real = packages._run
    def no_replay(command, **kwargs):
        assert "install" not in command
        return real(command, **kwargs)
    monkeypatch.setattr(packages, "_run", no_replay)
    assert packages.reconcile_package_receipt(plan, journal, {"module:alpha"}, evidence)["status"] == "verified"
    assert packages.rollback_package_plan(plan, journal, {"module:alpha"})["beforestate_restored"] is True


@pytest.mark.parametrize("kind", ["journal", "target", "profile", "backup", "unselected"])
def test_recovery_drift_fails_without_any_restore(environment, tmp_path, kind):
    _, artifacts, profile_path, request = environment
    plan = packages.prepare_package_plan(request(wheel(artifacts, "alpha", "1.0")), {"module:alpha"})
    journal = crash_after_native_pip(plan, tmp_path, "drift")
    evidence = packages.inspect_package_recovery(plan, journal, {"module:alpha"})
    if kind == "journal":
        journal.write_bytes(journal.read_bytes() + b"\n")
    elif kind == "profile":
        profile_path.write_bytes(profile_path.read_bytes() + b"\n")
    elif kind == "target":
        file = Path(plan["environment"]["paths"]["purelib"]) / "alpha/__init__.py"
        file.write_text("legitimate concurrent change")
    elif kind == "unselected":
        (Path(plan["environment"]["venv"]) / "foreign-file").write_bytes(b"preserve")
    else:
        value = json.loads(journal.read_bytes())
        transaction = value["entries"][0]["transaction"]
        transaction["backup"]["not-in-beforestate"] = base64.b64encode(b"untrusted").decode()
        value["entries"][0]["transaction"] = packages._with_hash(
            {key: item for key, item in transaction.items() if key != "content_hash"})
        journal.write_text(json.dumps(value))
    before = packages.target_metadata(plan["environment"])
    raw = journal.read_bytes()
    with pytest.raises((packages.PackageError, OSError, ValueError)):
        packages.rollback_package_plan(plan, journal, {"module:alpha"}, recovery=evidence)
    assert packages.target_metadata(plan["environment"]) == before and journal.read_bytes() == raw


def test_interrupted_real_restore_requires_fresh_snapshot_and_can_finish_without_pip_replay(environment, tmp_path):
    _, artifacts, _, request = environment
    old = packages.prepare_package_plan(request(wheel(artifacts, "alpha", "0.1", console_script=True)), {"module:alpha"})
    packages.apply_package_plan(old, tmp_path / "old.json", {"module:alpha"})
    plan = packages.prepare_package_plan(request(wheel(artifacts, "alpha", "1.0")), {"module:alpha"})
    journal = tmp_path / "restore.json"
    packages.apply_package_plan(plan, journal, {"module:alpha"}, activation_log=True)
    source = tmp_path / "restore-plan.json"
    source.write_text(json.dumps(plan))
    code = (
        "import sys,os,json;sys.path.insert(0,sys.argv[1]);from pathlib import Path;"
        "from tools import python_packages as p;real=p.os.replace;root=Path(sys.argv[4]);"
        "\ndef replace(source,target):"
        "\n real(source,target)"
        "\n if Path(target).is_relative_to(root):os._exit(94)"
        "\np.os.replace=replace;"
        "p.rollback_package_plan(json.loads(Path(sys.argv[2]).read_bytes()),Path(sys.argv[3]),{'module:alpha'})"
    )
    run = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", code,
                          str(Path(__file__).resolve().parents[1]), str(source), str(journal),
                          plan["environment"]["venv"]], capture_output=True, timeout=120)
    assert run.returncode == 94
    assert json.loads(journal.read_bytes())["entries"][0]["transaction"]["state"] == "rolling-back"
    before = packages.target_metadata(plan["environment"])
    with pytest.raises(packages.PackageError, match="interrupted"):
        packages.rollback_package_plan(plan, journal, {"module:alpha"})
    assert packages.target_metadata(plan["environment"]) == before
    evidence = packages.inspect_package_recovery(plan, journal, {"module:alpha"})
    assert packages.rollback_package_plan(plan, journal, {"module:alpha"}, recovery=evidence)["beforestate_restored"] is True
    assert packages.target_metadata(plan["environment"]) == plan["before"]["target_metadata"]


@pytest.mark.skipif(os.name == "nt", reason="physical POSIX inherited flock and SIGKILL evidence")
def test_mid_pip_parent_sigkill_retains_kernel_mutex_until_writer_dies_and_recovery_restores(environment, tmp_path):
    """Stop real pip only after its first physical wheel write, never before I/O."""
    import signal
    target, artifacts, _, request = environment
    payload = {f"alpha/chunk_{index:05}.bin": b"synthetic-data" * 64 for index in range(8000)}
    plan = packages.prepare_package_plan(request(wheel(artifacts, "alpha", "1.0", extra_files=payload)),
                                         {"module:alpha"})
    source = tmp_path / "mid-pip-plan.json"
    source.write_text(json.dumps(plan))
    journal = tmp_path / "mid-pip-journal.json"
    pid_path = tmp_path / "actual-pip.pid"
    code = (
        "import sys,json;sys.path.insert(0,sys.argv[1]);from pathlib import Path;"
        "from tools import python_packages as p;real=p.subprocess.Popen;"
        "\ndef spawn(command,*args,**kw):"
        "\n child=real(command,*args,**kw)"
        "\n if 'install' in command and '--dry-run' not in command:Path(sys.argv[4]).write_text(str(child.pid))"
        "\n return child"
        "\np.subprocess.Popen=spawn;"
        "p.apply_package_plan(json.loads(Path(sys.argv[2]).read_bytes()),Path(sys.argv[3]),"
        "{'module:alpha'},activation_log=True)"
    )
    parent = subprocess.Popen([sys.executable, "-I", "-S", "-B", "-c", code,
                               str(Path(__file__).resolve().parents[1]), str(source), str(journal), str(pid_path)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    writer = None
    try:
        first = Path(plan["environment"]["paths"]["purelib"]) / "alpha/chunk_00000.bin"
        deadline = time.monotonic() + 90
        while not first.is_file():
            assert parent.poll() is None, "parent exited before real pip mutation"
            assert time.monotonic() < deadline, "real wheel write was not observed"
            time.sleep(.001)
        assert pid_path.is_file()
        writer = int(pid_path.read_text())
        os.kill(writer, signal.SIGSTOP)
        assert first.read_bytes() == payload["alpha/chunk_00000.bin"]
        os.kill(parent.pid, signal.SIGKILL)
        assert parent.wait(timeout=10) == -signal.SIGKILL
        # PID is observation only. The actual kernel lock denies recovery.
        raw = journal.read_bytes()
        assert json.loads(raw)["entries"][0]["transaction"]["state"] == "applying"
        with pytest.raises(packages.PackageError, match="active package operation"):
            packages.inspect_package_recovery(plan, journal, {"module:alpha"})
        assert journal.read_bytes() == raw
        os.killpg(writer, signal.SIGKILL)
        deadline = time.monotonic() + 10
        while True:
            try:
                evidence = packages.inspect_package_recovery(plan, journal, {"module:alpha"})
                break
            except packages.PackageError as exc:
                if "active package operation" not in str(exc):
                    raise
                assert time.monotonic() < deadline
                time.sleep(.01)
        assert evidence["complete_afterstate"] is None
        assert evidence["journal_sha256"] == hashlib.sha256(raw).hexdigest()
        assert evidence["observed"]["target_metadata"] != plan["before"]["target_metadata"]
        assert packages.rollback_package_plan(plan, journal, {"module:alpha"}, recovery=evidence)[
            "beforestate_restored"] is True
        assert packages.target_metadata(plan["environment"]) == plan["before"]["target_metadata"]
        assert target.is_dir()
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=10)
        if writer is not None:
            try:
                os.killpg(writer, signal.SIGKILL)
            except ProcessLookupError:
                pass


@pytest.mark.skipif(os.name != "nt", reason="physical Windows named Job parent-death evidence")
def test_windows_parent_death_kills_named_job_writer_before_target_can_be_reused(environment, tmp_path):
    import ctypes
    from ctypes import wintypes
    _, _, profile_path, _ = environment
    profile = json.loads(profile_path.read_bytes())
    pid_path = tmp_path / "owned-writer.pid"
    marker = tmp_path / "forbidden-late-write"
    writer_code = ("import os,time,pathlib;"
                   f"pathlib.Path({str(pid_path)!r}).write_text(str(os.getpid()));"
                   f"time.sleep(3);pathlib.Path({str(marker)!r}).touch();time.sleep(30)")
    code = ("import sys,json;sys.path.insert(0,sys.argv[1]);from tools import python_packages as p;"
            "\nwith p._venv_mutex(json.loads(sys.argv[2])):"
            "\n p._run([sys.executable,'-I','-S','-B','-c',sys.argv[3]])")
    parent = subprocess.Popen([sys.executable, "-I", "-S", "-B", "-c", code,
                               str(Path(__file__).resolve().parents[1]), json.dumps(profile), writer_code],
                              creationflags=subprocess.CREATE_NO_WINDOW,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    handle = None
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    api.GetExitCodeProcess.restype = wintypes.BOOL
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    try:
        deadline = time.monotonic() + 20
        while not pid_path.is_file():
            assert parent.poll() is None
            assert time.monotonic() < deadline
            time.sleep(.01)
        handle = api.OpenProcess(0x1000, False, int(pid_path.read_text()))
        assert handle
        parent.kill()
        parent.wait(timeout=10)
        # Original context rejects any active named job even if the parent file
        # lock was already closed. When acquisition succeeds, writer is dead.
        deadline = time.monotonic() + 10
        while True:
            try:
                with packages._venv_mutex(profile):
                    status = wintypes.DWORD()
                    assert api.GetExitCodeProcess(handle, ctypes.byref(status))
                    assert status.value != 259
                break
            except packages.PackageError:
                assert time.monotonic() < deadline
                time.sleep(.01)
        time.sleep(3.1)
        assert not marker.exists()
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=10)
        if handle:
            api.CloseHandle(handle)


@pytest.mark.skipif(os.name != "nt", reason="physical Windows atomic Job-list creation evidence")
def test_windows_controller_death_after_birth_before_resume_leaves_no_launcher_or_writer(environment, tmp_path):
    import ctypes
    from ctypes import wintypes
    _, _, profile_path, _ = environment
    profile = json.loads(profile_path.read_bytes())
    born = tmp_path / "suspended-launcher.json"
    marker = tmp_path / "must-never-start"
    writer_code = f"import pathlib;pathlib.Path({str(marker)!r}).touch()"
    code = (
        "import sys,json,time;sys.path.insert(0,sys.argv[1]);from pathlib import Path;"
        "from tools import python_packages as p;real=p._WindowsJob.bind;"
        "\ndef bind(job,pid):"
        "\n real(job,pid)"
        "\n Path(sys.argv[3]).write_text(json.dumps({'pid':pid,'active':job.active(),"
        "'primary_handle_owned':pid in job.primary_threads}))"
        "\n time.sleep(30)"
        "\np._WindowsJob.bind=bind;"
        "\nwith p._venv_mutex(json.loads(sys.argv[2])):"
        "\n p._run([sys.executable,'-I','-S','-B','-c',sys.argv[4]])"
    )
    parent = subprocess.Popen([sys.executable, "-I", "-S", "-B", "-c", code,
                               str(Path(__file__).resolve().parents[1]), json.dumps(profile), str(born), writer_code],
                              creationflags=subprocess.CREATE_NO_WINDOW,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    api.GetExitCodeProcess.restype = wintypes.BOOL
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = None
    try:
        deadline = time.monotonic() + 20
        while not born.is_file():
            assert parent.poll() is None
            assert time.monotonic() < deadline
            time.sleep(.01)
        state = json.loads(born.read_bytes())
        assert state["active"] == 1 and state["primary_handle_owned"] is True
        assert not marker.exists()
        handle = api.OpenProcess(0x1000, False, state["pid"])
        assert handle
        parent.kill()
        parent.wait(timeout=10)
        deadline = time.monotonic() + 10
        while True:
            status = wintypes.DWORD()
            assert api.GetExitCodeProcess(handle, ctypes.byref(status))
            if status.value != 259:
                break
            assert time.monotonic() < deadline
            time.sleep(.01)
        with packages._venv_mutex(profile):
            assert not marker.exists()
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=10)
        if handle:
            assert api.CloseHandle(handle)
