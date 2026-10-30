"""Download and verify the V1 model bundle from a GitHub Release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from shield_core.models.registry import ARTIFACT_ENV, DEFAULT_ARTIFACT_DIR

DEFAULT_REPOSITORY = "nhahub/NHA-5-186"
ASSET_NAME = "shield-v1.zip"
REQUIRED_FILES = {"binary_model.json", "preprocessing.joblib", "config.json"}
MAX_BUNDLE_SIZE = 100 * 1024 * 1024


class InstallError(RuntimeError):
    """The release bundle could not be verified or installed."""


def _request(url: str, token: str | None, accept: str) -> urllib.request.Request:
    headers = {"Accept": accept, "User-Agent": "SHIELD-model-installer"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, headers=headers)


def _release_asset(repository: str, tag: str | None, token: str | None) -> dict:
    endpoint = f"https://api.github.com/repos/{repository}/releases/"
    endpoint += f"tags/{tag}" if tag else "latest"
    try:
        with urllib.request.urlopen(
            _request(endpoint, token, "application/vnd.github+json"), timeout=30
        ) as response:
            release = json.load(response)
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise InstallError(f"Could not read a GitHub release for {repository}: {exc}") from exc
    for asset in release.get("assets", []):
        if asset.get("name") == ASSET_NAME:
            if asset.get("size", MAX_BUNDLE_SIZE + 1) > MAX_BUNDLE_SIZE:
                raise InstallError(f"Release asset {ASSET_NAME} exceeds the 100 MiB limit")
            return asset
    raise InstallError(f"Release {release.get('tag_name', 'latest')!r} has no {ASSET_NAME} asset")


def _download(url: str, destination: Path, token: str | None) -> None:
    try:
        with (
            urllib.request.urlopen(
                _request(url, token, "application/octet-stream"), timeout=60
            ) as response,
            destination.open("wb") as output,
        ):
            shutil.copyfileobj(response, output)
    except (urllib.error.URLError, OSError) as exc:
        raise InstallError(f"Could not download model bundle: {exc}") from exc


def _verify_and_extract(archive: Path, staging: Path) -> None:
    try:
        with zipfile.ZipFile(archive) as bundle:
            members = bundle.namelist()
            if any(
                PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts
                for name in members
            ):
                raise InstallError("Model bundle contains an unsafe path")
            if "SHA256SUMS" not in members:
                raise InstallError("Model bundle is missing SHA256SUMS")
            expected: dict[str, str] = {}
            for line in bundle.read("SHA256SUMS").decode("ascii").splitlines():
                digest, _, filename = line.partition("  ")
                relative = PurePosixPath(filename)
                if (
                    len(digest) != 64
                    or not filename
                    or relative.is_absolute()
                    or ".." in relative.parts
                ):
                    raise InstallError("Model bundle has an invalid SHA256SUMS entry")
                expected[filename] = digest
            has_cwe_head = any(
                name in expected for name in ("cwe_model.json", "family_model.json")
            ) or any(PurePosixPath(name).name.startswith("leaf_") for name in expected)
            if not REQUIRED_FILES.issubset(expected) or not has_cwe_head:
                raise InstallError("Checksum list is missing required V1 files")
            if not set(expected).issubset(set(members)):
                raise InstallError("Model bundle is missing files listed in SHA256SUMS")
            for filename, digest in expected.items():
                content = bundle.read(filename)
                if hashlib.sha256(content).hexdigest() != digest:
                    raise InstallError(f"Checksum mismatch for {filename}")
                destination = staging.joinpath(*PurePosixPath(filename).parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
    except (zipfile.BadZipFile, UnicodeDecodeError, KeyError, OSError) as exc:
        if isinstance(exc, InstallError):
            raise
        raise InstallError(f"Invalid model bundle: {exc}") from exc


def install(repository: str = DEFAULT_REPOSITORY, tag: str | None = None) -> Path:
    """Fetch, verify, and install V1 into the registry's artifact folder."""
    artifact_root = Path(os.environ.get(ARTIFACT_ENV) or DEFAULT_ARTIFACT_DIR)
    destination = artifact_root / "v1"
    if destination.exists():
        raise InstallError(f"V1 already exists at {destination}; move it aside before reinstalling")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    asset = _release_asset(repository, tag, token)
    expected_archive_hash = None
    if asset.get("digest", "").startswith("sha256:"):
        expected_archive_hash = asset["digest"].split(":", 1)[1]

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="shield-v1-") as temp:
        temp_dir = Path(temp)
        archive = temp_dir / ASSET_NAME
        _download(asset["url"], archive, token)
        if archive.stat().st_size > MAX_BUNDLE_SIZE:
            raise InstallError("Downloaded model bundle exceeds the 100 MiB limit")
        if expected_archive_hash:
            actual = hashlib.sha256(archive.read_bytes()).hexdigest()
            if actual != expected_archive_hash:
                raise InstallError("GitHub release asset digest does not match the download")
        staging = temp_dir / "v1"
        staging.mkdir()
        _verify_and_extract(archive, staging)
        staging.replace(destination)
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPOSITORY, help="GitHub owner/repository")
    parser.add_argument("--tag", help="release tag; defaults to the latest release")
    args = parser.parse_args(argv)
    try:
        path = install(args.repo, args.tag)
    except InstallError as exc:
        parser.exit(2, f"Model install failed: {exc}\n")
    print(f"Installed SHIELD V1 at {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
