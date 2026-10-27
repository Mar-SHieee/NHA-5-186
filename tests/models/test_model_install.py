import hashlib
import zipfile

import pytest

from shield_core.models.install import InstallError, _verify_and_extract


def _bundle(path, override=None, bad_checksum=False):
    files = {
        "binary_model.json": b"binary",
        "cwe_model.json": b"cwe",
        "preprocessing.joblib": b"preprocessing",
        "config.json": b"{}",
    }
    if override:
        files.update(override)
    checksum_lines = []
    for name, value in files.items():
        digest = hashlib.sha256(value).hexdigest()
        if bad_checksum and name == "binary_model.json":
            digest = "0" * 64
        checksum_lines.append(f"{digest}  {name}\n")
    sums = "".join(checksum_lines)
    with zipfile.ZipFile(path, "w") as archive:
        for name, value in files.items():
            archive.writestr(name, value)
        archive.writestr("SHA256SUMS", sums)


def test_verifies_and_extracts_model_bundle(tmp_path):
    archive = tmp_path / "bundle.zip"
    staging = tmp_path / "staging"
    staging.mkdir()
    _bundle(archive)

    _verify_and_extract(archive, staging)

    assert (staging / "binary_model.json").read_bytes() == b"binary"
    assert (staging / "config.json").read_bytes() == b"{}"


def test_rejects_checksum_mismatch(tmp_path):
    archive = tmp_path / "bundle.zip"
    staging = tmp_path / "staging"
    staging.mkdir()
    _bundle(archive, bad_checksum=True)

    with pytest.raises(InstallError, match="Checksum mismatch"):
        _verify_and_extract(archive, staging)


def test_rejects_unsafe_archive_path(tmp_path):
    archive = tmp_path / "bundle.zip"
    staging = tmp_path / "staging"
    staging.mkdir()
    _bundle(archive, {"../escape": b"bad"})

    with pytest.raises(InstallError, match="unsafe path"):
        _verify_and_extract(archive, staging)
