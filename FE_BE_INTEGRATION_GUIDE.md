# Frontend ↔ backend integration guide

## Dev setup

Run both servers side by side:

```bash
# terminal 1
cd backend && uvicorn app.main:app --reload

# terminal 2
cd frontend && npm run dev
```

`frontend/vite.config.ts` proxies any `/api/*` request from the Vite dev
server (port 5173) to the backend (port 8000), so `src/services/api.ts` can
call relative paths (`/api/v1/...`) without hardcoding a host — this also
means no CORS headers are needed in dev. In production, wherever the
frontend is served from must still route `/api/*` to the backend (reverse
proxy / same origin), or `api.ts`'s `API_BASE` needs to become a full URL.

## Contract

- Backend routes are mounted under `settings.api_v1_prefix` (`/api/v1`,
  `backend/app/core/config.py`) via `app/api/routes/__init__.py`.
- Every backend route module (`app/api/routes/*.py`) should have a matching
  Pydantic schema in `app/schemas/` — mirror that shape as a TypeScript type
  in `frontend/src/types/` (e.g. `schemas/grading.py` ↔ `types/grading.ts`)
  so a backend field rename is easy to trace to its frontend usage.
- CORS origins for non-proxied access (e.g. hitting the backend directly
  from a different port/host) are set in `Settings.cors_origins`
  (`backend/app/core/config.py`) — add the frontend's origin there if you
  stop using the Vite proxy.

## Current endpoints

| Method | Path                          | Purpose                                   |
|--------|-------------------------------|--------------------------------------------|
| GET    | `/api/v1/health`              | liveness check                             |
| POST   | `/api/v1/grading/jobs`        | upload input+barem, starts a background grading job |
| GET    | `/api/v1/grading/jobs/{id}`   | poll job status/result path                |

Grading always calls a real LLM and can take a while — the frontend should
poll `GET /api/v1/grading/jobs/{id}` rather than expect a synchronous
response from job creation.
