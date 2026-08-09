"""Bridge to the existing single-file grading pipeline.

pipeline.py lives at backend/pipeline.py — a sibling of this backend's own
app/ package (not inside it), so the CLI, smoke tests, and Streamlit app
documented in the root CLAUDE.md keep working unchanged from backend/. This
module puts that directory on sys.path and imports it in-process, so
FastAPI calls straight into run_batch / grade_sample_advised / load_barem
without any subprocess or HTTP hop. This same relative layout (pipeline.py
next to app/) is also what the Docker image reproduces, so no separate
dev/prod path handling is needed.
"""

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import pipeline as engine  # noqa: E402


def load_barem(barem_path: str) -> dict:
    return engine.load_barem(barem_path)


def run_batch(test_input_path: str, barem_path: str, output_path: str | None = None) -> dict:
    return engine.run_batch(test_input_path, barem_path, output_path)


def grade_sample(sample: dict, barem_dict: dict) -> dict:
    return engine.grade_sample_advised(sample, barem_dict)
