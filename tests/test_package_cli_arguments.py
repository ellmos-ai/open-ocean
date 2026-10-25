"""Hash-pinned package-plan CLI spellings; private files and a stand-in engine."""

import contextlib
import hashlib
import json

import pytest

from tools import ocean_dev


@pytest.fixture
def plan_source(tmp_path):
    raw = b'{"fixture": "plan-transport-only"}'
    path = tmp_path / "plan source.json"
    path.write_bytes(raw)
    return path, raw, hashlib.sha256(raw).hexdigest()


def file_options(path, digest, file_equals, hash_equals):
    file_flag = "--python-package-plan-file"
    hash_flag = "--python-package-plan-file-sha256"
    return ([file_flag + "=" + str(path)] if file_equals else [file_flag, str(path)]) + (
        [hash_flag + "=" + digest] if hash_equals else [hash_flag, digest])


@pytest.mark.parametrize("file_equals,hash_equals", [(False, False), (True, False), (False, True), (True, True)])
def test_hashed_plan_file_accepts_argparse_option_spellings(plan_source, monkeypatch, file_equals, hash_equals):
    path, raw, digest = plan_source
    calls = []
    entered = []
    untouched = ["--expected-components-json", '["module:fixture"]', "--json"]
    monkeypatch.setattr(ocean_dev, "_main", lambda argv, **kwargs: calls.append(argv) or 19)

    @contextlib.contextmanager
    def transaction(plan):
        entered.append(plan)
        yield

    monkeypatch.setattr(ocean_dev, "package_transaction", transaction)
    assert ocean_dev.main(file_options(path, digest, file_equals, hash_equals) + untouched) == 19
    assert entered == [json.loads(raw)]
    assert calls == [untouched + ["--python-package-plan-json", raw.decode("utf-8")]]
    assert path.read_bytes() == raw


@pytest.mark.parametrize("file_equals,hash_equals", [(False, False), (True, False), (False, True), (True, True)])
def test_hashed_plan_file_rejects_wrong_digest_for_every_spelling(plan_source, monkeypatch, file_equals, hash_equals):
    path, raw, digest = plan_source
    assert digest != "0" * 64

    def forbidden(*args, **kwargs):
        raise AssertionError("bad hash reached transaction or engine")

    monkeypatch.setattr(ocean_dev, "package_transaction", forbidden)
    monkeypatch.setattr(ocean_dev, "_main", forbidden)
    assert ocean_dev.main(file_options(path, "0" * 64, file_equals, hash_equals), emitter=lambda *a, **k: None) == 3
    assert path.read_bytes() == raw


def test_hashed_plan_file_rejects_inline_and_file_mix(plan_source, monkeypatch):
    path, raw, digest = plan_source

    def forbidden(*args, **kwargs):
        raise AssertionError("mixed plan input reached transaction or engine")

    monkeypatch.setattr(ocean_dev, "package_transaction", forbidden)
    monkeypatch.setattr(ocean_dev, "_main", forbidden)
    args = file_options(path, digest, True, True) + ["--python-package-plan-json", raw.decode("utf-8")]
    assert ocean_dev.main(args, emitter=lambda *a, **k: None) == 3


@pytest.mark.parametrize("repeated", ["file", "hash"])
def test_hashed_plan_file_preserves_duplicate_input_rejection(plan_source, monkeypatch, repeated):
    path, raw, digest = plan_source
    monkeypatch.setattr(ocean_dev, "package_transaction", lambda plan: contextlib.nullcontext())
    args = file_options(path, digest, False, False)
    args += ["--python-package-plan-file", str(path)] if repeated == "file" else [
        "--python-package-plan-file-sha256", digest]
    assert ocean_dev.main(args, emitter=lambda *a, **k: None) == 3
    assert path.read_bytes() == raw


def test_hashed_plan_file_capture_is_reused_after_transaction_entry(plan_source, monkeypatch):
    path, raw, digest = plan_source
    captures = []
    actual_capture = ocean_dev.package_json_bytes
    calls = []

    def capture(source):
        captures.append(source)
        return actual_capture(source)

    @contextlib.contextmanager
    def transaction(plan):
        assert plan == json.loads(raw)
        path.write_bytes(b'{"changed": true}')
        yield

    monkeypatch.setattr(ocean_dev, "package_json_bytes", capture)
    monkeypatch.setattr(ocean_dev, "package_transaction", transaction)
    monkeypatch.setattr(ocean_dev, "_main", lambda argv, **kwargs: calls.append(argv) or 0)
    assert ocean_dev.main(file_options(path, digest, True, True)) == 0
    assert captures == [path]
    assert calls == [["--python-package-plan-json", raw.decode("utf-8")]]
