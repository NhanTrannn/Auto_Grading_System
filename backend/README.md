# Backend (FastAPI + grading pipeline)

This folder holds both the FastAPI web API (`app/`) and the original
single-file grading pipeline (`pipeline.py`, plus its data/tooling —
`structure/`, `scripts/`, `tool/`, `docs/`, and test/sample data under
`testing/` — `testing/input/`, `testing/output/`, etc.) side by side —
`pipeline.py` sits as a direct sibling of `app/`, not nested inside it. The API does not reimplement any grading logic —
`app/services/grading_engine/wrapper.py` puts this folder on `sys.path` and
calls straight into `pipeline.run_batch` / `grade_sample_advised` /
`load_barem` in-process.

See the root `CLAUDE.md` for the pipeline's own architecture/behavior notes
(barem schema, grading modes, LLM blending, etc.) — this README only covers
the FastAPI layer wrapped around it.

## Run locally

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The pipeline's own CLI/smoke tests still work unchanged from this same
folder — see `CLAUDE.md`'s Commands section (e.g. `python pipeline.py
--test`).

Uses the same `.env` (LLM credentials) as the root pipeline — see the root
`CLAUDE.md` for what it must contain. `app/core/config.py` reads it via
`pydantic-settings`.

## Run tests

```bash
pytest
```

## Grading jobs

`POST /api/v1/grading/jobs` accepts an `input_file` (raw OCR "Results" JSON)
and `barem_file`. It writes them to `var/jobs/{job_id}/`, inserts a
`pending` row, then spawns grading as a **separate OS subprocess**
(`app/worker.py`, run via `python -m app.worker <job_id> <input> <barem>
<output_dir>`) rather than a FastAPI `BackgroundTask` — grading always calls
a real LLM and can run long, and a subprocess keeps running even if this API
process is killed or restarted mid-run (a `BackgroundTask` would die with
it, since it shares the same process/event loop). On Windows the subprocess
is created with `CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS`; on POSIX with
`start_new_session=True` — both stop it from receiving the parent's
Ctrl+C/console-close signals. Its stdout/stderr are redirected to
`var/jobs/{job_id}/worker.log` for debugging. Poll
`GET /api/v1/grading/jobs/{job_id}` for status.

Job state is persisted in the `grading_jobs` table (`app/models/grading_job.py`,
SQLite by default via `Settings.database_url`) — both the API process and
`app/worker.py` open their own `SessionLocal()` and read/write the same row,
so status survives a restart of the API process itself. Tables are created
at startup via `Base.metadata.create_all` (`app/main.py`'s `lifespan`);
switch to real Alembic migrations (`requirements.txt` already includes it)
once the schema needs to evolve without a fresh `create_all`.

Verified manually: spawning the worker returns immediately (doesn't block
the parent), and the worker updates the job row to `failed`/`done` on its
own after the parent script/process has already moved on — confirming the
two are not coupled. Not yet covered by an automated test (would need
mocking `subprocess.Popen` or accepting a slow subprocess-based test).

`GET /api/v1/grading/jobs/{job_id}/result` returns the job's
`grading_results.json` + `student_summary.json` contents as JSON (404 if
the job doesn't exist, 409 if it hasn't reached `status: done` yet) — this
is what the frontend actually renders; `result_path` on the status endpoint
is a server-side filesystem path, not fetchable directly from a browser.

**Two real bugs found and fixed by running an actual job end-to-end through
the HTTP API** (not just unit-level/mocked checks):
1. `_spawn_worker` didn't set `PYTHONIOENCODING=utf-8` on the child
   process's environment. `pipeline.py` prints Vietnamese text throughout
   grading; on Windows the child inherits the parent's default console
   encoding (cp1252), which can't encode Vietnamese diacritics — the worker
   crashed with `UnicodeEncodeError` partway through a real grading run
   (same root cause as the `--test` CLI note in the root `CLAUDE.md`, just
   hit here via a spawned subprocess instead of an interactive terminal).
   Fixed by passing `env={**os.environ, "PYTHONIOENCODING": "utf-8"}` to
   `subprocess.Popen`.
2. `app/worker.py` passed its `output_dir` argument straight through to
   `pipeline.run_batch()` as-is. `run_batch`'s third argument is actually a
   **file path** (it does `open(output_path, "w")` directly) — the CLI
   (`pipeline.py`'s own `main()`) creates the directory itself and passes
   `str(output_dir / "grading_results.json")`, never the bare directory.
   Passing the bare directory instead created a plain file literally named
   `output` (no extension, no real directory) in the job folder, so every
   downstream read of `<output_dir>/grading_results.json` — including the
   `/result` endpoint above — failed with `FileNotFoundError` even though
   the job itself reported `status: done`. Fixed by having `worker.py`
   create the directory and build the file path itself before calling
   `run_batch`, mirroring exactly what the CLI does.

Both were only caught by actually running a job through `POST
/api/v1/grading/jobs` over real HTTP and polling it to completion — neither
surfaced in `pytest` (which mocks around the worker subprocess) or in
earlier manual `python -m app.worker` invocations run with
`PYTHONIOENCODING=utf-8` already set by hand in the shell.

## Docker

Build context is this `backend/` folder itself (`build: .` in both compose
files) — now that `pipeline.py` lives directly inside `backend/` as a
sibling of `app/`, there's no need to reach outside this folder for it (an
earlier version of this setup, when `backend/` was nested two levels under
a separate `Autograding2026/` folder with `pipeline.py` at the true repo
root, needed the build context pointed at the repo root instead — that
workaround is gone now that the layout is flat). `Dockerfile` copies just
`requirements.txt`, `app/`, and `pipeline.py` — a local `.dockerignore`
keeps the daemon from having to read everything else in this folder
(`output_*/`, `docs/`, `images/`, JSON fixtures, etc.) as build context.

Dev (`docker-compose.dev.yaml`) bind-mounts `./app` and `./pipeline.py` on
top of the built image so edits are picked up by `--reload` without
rebuilding.

**Verified with a real `docker build` + `docker run`** (before this folder
flatten, using the previous nested layout) — that run caught a real bug:
`wrapper.py`'s path resolution used to index `.parents[5]` directly, which
raises `IndexError` (not just "not found") on a shallower container
filesystem path — crashing the app the instant anything imported `wrapper`
inside the container. Fixed at the time by slicing instead of indexing;
now moot since `wrapper.py` only ever needs one fixed relative offset
(`parents[3]`, this backend's own root) in both dev and the image. Should
be re-verified with a fresh `docker build` after this folder flatten, since
the Dockerfile/compose files changed again.
