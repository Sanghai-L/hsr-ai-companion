import base64
import io
import json
import zipfile

import pytest

from companion.contracts import CompanionError, canonical
from companion.release.artifacts import digest, make_artifact, open_artifact, zip_files
from companion.release.signing import sign, test_key as new_test_key


@pytest.fixture
def identity():
    return new_test_key()


def artifact(identity, files=None):
    private, _ = identity
    return make_artifact(files or {"runtime/python.exe": b"synthetic exe", "runtime/app.py": b"pass\n"},
                         kind="program", version="0.1.3", private=private)


def test_round_trip_and_reproducible_business_inventory(identity):
    first = artifact(identity)
    assert first == artifact(identity)
    manifest, files, proof = open_artifact(first, [identity[1]], allow_test=True)
    assert proof["verified"] and len(files) == len(manifest["files"]) == 2
    assert "personal.sqlite3" not in files


def test_test_keys_are_never_production_trust(identity):
    for records in ([], [identity[1]], [new_test_key()[1]]):
        with pytest.raises(CompanionError):
            open_artifact(artifact(identity), records)


@pytest.mark.parametrize("mutation", ["payload", "signature", "version", "key"])
def test_tampering_and_wrong_signer_rejected(identity, mutation):
    value = json.loads(artifact(identity))
    if mutation == "payload":
        value["payload"] = base64.b64encode(b"replaced executable").decode()
    elif mutation == "signature":
        value["signature"]["value"] = base64.b64encode(b"x"*64).decode()
    elif mutation == "version":
        value["manifest"]["version"] = "9.0.0"
    else:
        value["signature"] = sign(value["manifest"], new_test_key()[0])
    with pytest.raises(CompanionError):
        open_artifact(canonical(value), [identity[1]], allow_test=True)


@pytest.mark.parametrize("path", ["../outside", "/absolute", "C:/private", "file:stream", "NUL.txt", "a./b", "a\\b", "a//b"])
def test_unsafe_paths_rejected_before_any_extraction(identity, path):
    with pytest.raises(CompanionError):
        artifact(identity, {path: b"bad"})


def test_windows_case_collisions_and_file_directory_collisions(identity):
    for files in ({"File": b"1", "file": b"2"}, {"a": b"1", "a/b": b"2"}):
        with pytest.raises(CompanionError):
            artifact(identity, files)


def test_signed_but_mismatched_inventory_is_rejected(identity):
    value = json.loads(artifact(identity))
    value["manifest"]["files"][0]["sha256"] = "0"*64
    value["signature"] = sign(value["manifest"], identity[0])
    with pytest.raises(CompanionError):
        open_artifact(canonical(value), [identity[1]], allow_test=True)


def test_signed_zip_member_traversal_and_symlinks_rejected(identity):
    for name, mode in [("../outside", 0o100644), ("link", 0o120777)]:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            item = zipfile.ZipInfo(name)
            item.external_attr = mode << 16
            archive.writestr(item, b"target")
        value = json.loads(artifact(identity))
        payload = buffer.getvalue()
        value["manifest"].update(payload_sha256=digest(payload), payload_size=len(payload))
        value["signature"] = sign(value["manifest"], identity[0])
        value["payload"] = base64.b64encode(payload).decode()
        with pytest.raises(CompanionError):
            open_artifact(canonical(value), [identity[1]], allow_test=True)


def test_duplicate_json_fields_rejected(identity):
    raw = artifact(identity)
    with pytest.raises(CompanionError):
        open_artifact(b'{"manifest":{},'+raw[1:], [identity[1]], allow_test=True)
