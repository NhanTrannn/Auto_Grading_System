# Frontend ↔ backend integration guide

## Dev setup

Two processes, run side by side:

```bash
# terminal 1 — backend (grading + pipeline + barems + OCR modules)
cd backend && uvicorn app.main:app --reload --port 8000

# terminal 2 — frontend
cd frontend && npm run dev
```

`frontend/vite.config.ts` proxies `/api` from the Vite dev server (port 5173)
to `http://localhost:8000`, with no rewrite (the backend already mounts under
`/api/v1`), so `src/services/*.ts` can use relative paths without hardcoding a
host — this also means no CORS headers are needed in dev.

There used to be a second process and a second proxy prefix (`/ocr` →
port 8081) for a standalone OCR service; see "One backend" below.

In production, whatever serves the frontend must route `/api` the same way
(reverse proxy / same origin), or `API_BASE` in `services/api.ts` and
`OCR_BASE` in `services/ocrApi.ts` need to become full URLs.

## One backend

`backend/ocr/` arrived as its own FastAPI service whose modules lived in a
package named `app` — the same name as `backend/app`, so the grading API could
never import the OCR code, no matter the `sys.path` order. Everything that
needed to cross that line went the long way round: the pipeline worker spawned
`backend/ocr/main.py` as a child process and read progress from a JSON file on
disk, and the browser fetched a template page from one service only to POST it
straight to the other.

The package is now `backend/ocr/ocr_modules/`, which removed the collision and
the workarounds with it. The three OCR endpoints are a router
(`app/api/routes/ocr.py`) at `/api/v1/ocr/*`, `app/services/ocr_engine.py`
imports the modules directly the way `grading_engine/wrapper.py` imports
`pipeline.py`, and the worker runs OCR and grading in one process, writing
progress straight to the database.

## Contract

- All routes are mounted under `settings.api_v1_prefix` (`/api/v1`,
  `backend/app/core/config.py`) via `app/api/routes/__init__.py`.
- Every backend route module (`app/api/routes/*.py`) should have a matching
  Pydantic schema in `app/schemas/` — mirror that shape as a TypeScript type
  in `frontend/src/types/` (e.g. `schemas/grading.py` ↔ `types/grading.ts`)
  so a backend field rename is easy to trace to its frontend usage. The OCR
  routes return plain dicts rather than Pydantic models, so
  `frontend/src/types/ocr.ts` is hand-mirrored from the docstrings in
  `backend/app/api/routes/ocr.py` — keep them in sync manually.
- CORS origins for non-proxied access are set in `Settings.cors_origins`
  (`backend/app/core/config.py`).

## Current endpoints

### Grading API — port 8000

| Method | Path                                | Purpose                                   |
|--------|-------------------------------------|--------------------------------------------|
| GET    | `/api/v1/health`                    | liveness check                             |
| GET    | `/api/v1/grading/jobs`              | list recent jobs (newest first, max 50) — powers the sidebar history |
| POST   | `/api/v1/grading/jobs`              | multipart `input_file` + **either** `barem_id` (from the library — what the UI sends) **or** `barem_file`; starts a background grading job. Neither → 400, unknown id → 404 |
| GET    | `/api/v1/grading/jobs/{id}`         | poll job status (`result_path` here is a server-side path, not fetchable) |
| GET    | `/api/v1/grading/jobs/{id}/result`  | fetch `{grading_results, student_summary}` JSON once `status: done` (409 otherwise) |

Grading always calls a real LLM and can take a while — the frontend should
poll `GET /api/v1/grading/jobs/{id}` rather than expect a synchronous
response from job creation, then call the `/result` endpoint once
`status === "done"`. `frontend/src/modules/grading/useJobStatus.ts` is the
reference implementation of this poll-then-fetch flow.

### Barem library — port 8000

| Method | Path                        | Purpose                                                   |
|--------|-----------------------------|-----------------------------------------------------------|
| GET    | `/api/v1/barems`            | list saved rubrics (metadata only — no `content`)          |
| POST   | `/api/v1/barems`            | JSON `{name, content}` — what the builder's "Lưu vào thư viện" sends |
| POST   | `/api/v1/barems/upload`     | multipart `file` — an existing barem `.json`               |
| GET    | `/api/v1/barems/{id}`       | full rubric including `content`                            |
| PUT    | `/api/v1/barems/{id}`       | rename and/or replace `content`                            |
| DELETE | `/api/v1/barems/{id}`       | remove from the library                                    |

`ma_de` and `teacher_barem` are required on write (400 otherwise) because
`pipeline.load_barem()` raises without them.

### End-to-end pipeline — port 8000 (page images -> OCR -> grading)

Two steps: unpack and inspect the archives first, then run **one exam code**
from that upload. A teacher's archive holds a whole semester, so the cohort to
grade is an explicit choice, never a guess.

| Method | Path                                        | Purpose                                              |
|--------|---------------------------------------------|------------------------------------------------------|
| POST   | `/api/v1/pipeline/uploads`                  | multipart `template_zip` + `students_zip` → `{upload_id, template_pages, ma_de_list}` |
| GET    | `/api/v1/pipeline/uploads/{id}/template/{page}` | one blank exam page image (the ROI editor's canvas) |
| POST   | `/api/v1/pipeline/jobs`                     | JSON `{upload_id, ma_de, barem_id, roi_config}` → starts a run |
| GET    | `/api/v1/pipeline/jobs`                     | list recent pipeline runs (newest first, max 50)      |
| GET    | `/api/v1/pipeline/jobs/{id}`                | poll status **with progress**: `stage` (`ocr`/`grading`/`done`), `progress_done`/`progress_total`, `progress_message` |
| GET    | `/api/v1/pipeline/jobs/{id}/result`         | graded `{grading_results, student_summary}` once done (409 otherwise) — same shape as the grading API's |
| GET    | `/api/v1/pipeline/jobs/{id}/ocr-result`     | intermediate Results-format JSON, readable as soon as OCR finishes (409 before that) |
| GET    | `/api/v1/pipeline/jobs/{id}/log?offset=`    | incremental stdout tail → `{text, next_offset, size}`  |
| GET    | `/api/v1/pipeline/jobs/{id}/crops/{hs}/{cau}` | the cropped answer region, for the review screen     |

The students ZIP keeps the teacher's own tree
(`HKI2025_2026/Made_1/Bai_lam/HS_10/*.png`); intake finds the student folder
as whichever directory holds the images and the exam code by folder name. See
`backend/README.md` for the cp437/zip-slip/`__MACOSX` handling and the
`HS_<n>` renaming rule. `POST /jobs` echoes `student_map` so the UI never has
to guess, and rejects a malformed region list with a 400 naming the offending
`rois[i]`. `frontend/src/modules/pipeline/roiConfigUtils.ts` mirrors those
same rules client-side so problems surface before submitting.

**Module 1 in the browser**: the ROI editor fetches the template page from
`/uploads/{id}/template/{page}` and posts that blob to
`/api/v1/ocr/module1/roi`. Module 1 only returns geometry — it has no idea
which region is which barem question — so assigning `cau_key`/`task_type`
stays a human step, with the candidate keys derived from the selected barem
(`frontend/src/modules/pipeline/cauKeySuggestions.ts`).

`app/pipeline_worker.py` runs OCR and grading in its own single process
(spawned detached, so a run survives uvicorn reloading) and writes progress
straight to the `pipeline_jobs` table. `pipeline_jobs` is a separate table from
`grading_jobs`; `app/db/migrate.py` handles new nullable columns on tables that
already exist, since `create_all` never ALTERs.

### OCR modules — `/api/v1/ocr/*`

| Method | Path                       | Purpose                                                     |
|--------|----------------------------|-------------------------------------------------------------|
| POST   | `/api/v1/ocr/module1/roi`  | multipart `files` (1..n images) → per-page ROI geometry + stats |
| POST   | `/api/v1/ocr/module2/align`| multipart `template` + `student` → aligned PNG (base64) + ORB/RANSAC metrics |
| POST   | `/api/v1/ocr/module3/ocr`  | multipart `image` + `task_type` (+ `n_rows`/`n_cols` for tables) → 2-pass handwriting OCR |

Module 1 and 2 are pure OpenCV (fast, free). **Module 3 calls Qwen3-VL through
the real API and costs money per request** — the UI labels it accordingly.
`/module3/ocr` returns 503 when `LLM_API_KEY`/`LLM_MODEL_API`/`LLM_MODEL_NAME`
are missing from the repo-root `.env`; `frontend/src/services/ocrApi.ts`
surfaces FastAPI's `detail` string so that reason reaches the user verbatim.
Whether those credentials are present is reported by `llm_configured` on
`GET /api/v1/health`, so the sidebar needs one request rather than a separate
OCR health check.

These three routes are for running one image through one module by hand. The
end-to-end pipeline does **not** call them — `app/pipeline_worker.py` invokes
`ocr_main.build_results_json()` directly to assemble the `HS_N`-keyed "Results"
JSON that `pipeline.py` consumes.
