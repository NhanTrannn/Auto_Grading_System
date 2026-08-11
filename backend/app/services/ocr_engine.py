"""Bridge to the OCR code under backend/ocr/.

Mirrors services/grading_engine/wrapper.py: backend/ocr/ is a sibling of this
backend's app/ package rather than a subpackage of it, so its own CLI
(`python ocr_main.py`, `python main.py`) keeps working unchanged from inside
backend/ocr/. This module puts that directory on sys.path and imports it
in-process — no subprocess, no HTTP hop.

This import used to be impossible: backend/ocr/ held a package literally named
`app`, colliding with backend/app (this very package), so `import app.module2`
from here resolved to the wrong `app`. That package is now `ocr_modules`, which
is what makes the whole OCR layer directly importable and let the standalone
OCR service on port 8081 go away.
"""

import sys
from pathlib import Path

_OCR_DIR = Path(__file__).resolve().parents[2] / "ocr"
if str(_OCR_DIR) not in sys.path:
    sys.path.insert(0, str(_OCR_DIR))

import ocr_main  # noqa: E402
from ocr_modules.module1 import process_image  # noqa: E402
from ocr_modules.module2 import align_images, encode_png  # noqa: E402
from ocr_modules.module3 import (  # noqa: E402
    LLMConfigError,
    is_configured,
    run_ocr_single,
)

__all__ = [
    "LLMConfigError",
    "align_images",
    "encode_png",
    "is_configured",
    "ocr_main",
    "process_image",
    "run_ocr_single",
]
