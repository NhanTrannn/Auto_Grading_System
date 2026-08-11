# Backend (FastAPI + grading pipeline)

This folder holds the FastAPI web API (`app/`), the original single-file
grading pipeline (`pipeline.py`, plus its data/tooling — `structure/`,
`scripts/`, `tool/`, `docs/`, and test/sample data under `testing/`), and the
OCR code (`ocr/`) side by side. `pipeline.py` and `ocr/` sit as direct siblings
of `app/`, not nested inside it, so their own CLIs keep working unchanged.

**One service serves all of it** — `uvicorn app.main:app --port 8000`. The API
reimplements no logic from either: `app/services/grading_engine/wrapper.py` and
`app/services/ocr_engine.py` put those folders on `sys.path` and import them
in-process. The OCR modules used to be a second FastAPI service on port 8081
(`backend/ocr/app/`); that package is now `backend/ocr/ocr_modules/` and its
three endpoints are a router at `/api/v1/ocr/*`.

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
plus **either** a `barem_id` from the library (what the UI sends — the stored
rubric is written out to `barem.json`, so the worker cannot tell the
difference) **or** an uploaded `barem_file`. Neither present is a 400, an
unknown id a 404. The id path exists because the rubric a teacher already
saved from the builder is the one they want to grade with; asking for the file
again each run mostly produced runs against a stale copy on disk.

It writes them to `var/jobs/{job_id}/`, inserts a
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

## Pipeline jobs (student page images → OCR → grading)

The web equivalent of running `backend/ocr/main.py` by hand, in **two steps**
because a teacher's archive holds a whole semester and the server must not
guess which cohort to grade:

1. `POST /api/v1/pipeline/uploads` — multipart `template_zip` + `students_zip`.
   Unpacks both under `var/pipeline_uploads/{upload_id}/` and answers with an
   inventory: the exam's page images in order, plus every exam code found and
   its students. `GET .../uploads/{id}/template/{page}` then serves one blank
   page image, which is what the browser's ROI editor draws its boxes on (and
   re-posts to `/api/v1/ocr/module1/roi`).
2. `POST /api/v1/pipeline/jobs` — JSON `{upload_id, ma_de, barem_id,
   roi_config}`. Runs exactly one exam code, against a barem from the library
   (`/api/v1/barems`, see below) and a region list assembled in the browser.
   It materialises a `roi_config.json` pointing at the unpacked files and
   spawns `app/pipeline_worker.py`.

Other endpoints: `GET .../jobs` (list), `GET .../jobs/{id}` (status **with
progress**), `GET .../jobs/{id}/result` (graded output, same shape as the
grading API's), `GET .../jobs/{id}/ocr-result` (intermediate Results-format
JSON, readable from the moment OCR finishes — for eyeballing what the OCR
actually read before trusting the grade), `GET .../jobs/{id}/log?offset=`
(incremental stdout tail for the live log panel), and
`GET .../jobs/{id}/crops/{hs_key}/{cau_key}` (the cropped answer region, shown
beside its OCR text on the review screen).

`app/services/zip_intake.py` does the unpacking. Three things it handles that
a plain `extractall` does not: entries written by Windows' built-in zipper
carry no UTF-8 flag and decode as cp437, mangling folder names like "Mã đề 1"
(recovered by re-encoding through cp437); `..`/absolute entries are dropped
(zip-slip); and macOS `__MACOSX/._*` resource forks are skipped. The student
folder is simply whichever directory an image sits in, and the exam-code
folder is recognised by name (`Made_1`, `ma_de_2`) or as the parent of a
`Bai_lam` directory — so one extra or missing wrapper directory in the
teacher's tree doesn't break intake.

Student folders are renamed to `HS_<n>` (`normalise_hs_key`) because
`convert_results_to_samples()` keys on that and `summarize_by_student()` sorts
with `int(hs.split("_")[-1])`; the number comes from the folder name when it
has one, else from its position. Folders sort naturally (`HS_2` before
`HS_10`). `POST` echoes the resulting `student_map` so the mapping is never
implicit, and `_validate_rois` rejects a malformed region list with a 400
naming the offending `rois[i]` rather than letting the run fail ten minutes
in.

**Multi-page exams**: each ROI carries a 1-based `page` that indexes both the
template pages and the student's pages positionally — page 2 of a submission
is aligned against page 2 of the exam. Pages no ROI refers to are never
loaded or aligned. `page` defaults to 1, so single-page configs still work.

## OCR modules on their own

`/api/v1/ocr/module1/roi`, `/module2/align`, `/module3/ocr`
(`app/api/routes/ocr.py`) expose the three OCR stages individually, for trying
one image at a time in the UI. Nothing in the pipeline flow goes through them —
that path calls `ocr_main.build_results_json()` directly. Module 1 and 2 are
pure OpenCV and free; **module 3 calls Qwen3-VL and costs money per request**,
and returns 503 when the `.env` credentials are missing.

`GET /api/v1/health` carries `llm_configured` alongside `status`, so the UI
learns both from one request — it is the same credential check that decides
whether module 3 and grading can run at all.

## Barem library

`/api/v1/barems` stores rubrics so a run can pick one instead of re-uploading
a file: `POST` (JSON body — what the in-browser barem builder's "Lưu vào thư
viện" button sends), `POST /upload` (an existing `.json`), plus list/get/
update/delete. The rubric is stored verbatim in a TEXT column; only the few
fields the picker lists (`ma_de`, `subject`, `total_score`, question count)
are mirrored into columns. `ma_de` and `teacher_barem` are required at write
time because `load_barem()` raises without them — better to reject at the
door than at grading time.

## Schema changes without Alembic

`app/db/migrate.py`'s `ensure_columns()` runs after `create_all` in the
lifespan. `create_all` only ever CREATEs, so adding a field to an existing
model leaves older databases without the column and every query fails — which
is exactly what happened when `ma_de`/`barem_name` were added to
`pipeline_jobs`. `ensure_columns` issues `ALTER TABLE … ADD COLUMN` for model
columns missing from an existing table, and only for columns that are nullable
or defaulted; it never drops, renames or retypes, so it cannot lose data.
Anything beyond new nullable columns still needs real Alembic migrations.

**`pipeline_worker.py` runs both halves in its own single process**: it imports
`ocr_main.build_results_json` (via `app/services/ocr_engine.py`) and
`pipeline.run_batch` (via `app/services/grading_engine/wrapper.py`), and writes
`stage`/`progress_done`/`progress_total`/`progress_message` straight to the job
row from the OCR connector's `on_progress` callback. It is still a *detached*
process spawned by the route — a run has to survive uvicorn restarting under
it, and `--reload` restarts on every source edit — but nothing is chained
behind it.

It used to be three processes (`app` → `backend/ocr/main.py` → `pipeline.py`)
coordinating through a progress file on disk, polled once a second. That was
forced by an import collision, not chosen: `backend/ocr/` held its own package
literally named `app` (`app.module1/2/3`), so `import app.module2` from here
resolved against `backend/app` — this very package. Renaming it to
`ocr_modules` removed the collision and with it the whole apparatus: no
snapshot file, no polling interval for progress to lag behind, no child exit
code to translate back into an error message. A failure is now just an
exception whose real traceback lands in the job's log.

State lives in a **separate `pipeline_jobs` table**
(`app/models/pipeline_job.py`), not extra columns on `grading_jobs`: this job
type needs `stage`/`progress_done`/`progress_total`/`progress_message`, and
`Base.metadata.create_all` never ALTERs an existing table — widening
`grading_jobs` would silently break every already-created database.

**A real pre-existing `pipeline.py` bug was found by running this flow
end-to-end**: `run_batch`'s summary line divided by `total_mx` unguarded, so
any batch whose total max score is 0 died with `ZeroDivisionError` *after*
grading had already finished, discarding all results. That happens for real
whenever a `cau_key` in `roi_config.json` matches no barem question (one
typo is enough — `barem_dict.get(q_num, [])` yields zero criteria, hence zero
max score). The per-sample print immediately above it was already guarded
with `if mx else 0`; only the total was missed. Fixed the same way.

Verified end-to-end over real HTTP with **zero LLM spend**, by using a
`roi_config` containing only `diagram` ROIs (never sent to module3) whose
`cau_key`s match no barem question (so grading calls no LLM either): both ZIPs
unpacked with Vietnamese paths intact, two exam codes were detected, a
three-page job reached `done`, all 6 crops (3 regions × 2 students, from
pages 1/2/3) were written and served, and `/result` + `/ocr-result` + `/log`
all answered correctly. A deliberately mismatched page correctly reported
`failed_at_cropping` while still advancing the progress counter.

**A second real bug surfaced only once real folder names were involved**:
`cv2.imread` uses the ANSI file API on Windows and returns `None` for any path
containing Vietnamese characters — i.e. every real exam folder ("Mã đề 1 -
Bản clean chưa làm"). The whole OCR stage died on the first page with a
misleading "can't open/read file" even though the file existed and the API had
just served it over HTTP. Fixed in `ocr_main.py` by reading bytes through
`np.fromfile` and decoding with `cv2.imdecode` (`_read_image`), and writing
crops via `cv2.imencode` + `ndarray.tofile` (`_write_image`) — both use the
wide-char API and work on every platform.

## Docker

Build context is this `backend/` folder itself (`build: .` in both compose
files) — now that `pipeline.py` lives directly inside `backend/` as a
sibling of `app/`, there's no need to reach outside this folder for it (an
earlier version of this setup, when `backend/` was nested two levels under
a separate `Autograding2026/` folder with `pipeline.py` at the true repo
root, needed the build context pointed at the repo root instead — that
workaround is gone now that the layout is flat). `Dockerfile` copies
`requirements.txt`, `app/`, `pipeline.py` **and `ocr/`** — all three must be
siblings inside `/app`, since `grading_engine/wrapper.py` and
`ocr_engine.py` reach them by relative path. A local `.dockerignore` keeps the
daemon from having to read everything else in this folder (`output_*/`,
`docs/`, `images/`, JSON fixtures, etc.) as build context, and explicitly
excludes `ocr/debug_module3.py`, which fires a real paid OCR request at import
time.

Dev (`docker-compose.dev.yaml`) bind-mounts `./app`, `./pipeline.py` and
`./ocr` on top of the built image so edits are picked up by `--reload` without
rebuilding — plus `./autograding.db` and `./var`, so the container shares the
host's barem library, job history and crops instead of keeping its own. Without
those two the app looks empty when you switch from `uvicorn` on the host to
Docker (the library reads back `[]` even though uploads succeed), and a
rebuild silently discards whatever the previous container held. `autograding.db`
must already exist on the host: bind-mounting a missing file makes Docker create
a *directory* with that name, which SQLAlchemy then cannot open.

Prod (`docker-compose.prod.yaml`) mounts a named volume at `/app/var` and
points `DATABASE_URL` into it. Without that, both the SQLite database and
`var/` (uploaded archives, per-job working dirs, crops, graded output — all
still reachable by URL from the UI long after a run) live in the container's
own filesystem, so every rebuild silently starts from an empty job history.

**Verified with a real `docker build` + `docker run`** (2026-08-11, after the
single-service merge): container starts clean, all 18 routes present, module 1
runs inside it (same 9 regions as on the host), and a full pipeline job
(2 students × 3 pages, OCR + grading, crops served back over HTTP) completes
end-to-end.

That run caught a real bug — **`ocr/` was never copied into the image.** The
end-to-end pipeline had therefore never been able to work in Docker at all
(the worker's child process pointed at a path that did not exist in the
container); after the merge it got worse, since a route module imports the OCR
code at startup, so the container would have failed to boot rather than
failing later. Confirmed by simulating the old Dockerfile
(`docker run --tmpfs /app/ocr … python -c "import app.main"`), which raises
`ModuleNotFoundError: No module named 'ocr_main'`.

An earlier run, before this folder was flattened, caught a different one:
`wrapper.py`'s path resolution used to index `.parents[5]` directly, which
raises `IndexError` (not just "not found") on a shallower container filesystem
path. Now moot — `wrapper.py` needs one fixed relative offset in both dev and
the image.
