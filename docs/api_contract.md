# SHIELD API Contract

**Contract version:** 1.0 (`schema_version = "1.0"`)
**Status:** Draft for Gate G1 sign-off (W1-P4-02)
**Implemented in:** Week 5 (`api/`, FastAPI). Until then this document is the source of truth, and the frontend and VS Code extension build against a mock server.

This is a **document only**. Every request and response shape mirrors the dataclasses in `shield_core/interface.py` (Decision D19), so the backend is a thin wrapper: it validates input, calls `shield_core.interface`, and returns `.to_dict()`.

If this file and `interface.py` disagree, **`interface.py` wins**; fix this document in the same PR. Changes to either require team agreement and a row in the Decisions Log (Plan Section 2).

---

## 1. Conventions

| Topic | Rule |
|---|---|
| Base path | `/v1` |
| Format | JSON, UTF-8, `Content-Type: application/json` (except zip upload, see 3.2) |
| Field names | `snake_case` everywhere |
| Missing values | Sent as `null`, never omitted (so clients can rely on the key existing) |
| Confidence | Float in `[0, 1]`, calibrated |
| CWE | Normalized string, e.g. `"CWE-89"` |
| Language | A language `id` from the LanguageSpec registry (e.g. `"python"`, `"cpp"`). Never hard-coded; fetch the list from `GET /v1/languages` |
| Versioning | Every result carries `schema_version`. Results from detection also carry `model_version` |
| Auth | API key in header `X-API-Key` (Decision D11) |
| Timestamps | ISO 8601 UTC, e.g. `2026-10-04T12:30:00Z` |

`null` semantics worth remembering:

- `Result.cwe = null` means "not vulnerable".
- `Finding.file / function / start_line / end_line = null` means the location is unknown (e.g. pasted snippet, or V1 which cannot localize).
- `VerificationReport.tests_ok = null` means "no tests found, check not run". This is **not** a failure.

---

## 2. Data types

These map one-to-one to the dataclasses in `shield_core/interface.py`.

### 2.1 `TaintStep`

| Field | Type | Required | Notes |
|---|---|---|---|
| `file` | string | yes | |
| `line` | integer | yes | 1-based |
| `code` | string | no (default `""`) | source text of that line |

### 2.2 `TaintPath`

| Field | Type | Required | Notes |
|---|---|---|---|
| `source` | string | yes | where untrusted data enters, e.g. `request.args` |
| `sink` | string | yes | dangerous call, e.g. `cursor.execute` |
| `steps` | `TaintStep[]` | no (default `[]`) | ordered from source to sink |
| `sanitizer_present` | boolean | no (default `false`) | a sanitizer lies on the path |

### 2.3 `Finding`

| Field | Type | Required | Notes |
|---|---|---|---|
| `cwe` | string | yes | |
| `confidence` | number | yes | 0 to 1 |
| `language` | string | yes | |
| `file` | string \| null | no | |
| `function` | string \| null | no | |
| `start_line` | integer \| null | no | |
| `end_line` | integer \| null | no | |
| `taint_paths` | `TaintPath[]` | no (default `[]`) | evidence |

### 2.4 `Result`

| Field | Type | Notes |
|---|---|---|
| `vulnerable` | boolean | overall verdict |
| `cwe` | string \| null | top CWE; `null` when not vulnerable |
| `confidence` | number | 0 to 1 |
| `findings` | `Finding[]` | empty when clean |
| `taint_paths` | `TaintPath[]` | empty when no data-flow evidence |
| `model_version` | string | e.g. `"v4-fusion-1.0"`; `"v1-xgb-1.0"` reveals the fallback was used |
| `schema_version` | string | `"1.0"` |

### 2.5 `RepoResult`

| Field | Type | Notes |
|---|---|---|
| `files` | `{ [path: string]: Result }` | one result per scanned file |
| `cwe_distribution` | `{ [cwe: string]: integer }` | counts for dashboard charts |
| `top_risks` | `Finding[]` | highest-confidence findings first |
| `schema_version` | string | `"1.0"` |

### 2.6 `VerificationReport`

| Field | Type | Notes |
|---|---|---|
| `syntax_ok` | boolean | patched code re-parses (tree-sitter) |
| `tests_ok` | boolean \| null | `null` = no tests found / not run |
| `redetect_ok` | boolean | detector now says "not vulnerable" |
| `verdict` | `"PASS"` \| `"FAIL"` | `FAIL` if `syntax_ok` or `redetect_ok` is false, or `tests_ok` is `false`. `tests_ok = null` never causes a `FAIL` |
| `notes` | string | human-readable detail |

Verification is a **soft check, not a proof** (Plan Section 4.1). Clients should display which checks actually ran.

### 2.7 `FixResult`

| Field | Type | Notes |
|---|---|---|
| `finding` | `Finding` | the finding being fixed |
| `status` | `"ok"` \| `"no_fix_available"` \| `"rejected"` \| `"error"` | see table below |
| `method` | `"template"` \| `"codet5"` | method attempted |
| `candidate_fix` | string \| null | patched code |
| `diff` | string \| null | unified diff |
| `verification` | `VerificationReport` \| null | |
| `message` | string | human-readable reason |
| `schema_version` | string | `"1.0"` |

| `status` | `candidate_fix` | `verification` | Client should show |
|---|---|---|---|
| `ok` | present | `PASS` | diff with a green badge |
| `rejected` | present | `FAIL` | diff greyed out, "failed verification" (do not hide it) |
| `no_fix_available` | `null` | `null` | "No automatic fix for this CWE yet" |
| `error` | `null` | `null` | "Fix generation failed" plus `message` |

---

## 3. Endpoints

### 3.1 `POST /v1/scan/snippet`

Scan one piece of code synchronously.

**Request**

```json
{
  "code": "query = \"SELECT * FROM users WHERE id = \" + request.args[\"id\"]\ncursor.execute(query)",
  "language": "python"
}
```

| Field | Type | Required |
|---|---|---|
| `code` | string | yes (size-limited, see Section 5) |
| `language` | string | yes (must be enabled) |

**Response `200`:** a `Result`.

```json
{
  "vulnerable": true,
  "cwe": "CWE-89",
  "confidence": 0.91,
  "findings": [
    {
      "cwe": "CWE-89",
      "confidence": 0.91,
      "language": "python",
      "file": null,
      "function": null,
      "start_line": 1,
      "end_line": 2,
      "taint_paths": [
        {
          "source": "request.args",
          "sink": "cursor.execute",
          "sanitizer_present": false,
          "steps": [
            {"file": "snippet", "line": 1, "code": "query = \"SELECT ... \" + request.args[\"id\"]"},
            {"file": "snippet", "line": 2, "code": "cursor.execute(query)"}
          ]
        }
      ]
    }
  ],
  "taint_paths": [],
  "model_version": "v4-fusion-1.0",
  "schema_version": "1.0"
}
```

Backed by `interface.predict(code, language)`.

### 3.2 `POST /v1/scan/repo`

Start an asynchronous repository scan. Accepts **either** JSON with a URL **or** a zip upload.

**Request (JSON)**

```json
{ "repo_url": "https://github.com/owner/project" }
```

**Request (zip):** `multipart/form-data` with a `file` field containing the archive.

**Response `202`**

```json
{ "job_id": "9b1c6e0e-6f5a-4d5e-9d7a-2f1c0a8e7b11" }
```

Backed by `interface.scan_repo(path)` after ingestion (clone or unzip into a sandboxed workspace). Path traversal in uploaded archives must be rejected.

### 3.3 `GET /v1/jobs/{job_id}`

Poll a repo scan.

**Response `200`**

```json
{
  "job_id": "9b1c6e0e-6f5a-4d5e-9d7a-2f1c0a8e7b11",
  "status": "running",
  "progress": 0.42,
  "result": null,
  "error": null,
  "created_at": "2026-10-04T12:30:00Z",
  "finished_at": null
}
```

| Field | Type | Notes |
|---|---|---|
| `status` | `"queued"` \| `"running"` \| `"done"` \| `"failed"` | |
| `progress` | number | 0 to 1 |
| `result` | `RepoResult` \| null | present only when `status = "done"` |
| `error` | string \| null | present only when `status = "failed"` |

### 3.4 `POST /v1/fix`

Request a candidate fix for a finding.

**Request**

```json
{
  "finding": {
    "cwe": "CWE-89",
    "confidence": 0.91,
    "language": "python",
    "file": "app.py",
    "function": "get_user",
    "start_line": 4,
    "end_line": 8,
    "taint_paths": []
  },
  "code": "<optional: source text of the affected function>"
}
```

`code` is optional when the server already holds the scanned source (a stored scan). It is required for snippet findings.

**Response `200`:** a `FixResult`.

```json
{
  "finding": { "cwe": "CWE-89", "confidence": 0.91, "language": "python",
               "file": "app.py", "function": "get_user",
               "start_line": 4, "end_line": 8, "taint_paths": [] },
  "status": "ok",
  "method": "template",
  "candidate_fix": "cursor.execute(\"SELECT * FROM users WHERE id = ?\", (user_id,))",
  "diff": "- cursor.execute(query)\n+ cursor.execute(\"SELECT * FROM users WHERE id = ?\", (user_id,))",
  "verification": {
    "syntax_ok": true,
    "tests_ok": null,
    "redetect_ok": true,
    "verdict": "PASS",
    "notes": "No test suite found; verification is syntax + re-detection only."
  },
  "message": "",
  "schema_version": "1.0"
}
```

A fix that fails verification still returns `200` with `status = "rejected"`; it is a valid answer, not an HTTP error. Backed by `interface.suggest_fix(finding)`.

**The API never applies a fix to a codebase.** Merging a fix is a deliberate human step (Plan Section 8).

### 3.5 `GET /v1/scans` and `GET /v1/scans/{scan_id}`

Scan history (stored in PostgreSQL).

`GET /v1/scans?limit=20&offset=0`

```json
{
  "items": [
    {
      "scan_id": "a3f1...",
      "kind": "snippet",
      "language": "python",
      "vulnerable": true,
      "top_cwe": "CWE-89",
      "model_version": "v4-fusion-1.0",
      "created_at": "2026-10-04T12:30:00Z"
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

`kind` is `"snippet"` or `"repo"`.

`GET /v1/scans/{scan_id}` returns the summary fields above plus `result`, which is a `Result` (snippet) or `RepoResult` (repo).

### 3.6 `GET /v1/languages`

Enabled languages, read from the LanguageSpec registry. Clients (web dropdown, VS Code activation) must use this instead of hard-coding.

```json
{
  "languages": [
    { "id": "python", "extensions": [".py"], "cwe_list": ["CWE-89", "CWE-79", "CWE-78"] },
    { "id": "cpp", "extensions": [".c", ".cpp", ".h"], "cwe_list": ["CWE-119", "CWE-787"] }
  ]
}
```

### 3.7 `GET /v1/health` and `GET /v1/models`

`GET /v1/health`

```json
{ "status": "ok", "schema_version": "1.0" }
```

`GET /v1/models`

```json
{
  "default": "v4-fusion-1.0",
  "fallback": "v1-xgb-1.0",
  "available": [
    { "version": "v1-xgb-1.0", "loaded": true },
    { "version": "v3-gnn-1.0", "loaded": true },
    { "version": "v4-fusion-1.0", "loaded": true }
  ]
}
```

`health` and `models` do not require an API key (health only; `models` may require one, to be decided in Week 5).

---

## 4. Errors

All errors use one shape:

```json
{ "error": { "code": "unsupported_language", "message": "Unsupported language: cobol" } }
```

| HTTP | `code` | When |
|---|---|---|
| 400 | `bad_request` | malformed JSON, missing field |
| 401 | `unauthorized` | missing or invalid `X-API-Key` |
| 404 | `not_found` | unknown `job_id` or `scan_id` |
| 413 | `payload_too_large` | code or archive over the size limit |
| 422 | `unsupported_language` | language not enabled (mirrors `ValueError` from `interface.py`) |
| 429 | `rate_limited` | rate limit exceeded |
| 500 | `internal_error` | unexpected failure |
| 503 | `model_unavailable` | no model could be loaded (V1 fallback also failed) |

Model fallback is **not** an error: if V4 fails to load and V1 answers, the response is `200` with `model_version` showing the V1 version.

---

## 5. Limits and security (initial values, tune in Week 5)

- Maximum snippet size: 200 KB
- Maximum repo archive: 50 MB
- Rate limit: per API key (value set in W5-P4-02)
- CORS: allow the web app origin only
- Repo ingestion and any project-test execution run in the sandbox (Docker, no network, CPU/memory/time limits)
- Secrets (API keys, tokens) are never logged
- Uploaded archive paths are sanitized before extraction

---

## 6. Mapping to `shield_core.interface`

| Endpoint | Calls | Returns |
|---|---|---|
| `POST /v1/scan/snippet` | `predict(code, language)` | `Result` |
| `POST /v1/scan/repo` + `GET /v1/jobs/{id}` | `scan_repo(path)` | `RepoResult` |
| `POST /v1/fix` | `suggest_fix(finding)` | `FixResult` |
| `GET /v1/languages` | language registry | language list |

---

## 7. Compatibility rules

- **Adding an optional field** is allowed within `1.x`; clients must ignore unknown fields.
- **Removing, renaming, or changing the type of a field** requires a major bump (`2.0`), team agreement, and a Decisions Log row.
- `schema_version` in every payload lets clients detect a mismatch.
- Contract tests in CI (W4-P5-03) must fail if `interface.py` output drifts from this document.

---

## 8. Open items

- [ ] Final size and rate limit values (W5-P4-02)
- [ ] Whether `GET /v1/models` requires an API key
- [ ] `repo_url` support for private repositories (likely out of scope; GitHub OAuth is Stretch, D11)
- [ ] Pagination style for very large `RepoResult.files` (possibly a separate paged endpoint if repos are large)
