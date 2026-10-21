"""Project names for SHIELD datasets: one convention, `owner/repo`.

Every loader that has a repository URL should build `project` with
`project_from_repo_url`, so the same repository gets the same name in every dataset.

Rules
-----
* GitHub URLs        -> "owner/repo"            (".git" and trailing "/" removed)
* other hosts        -> "host/path"             e.g. "gitlab.com/group/repo", so a GitLab
                        repository can never collide with a GitHub one
* missing / invalid  -> <NA>

Letter case is kept as written in the URL. GitHub names are case-insensitive, so the split
code lower-cases them (`project_normalization.normalize_project_name`) before grouping.
"""

from __future__ import annotations

from urllib.parse import urlparse

import pandas as pd

_GITHUB_HOSTS = {"github.com", "www.github.com"}


def project_from_repo_url(value: object, *, github_only: bool = False) -> object:
    """Repository URL -> `owner/repo`. Returns <NA> when the URL cannot be used.

    github_only=True gives <NA> for non-GitHub hosts (use it before calling the GitHub API).
    """
    if value is None or pd.isna(value) or not str(value).strip():
        return pd.NA
    parsed = urlparse(str(value).strip())
    host = (parsed.hostname or "").lower()
    segments = [s for s in parsed.path.strip("/").split("/") if s]
    if not host or len(segments) < 2:
        return pd.NA
    segments[-1] = segments[-1].removesuffix(".git")
    if host in _GITHUB_HOSTS:
        return f"{segments[0]}/{segments[1]}"
    if github_only:
        return pd.NA
    return f"{host}/{'/'.join(segments)}"
