# API reference

FastAPI reports API version **2.0.0**. Interactive schema documentation is at `/docs` on a running instance. The extension's version is maintained separately.

## POST /api/score

Send `multipart/form-data`.

| Field | Required | Behavior |
| --- | --- | --- |
| `job_description` | Yes | Nonblank string, at most 15,000 characters |
| `pdf_file` | One resume source | PDF up to 2 MiB; filename must end in `.pdf`, PDF header must be present, and parsing must succeed |
| `resume_text` | One resume source | Nonblank string, at most 100,000 characters |
| `return_resume_text` | No | Boolean, default false; includes extracted resume text for profile saving |

Supply `pdf_file` or `resume_text`, not both. Extracted PDF text also has a 100,000-character limit. Image-only PDFs are rejected when no readable native text is found; OCR is not implemented.

```bash
curl -X POST http://localhost:8000/api/score \
  -F 'resume_text=Backend engineer experienced in Python and PostgreSQL.' \
  -F 'job_description=Backend engineer with Python and SQL experience'
```

Successful responses use `Cache-Control: no-store`. The following is an illustrative response shape, not measured scoring output:

```json
{
  "overall_score": 75.0,
  "scores": {
    "skills": 80.0,
    "experience": 65.0,
    "education": 60.0,
    "projects": 70.0,
    "semantic": 78.0,
    "resume_quality": 72.0
  },
  "matched_skills": ["Python"],
  "missing_skills": ["Docker"],
  "partial_skills": [],
  "top_positive_factors": ["Example positive factor"],
  "top_negative_factors": ["Example improvement factor"],
  "ranking_method": "linear_fallback",
  "feature_vector": {},
  "match_summary": "",
  "suggestions": []
}
```

`ranking_method` is `linear_fallback` or `xgboost`. `partial_skills` entries contain `jd_skill`, `matched_as`, and `confidence`. Coaching suggestions contain string `issue`, string `suggestion`, and `priority` (`high`, `medium`, or `low`). At most five valid suggestions are returned.

`match_summary` and `suggestions` are always present in the API payload, but may be empty if coaching is disabled. An attempted but failed coaching call can return a failure summary and an empty suggestions list while preserving the numerical scoring result. AI output is validated and client rendering escapes its text.

`extracted_resume_text` appears only if `return_resume_text=true`. The extension uses it to save a PDF-derived profile. No `parsed_resume` object is returned.

### Error responses

Errors normally contain `{"detail": "message"}`. FastAPI validation errors may contain a structured `detail` list instead.

| Status | Examples |
| --- | --- |
| 400 | Blank inputs, both resume sources, unsupported extension, invalid/unreadable PDF, no extracted text |
| 413 | PDF, resume text, or job description exceeds its limit |
| 422 | Missing required form field or an invalid form type |
| 500 | Internal analysis failure; response omits internal exception details |

The 2 MiB file check applies while the handler copies the already parsed upload into its own temporary file. It is not a total HTTP-body limit enforced before multipart parsing. Configure proxy/server request limits and rate controls for a public deployment.

## GET /api/health

Successful native library loading returns 200:

```json
{"status": "ok", "engine_version": "<native version>", "api_version": "2.0.0"}
```

A native library failure returns 503:

```json
{"status": "unavailable", "api_version": "2.0.0"}
```

This checks native library availability. It does not verify successful inference, embedding readiness, model accuracy, or Groq availability.

## Serving and operational behavior

API routes are registered before public frontend routes. The website loads from `frontend/dist` when it exists, otherwise from an allowlist of public files in `frontend/`. Files outside the selected root, hidden paths, raw source/configuration files, and unknown routes return 404. Built assets use FastAPI's static file handler.

PDFs use generated temporary filenames and are removed when processing finishes. CORS currently allows all origins without credentials. The API is unauthenticated and does not have rate limiting or a work queue. Synchronous inference inside the async handler can block that worker's event loop; HTTP client concurrency is not evidence of concurrent native execution.

Optional Groq coaching is enabled by the deployment's `GROQ_API_KEY`, not a per-request parameter. Each Groq request has a 15-second timeout; the wrapper permits up to two attempts for eligible API errors. Up to 2,500 resume characters, 1,500 JD characters, and ten matched and ten missing skill names are included in its prompt. `MOCK_LLM=1` substitutes deterministic coaching for local checks; do not enable it for normal production output.
