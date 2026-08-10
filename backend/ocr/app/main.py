import base64
import logging
from typing import List, Optional

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .module1 import process_image
from .module2 import align_images, encode_png
from .module3 import LLMConfigError, is_configured, run_ocr_single

logger = logging.getLogger("uvicorn.error")

app = FastAPI(
    title="mmlab-auto-grading backend",
    description="FastAPI service chạy opencv-python y hệt logic trong các notebook gốc.",
    version="0.1.0",
)

# Dev CORS: cho phép Vite dev server gọi thẳng (không cần proxy) nếu cần.
# Khi dùng Vite dev proxy (khuyên dùng), origin sẽ luôn same-origin nên CORS không quan trọng lắm,
# nhưng vẫn để mở cho tiện lúc mới setup.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "module3_llm_configured": is_configured()}


@app.post("/module1/roi")
async def module1_roi(files: List[UploadFile] = File(...)):
    """
    Nhận 1 hoặc nhiều ảnh (multipart/form-data, field 'files').
    Trả về danh sách PageResult, đúng thứ tự với files đã gửi lên,
    theo đúng shape mà frontend (src/lib/roi/module1.ts -> PageResult) đang dùng.
    """
    results = []
    for f in files:
        data = await f.read()
        arr = np.frombuffer(data, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)

        if img is None:
            results.append(
                {
                    "filename": f.filename,
                    "error": "Không thể đọc ảnh (file hỏng hoặc không đúng định dạng).",
                }
            )
            continue

        try:
            result = process_image(img, f.filename or "unknown")
            results.append(result)
        except Exception as exc:  # noqa: BLE001 - trả lỗi rõ ràng về cho frontend
            results.append({"filename": f.filename, "error": str(exc)})

    return results


def _read_upload_as_bgr(data: bytes):
    arr = np.frombuffer(data, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


@app.post("/module2/align")
async def module2_align(template: UploadFile = File(...), student: UploadFile = File(...)):
    """
    Căn chỉnh 1 ảnh bài làm học sinh (`student`) về đúng khung của 1 ảnh
    template (`template`) bằng ORB + RANSAC homography (opencv-python thật,
    y hệt notebook — xem backend/app/module2.py).

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
    Việc cắt ROI (crop) vẫn làm ở frontend (chỉ là slice mảng pixel theo toạ độ
    có sẵn, không phải thuật toán CV, nên không cần chạy qua backend).
    """
    tpl_bytes = await template.read()
    stu_bytes = await student.read()

    tpl_img = _read_upload_as_bgr(tpl_bytes)
    stu_img = _read_upload_as_bgr(stu_bytes)

    if tpl_img is None or stu_img is None:
        return {
            "ok": False,
            "error": {
                "error_type": "FEATURE_ERROR",
                "reason": "Không thể đọc ảnh (file hỏng hoặc không đúng định dạng).",
            },
            "matches": 0,
            "inliers": 0,
            "skew": 0.0,
            "width": 0,
            "height": 0,
            "image_base64": None,
        }

    try:
        result = align_images(tpl_img, stu_img)
    except Exception as exc:  # noqa: BLE001 - trả lỗi rõ ràng về cho frontend
        return {
            "ok": False,
            "error": {"error_type": "FEATURE_ERROR", "reason": str(exc)},
            "matches": 0,
            "inliers": 0,
            "skew": 0.0,
            "width": 0,
            "height": 0,
            "image_base64": None,
        }

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


@app.post("/module3/ocr")
async def module3_ocr(
    image: UploadFile = File(...),
    task_type: str = Form(...),
    n_rows: Optional[int] = Form(None),
    n_cols: Optional[int] = Form(None),
):
    """
    OCR chữ viết tay 2-pass (Pass 1 trích xuất + Pass 2 self-reflection) cho
    1 ảnh crop, gọi Qwen3-VL-32B qua API (prompt/logic port y hệt 3 notebook
    gốc: qwenver15update-shorttext / ocr-longtext / qwenver15update-table —
    xem backend/ocr/app/module3.py).

    `task_type`: "short_text" | "long_text" | "code" | "table".
    `n_rows`/`n_cols` bắt buộc khi `task_type="table"`.

    Cần `LLM_API_KEY`/`LLM_MODEL_API`/`LLM_MODEL_NAME` trong `.env` (cùng
    file `.env` mà `backend/pipeline.py` dùng) — không cần GPU/CUDA.

    Trả về:
    {
      "status": "completed" | "failed_all_samples",
      "confidence": 1.0 | 0.0,
      "pass1_content": <object|null>,
      "content": <object>,
      "structure_warning": <string|null>
    }
    """
    if task_type not in ("short_text", "long_text", "code", "table"):
        raise HTTPException(status_code=400, detail=f"task_type không hợp lệ: '{task_type}'")
    if task_type == "table" and (n_rows is None or n_cols is None):
        raise HTTPException(status_code=400, detail="task_type='table' yêu cầu n_rows và n_cols.")

    data = await image.read()
    try:
        result = await run_ocr_single(data, task_type, n_rows=n_rows, n_cols=n_cols)
    except LLMConfigError as exc:
        logger.exception("Module 3 OCR lỗi (LLM chưa cấu hình)")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - log đầy đủ ra console, trả lỗi rõ ràng về frontend
        logger.exception("Module 3 OCR lỗi khi gọi API (xem traceback đầy đủ ở trên)")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return result
