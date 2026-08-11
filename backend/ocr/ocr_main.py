"""
Bridge: template + ROI config + student page images  -->  "Results" format
JSON that backend/pipeline.py's load_input()/convert_results_to_samples()
consumes directly (see ../structure/structure_input.txt and
../CLAUDE.md#input-format for the target shape).

Pure OCR connector — module1 (ROI suggestion) + module2 (alignment) +
module3 (handwriting OCR), nothing else. It does NOT call pipeline.py; see
main.py in this same directory for the OCR -> grading bridge.

This script imports module1/module2/module3 as plain Python functions
in-process (no HTTP, no need to run `uvicorn app.main:app`). Run it from
inside `backend/ocr/` so the `app` package is importable:

    cd backend/ocr
    python ocr_main.py --config roi_config.json --output results.json

    # helper to bootstrap a roi_config.json: run Module 1's ROI detector on
    # the template page and print the raw detections (x/y/w/h/type) as JSON —
    # copy the ones you want into roi_config.json's "rois" list and add the
    # missing "cau_key"/"task_type" (and "n_rows"/"n_cols" for tables) by hand.
    python ocr_main.py --suggest-rois template.jpg

roi_config.json shape:
{
  "ma_de": "1",
  "template_pages": ["de/page_1.png", "de/page_2.png"],   // multi-page exam
  "crop_dir": "crops",                          // optional, default "crops"
  "students": [
    {"hs_key": "HS_1", "pages": ["hs1/p1.png", "hs1/p2.png"]},
    {"hs_key": "HS_2", "pages": ["hs2/p1.png", "hs2/p2.png"]}
  ],
  "rois": [
    {"cau_key": "Cau_01",    "page": 1, "x": 100, "y": 200, "w": 300, "h": 80,  "task_type": "short_text"},
    {"cau_key": "Cau_08_1",  "page": 1, "x": 120, "y": 400, "w": 250, "h": 60,  "task_type": "short_text"},
    {"cau_key": "Cau_15b_1", "page": 2, "x": 100, "y": 900, "w": 500, "h": 200, "task_type": "table", "n_rows": 3, "n_cols": 2},
    {"cau_key": "Cau_13c",   "page": 2, "x": 100, "y": 1200,"w": 400, "h": 300, "task_type": "diagram"}
  ]
}

"page" is 1-based and indexes BOTH lists positionally: ROI page 2 is cropped
from the student's 2nd page after aligning it to the template's 2nd page. It
defaults to 1 when absent, so a single-page config stays valid. Pages that no
ROI refers to are never aligned (alignment is the expensive CV step).

Single-page back-compat: `"template_image": "..."` and `{"hs_key", "image"}`
are still accepted and treated as a one-page list.

"cau_key" follows pipeline.py's Cau_XX / Cau_XX_N / Cau_XXa / Cau_XXa_N
convention (see convert_results_to_samples()'s regex `Cau_(\\d+)([a-z]?)(?:_(\\d+))?`).
"task_type" is one of module3's "short_text" | "long_text" | "code" | "table",
plus "diagram" (handled here, not sent to module3 — just saved as a crop and
marked as a visual answer, matching convert_results_to_samples()'s
`cau_type == "diagram"` handling).

Known limitation: ROI coordinates and cau_key/task_type mapping are supplied
manually in roi_config.json — module1's automatic ROI detection only gives
generic geometry + a rough "type" guess (e.g. "fill_in_blank"), it has no
notion of which barem question/part a region belongs to. The web UI closes
that gap with a ROI-assignment editor rather than guessing (see
backend/app/api/routes/pipeline.py).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import cv2
import numpy as np

from ocr_modules.module2 import align_images

# on_progress(done, total, message) — called once per ROI processed. Optional:
# the CLI passes a writer that appends to --progress-file, the web worker
# (backend/app/pipeline_worker.py) polls that file to drive a progress bar.
# A whole-class run is len(students) * len(rois) LLM calls and can take a long
# time, so "no feedback until it finishes" is not a usable mode.
ProgressFn = Callable[[int, int, str], None]


def write_progress(path: Optional[str], stage: str, done: int, total: int, message: str) -> None:
    """Overwrite `path` with the current progress as JSON, atomically.

    Written to a sibling temp file then `os.replace`d, so a reader polling
    this file always sees either the previous complete snapshot or the new
    one — never a half-written file.
    """
    if not path:
        return
    target = Path(path)
    tmp = target.with_suffix(target.suffix + ".tmp")
    payload = {"stage": stage, "done": done, "total": total, "message": message}
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, target)


def progress_writer(path: Optional[str], stage: str) -> Optional[ProgressFn]:
    """Adapt `write_progress` into the `on_progress` callback shape."""
    if not path:
        return None
    return lambda done, total, message: write_progress(path, stage, done, total, message)


def _read_image(path: str) -> np.ndarray:
    """Read an image, tolerating non-ASCII paths.

    `cv2.imread` goes through the ANSI file API on Windows, so it silently
    returns None for any path containing Vietnamese characters — which is
    every real exam folder here ("Mã đề 1 - Bản clean chưa làm", "Bài làm",
    …). Reading the bytes with numpy (which uses the wide-char API) and
    decoding them in memory avoids the whole problem on every platform.
    """
    try:
        buffer = np.fromfile(path, dtype=np.uint8)
    except OSError as exc:
        raise ValueError(f"Không đọc được ảnh: {path} ({exc})") from exc
    img = cv2.imdecode(buffer, cv2.IMREAD_COLOR) if buffer.size else None
    if img is None:
        raise ValueError(f"Không đọc được ảnh: {path}")
    return img


def _write_image(path: Path, img: np.ndarray) -> None:
    """Write a PNG, tolerating non-ASCII paths (see `_read_image`)."""
    ok, buffer = cv2.imencode(".png", img)
    if not ok:
        raise ValueError(f"Không encode được ảnh: {path}")
    buffer.tofile(str(path))


def _crop(img: np.ndarray, roi: Dict[str, Any]) -> np.ndarray:
    x, y, w, h = roi["x"], roi["y"], roi["w"], roi["h"]
    return img[y : y + h, x : x + w]


def suggest_rois(template_path: str) -> None:
    from ocr_modules.module1 import process_image

    img = _read_image(template_path)
    result = process_image(img, Path(template_path).name)
    print(json.dumps(result, ensure_ascii=False, indent=2))


async def _ocr_roi(roi: Dict[str, Any], crop: np.ndarray) -> Dict[str, Any]:
    from ocr_modules.module3 import run_ocr_single

    ok, buf = cv2.imencode(".png", crop)
    if not ok:
        return {
            "status": "failed_all_samples",
            "content": {"error": "Không encode được ảnh crop."},
        }
    result = await run_ocr_single(
        buf.tobytes(),
        roi["task_type"],
        n_rows=roi.get("n_rows"),
        n_cols=roi.get("n_cols"),
    )
    return result


def _cau_entry_for_roi(
    roi: Dict[str, Any],
    aligned_img: np.ndarray,
    crop_dir: Path,
    hs_key: str,
    save_crop: bool,
) -> Dict[str, Any]:
    crop = _crop(aligned_img, roi)
    if crop.size == 0:
        return {"status": "failed_at_cropping", "content": {"lines": []}}

    if roi["task_type"] == "diagram":
        crop_path = crop_dir / f"{hs_key}_{roi['cau_key']}.png"
        _write_image(crop_path, crop)
        return {
            "status": "completed",
            "type": "diagram",
            "image_path": str(crop_path),
        }

    if save_crop:
        crop_path = crop_dir / f"{hs_key}_{roi['cau_key']}.png"
        _write_image(crop_path, crop)

    ocr_result = asyncio.run(_ocr_roi(roi, crop))
    status = "completed" if ocr_result.get("status") == "completed" else "failed_at_cropping"
    return {"status": status, "content": ocr_result.get("content", {})}


def _page_list(container: Dict[str, Any], plural_key: str, singular_key: str) -> List[str]:
    """Read a page-path list, accepting the old single-image key as one page."""
    pages = container.get(plural_key)
    if isinstance(pages, list) and pages:
        return [str(p) for p in pages]
    single = container.get(singular_key)
    if single:
        return [str(single)]
    raise ValueError(f"Thiếu '{plural_key}' (hoặc '{singular_key}') trong cấu hình.")


def _roi_page(roi: Dict[str, Any]) -> int:
    """1-based page index of an ROI; absent means a single-page exam."""
    try:
        return max(1, int(roi.get("page", 1)))
    except (TypeError, ValueError):
        return 1


def build_results_json(
    config: Dict[str, Any],
    save_crops: bool = False,
    on_progress: Optional[ProgressFn] = None,
) -> Dict[str, Any]:
    template_paths = _page_list(config, "template_pages", "template_image")
    crop_dir = Path(config.get("crop_dir", "crops"))
    crop_dir.mkdir(parents=True, exist_ok=True)

    rois: List[Dict[str, Any]] = config["rois"]
    students: List[Dict[str, Any]] = config["students"]

    # Only pages that actually carry an ROI are ever loaded/aligned — alignment
    # is the expensive CV step and a 9-page exam usually has answers on a few.
    pages_in_use = sorted({_roi_page(roi) for roi in rois})
    template_pages: Dict[int, np.ndarray] = {}
    for page in pages_in_use:
        if page > len(template_paths):
            raise ValueError(
                f"ROI trỏ tới trang {page} nhưng đề mẫu chỉ có {len(template_paths)} trang."
            )
        template_pages[page] = _read_image(template_paths[page - 1])

    total = len(students) * len(rois)
    done = 0

    def report(message: str) -> None:
        if on_progress is not None:
            on_progress(done, total, message)

    report("Bắt đầu OCR")

    output: Dict[str, Any] = {"ma_de": config.get("ma_de", "1")}

    for student in students:
        hs_key = student["hs_key"]
        student_paths = _page_list(student, "pages", "image")

        # Align page-by-page: a student whose page 3 is a bad photo should only
        # lose page 3's answers, not the whole submission.
        aligned_pages: Dict[int, Optional[np.ndarray]] = {}
        page_error: Dict[int, str] = {}
        for page in pages_in_use:
            if page > len(student_paths):
                aligned_pages[page] = None
                page_error[page] = f"thiếu trang {page}"
                continue
            try:
                align = align_images(template_pages[page], _read_image(student_paths[page - 1]))
            except Exception as exc:  # noqa: BLE001 - one bad page must not abort the class
                aligned_pages[page] = None
                page_error[page] = str(exc)
                continue
            if align["error"] is not None:
                aligned_pages[page] = None
                page_error[page] = align["error"].get("error_type", "ALIGN_ERROR")
            else:
                aligned_pages[page] = align["image"]

        entries: Dict[str, Any] = {}
        for roi in rois:
            page = _roi_page(roi)
            aligned_img = aligned_pages.get(page)
            if aligned_img is None:
                entries[roi["cau_key"]] = {"status": "failed_at_cropping", "content": {"lines": []}}
            else:
                entries[roi["cau_key"]] = _cau_entry_for_roi(
                    roi, aligned_img, crop_dir, hs_key, save_crops
                )
            done += 1
            # Reported even on the failed path so a class where one page fails
            # to align doesn't look like the run stalled.
            suffix = f" (trang {page}: {page_error[page]})" if page in page_error else ""
            report(f"{hs_key} · {roi['cau_key']}{suffix}")

        output[hs_key] = entries

    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", help="roi_config.json path")
    parser.add_argument("--output", help="Output Results-format JSON path")
    parser.add_argument("--save-crops", action="store_true", help="Also save non-diagram crops to crop_dir (debugging)")
    parser.add_argument("--suggest-rois", metavar="TEMPLATE_IMAGE", help="Run Module 1 ROI detection on a template image and print raw detections")
    parser.add_argument("--progress-file", help="Write live OCR progress as JSON to this path (for a UI/progress bar)")
    args = parser.parse_args()

    if args.suggest_rois:
        suggest_rois(args.suggest_rois)
        return

    if not args.config or not args.output:
        parser.error("--config and --output are required unless --suggest-rois is used")

    with open(args.config, "r", encoding="utf-8") as f:
        config = json.load(f)

    result = build_results_json(
        config,
        save_crops=args.save_crops,
        on_progress=progress_writer(args.progress_file, "ocr"),
    )

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Wrote {args.output} ({sum(1 for k in result if k.startswith('HS_'))} students)")


if __name__ == "__main__":
    main()
