"""The three OCR modules exposed individually, for running them by hand.

These used to be a separate FastAPI app on port 8081 (backend/ocr/app/main.py)
because backend/ocr/ could not be imported from this process at all — see
app/services/ocr_engine.py for why that is no longer true. The routes and their
payloads are unchanged; only the mount point moved, from `/{module}` on 8081 to
`/api/v1/ocr/{module}` here.

Nothing in the end-to-end pipeline (app/api/routes/pipeline.py -> ocr_worker)
goes through these — that path calls ocr_main.build_results_json() directly.
These exist so a teacher can try one image against one module in the UI.
"""

import base64
import logging
from typing import List, Optional

import cv2
import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.services.ocr_engine import (
    LLMConfigError,
    align_images,
    encode_png,
    process_image,
    run_ocr_single,
)

logger = logging.getLogger("uvicorn.error")

router = APIRouter()


def _read_upload_as_bgr(data: bytes):
    arr = np.frombuffer(data, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


@router.post("/module1/roi")
async def module1_roi(files: List[UploadFile] = File(...)):
    """
    Nhận 1 hoặc nhiều ảnh (multipart/form-data, field 'files').
    Trả về danh sách PageResult, đúng thứ tự với files đã gửi lên,
    theo đúng shape mà frontend (src/types/ocr.ts -> RoiPageResult) đang dùng.
    """
    results = []
    for f in files:
        data = await f.read()
        img = _read_upload_as_bgr(data)

        if img is None:
            results.append(
                {
                    "filename": f.filename,
                    "error": "Không thể đọc ảnh (file hỏng hoặc không đúng định dạng).",
                }
            )
            continue

        try:
            results.append(process_image(img, f.filename or "unknown"))
        except Exception as exc:  # noqa: BLE001 - trả lỗi rõ ràng về cho frontend
            results.append({"filename": f.filename, "error": str(exc)})

    return results


@router.post("/module2/align")
async def module2_align(template: UploadFile = File(...), student: UploadFile = File(...)):
    """
    Căn chỉnh 1 ảnh bài làm học sinh (`student`) về đúng khung của 1 ảnh
    template (`template`) bằng ORB + RANSAC homography (opencv-python thật,
    y hệt notebook — xem backend/ocr/ocr_modules/module2.py).

    Trả về:
    {
        "ok": true,
        "error": {"error_type","reason"} | null,
        "matches": int,
        "inliers": int,
        "skew": float,
        "width": int,
        "height": int,
        "image_base64": "<PNG base64 của ảnh đã align, kích thước = template>"
    }
    """
    tpl_img = _read_upload_as_bgr(await template.read())
    stu_img = _read_upload_as_bgr(await student.read())

    def _failure(reason: str) -> dict:
        return {
            "ok": False,
            "error": {"error_type": "FEATURE_ERROR", "reason": reason},
            "matches": 0,
            "inliers": 0,
            "skew": 0.0,
            "width": 0,
            "height": 0,
            "image_base64": None,
        }

    if tpl_img is None or stu_img is None:
        return _failure("Không thể đọc ảnh (file hỏng hoặc không đúng định dạng).")

    try:
        result = align_images(tpl_img, stu_img)
    except Exception as exc:  # noqa: BLE001 - trả lỗi rõ ràng về cho frontend
        return _failure(str(exc))

    png_bytes = encode_png(result["image"])
    h, w = result["image"].shape[:2]

    return {
        "ok": True,
        "error": result["error"],
        "matches": result["matches"],
        "inliers": result["inliers"],
        "skew": result["skew"],
        "width": w,
        "height": h,
        "image_base64": base64.b64encode(png_bytes).decode("ascii") if png_bytes else None,
    }


@router.post("/module3/ocr")
async def module3_ocr(
    image: UploadFile = File(...),
    task_type: str = Form(...),
    n_rows: Optional[int] = Form(None),
    n_cols: Optional[int] = Form(None),
):
    """
    OCR chữ viết tay 2-pass (Pass 1 trích xuất + Pass 2 self-reflection) cho
    1 ảnh crop, gọi Qwen3-VL-32B qua API — xem backend/ocr/ocr_modules/module3.py.

    `task_type`: "short_text" | "long_text" | "code" | "table".
    `n_rows`/`n_cols` bắt buộc khi `task_type="table"`.

    Cần `LLM_API_KEY`/`LLM_MODEL_API`/`LLM_MODEL_NAME` trong `.env` (cùng
    file `.env` mà `backend/pipeline.py` dùng) — không cần GPU/CUDA.
    """
    if task_type not in ("short_text", "long_text", "code", "table"):
        raise HTTPException(status_code=400, detail=f"task_type không hợp lệ: '{task_type}'")
    if task_type == "table" and (n_rows is None or n_cols is None):
        raise HTTPException(status_code=400, detail="task_type='table' yêu cầu n_rows và n_cols.")

    data = await image.read()
    try:
        return await run_ocr_single(data, task_type, n_rows=n_rows, n_cols=n_cols)
    except LLMConfigError as exc:
        logger.exception("Module 3 OCR lỗi (LLM chưa cấu hình)")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - log đầy đủ ra console, trả lỗi rõ ràng về frontend
        logger.exception("Module 3 OCR lỗi khi gọi API (xem traceback đầy đủ ở trên)")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
