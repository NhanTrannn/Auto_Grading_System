# Frontend ↔ backend integration guide

## Dev setup

Three processes, run side by side:

```bash
# terminal 1 — grading API (backend/app, wraps pipeline.py)
cd backend && uvicorn app.main:app --reload --port 8000

# terminal 2 — OCR service (backend/ocr/app, standalone)
cd backend/ocr && uvicorn app.main:app --reload --port 8081

# terminal 3 — frontend
cd frontend && npm run dev
```

`frontend/vite.config.ts` proxies two prefixes from the Vite dev server
(port 5173) so `src/services/*.ts` can use relative paths without hardcoding a
host — this also means no CORS headers are needed in dev:

| Prefix | Target | Rewrite |
|--------|--------|---------|
| `/api` | `http://localhost:8000` | none (backend already mounts under `/api/v1`) |
| `/ocr` | `http://localhost:8081` | `/ocr` prefix **stripped** — the OCR service serves at the root (`/health`, `/module1/roi`, …) |

In production, whatever serves the frontend must route both prefixes the same
way (reverse proxy / same origin), or `API_BASE` in `services/api.ts` and
`OCR_BASE` in `services/ocrApi.ts` need to become full URLs.

## Contract

- Grading routes are mounted under `settings.api_v1_prefix` (`/api/v1`,
  `backend/app/core/config.py`) via `app/api/routes/__init__.py`. The OCR
  service (`backend/ocr/app/main.py`) is a **separate FastAPI app** with no
  version prefix and no shared code with `backend/app/`.
- Every backend route module (`app/api/routes/*.py`) should have a matching
  Pydantic schema in `app/schemas/` — mirror that shape as a TypeScript type
  in `frontend/src/types/` (e.g. `schemas/grading.py` ↔ `types/grading.ts`)
  so a backend field rename is easy to trace to its frontend usage. The OCR
  service returns plain dicts rather than Pydantic models, so
  `frontend/src/types/ocr.ts` is hand-mirrored from the docstrings in
  `backend/ocr/app/main.py` — keep them in sync manually.
- CORS origins for non-proxied access to the grading API are set in
  `Settings.cors_origins` (`backend/app/core/config.py`). The OCR service
  already allows all origins (`allow_origins=["*"]` in its own `main.py`).

## Current endpoints

### Grading API — port 8000

| Method | Path                                | Purpose                                   |
|--------|-------------------------------------|--------------------------------------------|
| GET    | `/api/v1/health`                    | liveness check                             |
| GET    | `/api/v1/grading/jobs`              | list recent jobs (newest first, max 50) — powers the sidebar history |
| POST   | `/api/v1/grading/jobs`              | upload input+barem, starts a background grading job |
| GET    | `/api/v1/grading/jobs/{id}`         | poll job status (`result_path` here is a server-side path, not fetchable) |
| GET    | `/api/v1/grading/jobs/{id}/result`  | fetch `{grading_results, student_summary}` JSON once `status: done` (409 otherwise) |

Grading always calls a real LLM and can take a while — the frontend should
poll `GET /api/v1/grading/jobs/{id}` rather than expect a synchronous
response from job creation, then call the `/result` endpoint once
`status === "done"`. `frontend/src/modules/grading/useJobStatus.ts` is the
reference implementation of this poll-then-fetch flow.

### OCR service — port 8081 (reached as `/ocr/*` through the dev proxy)

| Method | Path                | Purpose                                                     |
|--------|---------------------|-------------------------------------------------------------|
| GET    | `/ocr/health`       | liveness + `module3_llm_configured` (is `.env` set up?)      |
| POST   | `/ocr/module1/roi`  | multipart `files` (1..n images) → per-page ROI geometry + stats |
| POST   | `/ocr/module2/align`| multipart `template` + `student` → aligned PNG (base64) + ORB/RANSAC metrics |
| POST   | `/ocr/module3/ocr`  | multipart `image` + `task_type` (+ `n_rows`/`n_cols` for tables) → 2-pass handwriting OCR |

Module 1 and 2 are pure OpenCV (fast, free). **Module 3 calls Qwen3-VL through
the real API and costs money per request** — the UI labels it accordingly.
`/module3/ocr` returns 503 when `LLM_API_KEY`/`LLM_MODEL_API`/`LLM_MODEL_NAME`
are missing from the repo-root `.env`; `frontend/src/services/ocrApi.ts`
surfaces FastAPI's `detail` string so that reason reaches the user verbatim.

The OCR service is **not wired into the grading pipeline** — assembling its
output into the `HS_N`-keyed "Results" JSON that `pipeline.py` consumes is done
offline by `backend/ocr/bridge.py`, not by any HTTP call from the frontend.
