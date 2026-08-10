"""
Bridge: template + ROI config + student page images  -->  "Results" format
JSON that backend/pipeline.py's load_input()/convert_results_to_samples()
consumes directly (see ../structure/structure_input.txt and
../CLAUDE.md#input-format for the target shape).

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
  "template_image": "path/to/template.jpg",
  "crop_dir": "crops",                          // optional, default "crops"
  "students": [
    {"hs_key": "HS_1", "image": "path/to/hs1.jpg"},
    {"hs_key": "HS_2", "image": "path/to/hs2.jpg"}
  ],
  "rois": [
    {"cau_key": "Cau_01",    "x": 100, "y": 200, "w": 300, "h": 80,  "task_type": "short_text"},
    {"cau_key": "Cau_08_1",  "x": 120, "y": 400, "w": 250, "h": 60,  "task_type": "short_text"},
    {"cau_key": "Cau_15b_1", "x": 100, "y": 900, "w": 500, "h": 200, "task_type": "table", "n_rows": 3, "n_cols": 2},
    {"cau_key": "Cau_13c",   "x": 100, "y": 1200,"w": 400, "h": 300, "task_type": "diagram"}
  ]
}

"cau_key" follows pipeline.py's Cau_XX / Cau_XX_N / Cau_XXa / Cau_XXa_N
convention (see convert_results_to_samples()'s regex `Cau_(\\d+)([a-z]?)(?:_(\\d+))?`).
"task_type" is one of module3's "short_text" | "long_text" | "code" | "table",
plus "diagram" (handled here, not sent to module3 — just saved as a crop and
marked as a visual answer, matching convert_results_to_samples()'s
`cau_type == "diagram"` handling).

Known limitation: ROI coordinates and cau_key/task_type mapping are supplied
manually in roi_config.json — module1's automatic ROI detection only gives
generic geometry + a rough "type" guess (e.g. "fill_in_blank"), it has no
notion of which barem question/part a region belongs to.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

from app.module2 import align_images


def _read_image(path: str) -> np.ndarray:
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Không đọc được ảnh: {path}")
    return img


def _crop(img: np.ndarray, roi: Dict[str, Any]) -> np.ndarray:
    x, y, w, h = roi["x"], roi["y"], roi["w"], roi["h"]
    return img[y : y + h, x : x + w]


def suggest_rois(template_path: str) -> None:
    from app.module1 import process_image

    img = _read_image(template_path)
    result = process_image(img, Path(template_path).name)
    print(json.dumps(result, ensure_ascii=False, indent=2))


async def _ocr_roi(roi: Dict[str, Any], crop: np.ndarray) -> Dict[str, Any]:
    from app.module3 import run_ocr_single

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
        cv2.imwrite(str(crop_path), crop)
        return {
            "status": "completed",
            "type": "diagram",
            "image_path": str(crop_path),
        }

    if save_crop:
        crop_path = crop_dir / f"{hs_key}_{roi['cau_key']}.png"
        cv2.imwrite(str(crop_path), crop)

    ocr_result = asyncio.run(_ocr_roi(roi, crop))
    status = "completed" if ocr_result.get("status") == "completed" else "failed_at_cropping"
    return {"status": status, "content": ocr_result.get("content", {})}


def build_results_json(config: Dict[str, Any], save_crops: bool = False) -> Dict[str, Any]:
    template_img = _read_image(config["template_image"])
    crop_dir = Path(config.get("crop_dir", "crops"))
    crop_dir.mkdir(parents=True, exist_ok=True)

    rois: List[Dict[str, Any]] = config["rois"]

    output: Dict[str, Any] = {"ma_de": config.get("ma_de", "1")}

    for student in config["students"]:
        hs_key = student["hs_key"]
        student_img = _read_image(student["image"])

        align = align_images(template_img, student_img)
        aligned_img = align["image"]
        alignment_failed = align["error"] is not None

        entries: Dict[str, Any] = {}
        for roi in rois:
            if alignment_failed:
                entries[roi["cau_key"]] = {"status": "failed_at_cropping", "content": {"lines": []}}
                continue
            entries[roi["cau_key"]] = _cau_entry_for_roi(
                roi, aligned_img, crop_dir, hs_key, save_crops
            )

        output[hs_key] = entries

    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", help="roi_config.json path")
    parser.add_argument("--output", help="Output Results-format JSON path")
    parser.add_argument("--save-crops", action="store_true", help="Also save non-diagram crops to crop_dir (debugging)")
    parser.add_argument("--suggest-rois", metavar="TEMPLATE_IMAGE", help="Run Module 1 ROI detection on a template image and print raw detections")
    args = parser.parse_args()

    if args.suggest_rois:
        suggest_rois(args.suggest_rois)
        return

    if not args.config or not args.output:
        parser.error("--config and --output are required unless --suggest-rois is used")

    with open(args.config, "r", encoding="utf-8") as f:
        config = json.load(f)

    result = build_results_json(config, save_crops=args.save_crops)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Wrote {args.output} ({sum(1 for k in result if k.startswith('HS_'))} students)")


if __name__ == "__main__":
    main()
