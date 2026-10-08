"""
Bridge: ROI layout + student page images  -->  "Results" format JSON that
backend/pipeline.py's load_input()/convert_results_to_samples() consumes
directly (see ../structure/structure_input.txt and ../CLAUDE.md#input-format
for the target shape).

Pure OCR connector — module1 (dò ROI ngay trên bài của từng học sinh, kèm
cảnh báo ảnh nghiêng mượn từ module2) + module3 (handwriting OCR), nothing
else. It does NOT call pipeline.py; see main.py in this same directory for
the OCR -> grading bridge.

KHÔNG còn bước căn ảnh về tờ mẫu. Trước đây toạ độ ROI được đo một lần trên
tờ đề sạch rồi mọi bài được warp về khung tờ đó (module2.align_images); ảnh
chụp chéo hay nghiêng làm warp thất bại và mất trắng cả trang — đo trên phiên
thật, HS_16 (chụp chéo, 41/750 điểm khớp) và HS_29 (nghiêng 5.97°, 22/750)
mỗi em mất 4 câu và bị báo là "không làm bài". Giờ khung được dò trực tiếp
trên bài của chính em đó rồi ghép với bố cục theo tỉ lệ trang, nên không còn
bước nào để hỏng; ô nào không tìm được khung thì mang status "needs_review"
để giáo viên xem, không bị chấm 0.

This script imports module1/module2/module3 as plain Python functions
in-process (no HTTP, no need to run `uvicorn app.main:app`). Run it from
inside `backend/ocr/` so the `app` package is importable:

    cd backend/ocr
    python ocr_main.py --config roi_config.json --output results.json

    # helper to bootstrap a roi_config.json: run Module 1's ROI detector on
    # ONE page of ONE student and print the detections with RELATIVE coords —
    # copy the ones you want into roi_config.json's "rois" list and add the
    # missing "cau_key"/"task_type" (and "n_rows"/"n_cols" for tables) by hand.
    python ocr_main.py --suggest-rois hs1/p1.jpg

roi_config.json shape:
{
  "ma_de": "1",                                 // mã đề mặc định cho mọi học sinh
  "crop_dir": "crops",                          // optional, default "crops"
  "students": [
    // "ma_de" riêng của từng em (tuỳ chọn) — thiếu thì lấy "ma_de" ở trên.
    // Kết quả ghi ma_de vào TỪNG học sinh, vì pipeline.py chọn barem theo đó.
    {"hs_key": "HS_1", "pages": ["hs1/p1.png", "hs1/p2.png"]},
    {"hs_key": "HS_2", "ma_de": "2", "pages": ["hs2/p1.png", "hs2/p2.png"]}
  ],
  // x/y/w/h là TỈ LỆ trang (0..1), KHÔNG phải pixel: mỗi bài chụp một cỡ nên
  // pixel không dùng chung được. Chúng chỉ mô tả bố cục tờ đề; khung thật
  // dùng để cắt là khung module1 dò được trên chính bài của từng học sinh.
  "rois": [
    {"cau_key": "MA_DE",     "page": 1, "x": 0.11, "y": 0.05, "w": 0.30, "h": 0.02, "task_type": "short_text"},
    {"cau_key": "Cau_01",    "page": 1, "x": 0.11, "y": 0.24, "w": 0.80, "h": 0.03, "task_type": "short_text"},
    {"cau_key": "Cau_08_1",  "page": 1, "x": 0.12, "y": 0.42, "w": 0.80, "h": 0.07, "task_type": "short_text"},
    {"cau_key": "Cau_15b_1", "page": 2, "x": 0.11, "y": 0.40, "w": 0.80, "h": 0.23, "task_type": "table", "n_rows": 3, "n_cols": 2},
    {"cau_key": "Cau_13c",   "page": 2, "x": 0.11, "y": 0.63, "w": 0.80, "h": 0.16, "task_type": "diagram"}
  ]
}

"page" is 1-based and indexes the student's own page list: ROI page 2 is
cropped from the student's 2nd page. It defaults to 1 when absent, so a
single-page config stays valid. Pages that no ROI refers to are never read.

Single-page back-compat: `{"hs_key", "image"}` is still accepted as a one-page
list. `"template_pages"`/`"template_image"` are REJECTED — a config still
carrying them was measured in pixels against a template and must be re-mapped.

One reserved cau_key: "MA_DE" marks the box where the exam code is printed.
It is OCR'd like any short_text region, but instead of becoming an answer its
text is parsed into that student's "ma_de", overriding the one configured
above — so a class can be graded without sorting the images into Made_N
folders. An unreadable or empty box falls back to the configured code rather
than guessing, because the wrong rubric marks every question wrong while
still looking like an ordinary result. The raw OCR text stays in the output
under "MA_DE" so a misread can be traced.

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
import re
import unicodedata
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import cv2
import numpy as np

from ocr_modules.module1 import detect_page_rois

# Vùng đã khai nhưng không tìm thấy khung tương ứng trên bài của em này. KHÁC
# hẳn "học sinh bỏ trống": máy không đọc được, nên phải đẩy sang giáo viên xem
# thay vì chấm 0. Gộp hai thứ này lại chính là lỗi đã khiến HS_16 và HS_29 mất
# trắng 4 câu mỗi em mà báo cáo vẫn ghi "Student left this part blank".
REGION_NOT_FOUND = "needs_review"

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


def suggest_rois(page_path: str) -> None:
    """In các khung dò được trên một trang, kèm toạ độ TỈ LỆ để dán vào config.

    Chạy trên một bài bất kỳ của lớp chứ không cần tờ mẫu sạch — bố cục là như
    nhau, và toạ độ tỉ lệ dùng lại được cho mọi bài dù ảnh chụp to nhỏ khác cỡ.
    """
    from ocr_modules.module1 import process_image, to_relative

    img = _read_image(page_path)
    height, width = img.shape[:2]
    result = process_image(img, Path(page_path).name)
    result["rois"] = [
        {**to_relative(r, width, height), "type": r.get("type", "table")}
        for r in result["rois"]
    ]
    print(json.dumps(result, ensure_ascii=False, indent=2))


async def _ocr_roi(roi: Dict[str, Any], crop: np.ndarray) -> Dict[str, Any]:
    from ocr_modules.module3 import run_ocr_single

    ok, buf = cv2.imencode(".png", crop)
    if not ok:
        return {
            "status": "failed_all_samples",
            "content": {"error": "Không encode được ảnh crop."},
        }
    # The exam code is printed by the exam author, not written by the student,
    # so it needs module3's "printed" prompt — every handwriting prompt is told
    # to skip printed text and returns an empty result for this box. Forced
    # here rather than left to the roi's declared task_type, because there is
    # exactly one right answer for this region and a wrong one fails silently
    # (empty OCR -> exam code falls back to the folder name).
    task_type = "printed" if roi["cau_key"] == MA_DE_KEY else roi["task_type"]
    result = await run_ocr_single(
        buf.tobytes(),
        task_type,
        n_rows=roi.get("n_rows"),
        n_cols=roi.get("n_cols"),
    )
    return result


def _cau_entry_for_roi(
    roi: Dict[str, Any],
    page_img: np.ndarray,
    crop_dir: Path,
    hs_key: str,
    save_crop: bool,
) -> Dict[str, Any]:
    crop = _crop(page_img, roi)
    if crop.size == 0:
        return {"status": "failed_at_cropping", "content": {"lines": []}}

    # Checked before the diagram branch: the exam code is always OCR'd as
    # printed text, whatever task_type the config happens to carry for it.
    if roi["task_type"] == "diagram" and roi["cau_key"] != MA_DE_KEY:
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


# Reserved `cau_key` for the region holding the exam code printed on the paper.
# Not a question: pipeline.py's `convert_results_to_samples` matches cau_keys
# against `Cau_(\d+)([a-z]?)(?:_(\d+))?$`, which this deliberately does not
# match, so grading skips it while the OCR text still lands in the Results JSON
# where a misread can be inspected.
MA_DE_KEY = "MA_DE"

# "MÃ ĐỀ: 1", "Ma de 1", "MADE:2" — the printed label sits inside the same box
# as the code, so it has to come off before the code can be read.
_MA_DE_LABEL_RE = re.compile(r"^\s*m[aă]\s*d[eê]\s*[:.\-]?\s*", re.IGNORECASE)


def _strip_accents(text: str) -> str:
    """Fold Vietnamese diacritics so a label can be matched case/accent-blind.

    `đ`/`Đ` (U+0111/U+0110) must be handled separately: unlike every other
    Vietnamese letter they are single codepoints with a stroke, not a base
    letter plus a combining mark, so NFD leaves them untouched and "MÃ ĐỀ"
    folds to "MA ĐE" — which no ASCII pattern for "ma de" can match.
    """
    folded = text.replace("đ", "d").replace("Đ", "D")
    return "".join(
        c for c in unicodedata.normalize("NFD", folded) if not unicodedata.combining(c)
    )


def _parse_ma_de(lines: List[str]) -> Optional[str]:
    """Pull the exam code out of what OCR read in the MA_DE region.

    Returns None when nothing usable was read, so the caller can fall back to
    the code configured for the student rather than inventing one — grading
    against the wrong rubric is far worse than grading against the folder's.
    """
    for raw in lines:
        text = _strip_accents(str(raw)).strip()
        if not text:
            continue
        without_label = _MA_DE_LABEL_RE.sub("", text)
        token = without_label.split()[0].strip(":.-") if without_label.split() else ""
        # A token carrying a digit is taken as-is, so alphanumeric codes like
        # "A2" survive. A purely alphabetic one means the label was worded
        # differently than expected ("Đề số 2" leaves "De"), so fall back to
        # the digits in the line rather than returning a fragment of the label.
        if token and any(ch.isdigit() for ch in token):
            return token
        digits = re.findall(r"\d+", text)
        if digits:
            return digits[-1]
        if token:
            return token
    return None


def build_results_json(
    config: Dict[str, Any],
    save_crops: bool = False,
    on_progress: Optional[ProgressFn] = None,
) -> Dict[str, Any]:
    if config.get("template_pages") or config.get("template_image"):
        raise ValueError(
            "roi_config còn khai 'template_pages'/'template_image' theo kiểu cũ. "
            "Pipeline không căn bài về tờ mẫu nữa — ROI được dò ngay trên bài của "
            "từng học sinh, và toạ độ trong 'rois' phải là TỈ LỆ trang (0..1). "
            "Hãy khai lại bố cục trong màn gán vùng."
        )

    crop_dir = Path(config.get("crop_dir", "crops"))
    crop_dir.mkdir(parents=True, exist_ok=True)

    rois: List[Dict[str, Any]] = config["rois"]
    students: List[Dict[str, Any]] = config["students"]

    for roi in rois:
        for axis in ("x", "y", "w", "h"):
            value = roi.get(axis)
            if not isinstance(value, (int, float)) or not 0.0 <= float(value) <= 1.0:
                raise ValueError(
                    f"ROI {roi.get('cau_key')!r} có {axis}={value!r}: toạ độ phải là "
                    "tỉ lệ trang trong khoảng 0..1, không phải pixel."
                )

    # Bố cục của từng trang, để `detect_page_rois` biết khung nào là câu nào.
    slots_by_page: Dict[int, List[Dict[str, Any]]] = {}
    for roi in rois:
        slots_by_page.setdefault(_roi_page(roi), []).append(roi)
    pages_in_use = sorted(slots_by_page)

    total = len(students) * len(rois)
    done = 0

    def report(message: str) -> None:
        if on_progress is not None:
            on_progress(done, total, message)

    report("Bắt đầu OCR")

    # `ma_de` đi theo TỪNG HỌC SINH, không phải theo file: một phiên chấm có
    # thể trộn nhiều mã đề, và pipeline.py chọn barem cho mỗi em dựa vào giá
    # trị này. Mỗi student trong roi_config khai `ma_de` riêng được; không
    # khai thì lấy `ma_de` chung của config.
    default_ma_de = str(config.get("ma_de", "1"))
    output: Dict[str, Any] = {}

    for student in students:
        hs_key = student["hs_key"]
        configured_ma_de = str(student.get("ma_de", default_ma_de))
        entries: Dict[str, Any] = {"ma_de": configured_ma_de}
        student_paths = _page_list(student, "pages", "image")

        # Dò từng trang riêng: một trang chụp hỏng chỉ mất các câu của trang
        # đó, không kéo theo cả bài. Không còn bước warp nào để hỏng — chỉ có
        # khung dò được hay không, và ô nào không có khung thì nói thẳng.
        page_images: Dict[int, Optional[np.ndarray]] = {}
        page_boxes: Dict[int, Dict[str, Any]] = {}
        page_error: Dict[int, str] = {}
        for page in pages_in_use:
            if page > len(student_paths):
                page_images[page] = None
                page_error[page] = f"thiếu trang {page}"
                continue
            try:
                img = _read_image(student_paths[page - 1])
                found = detect_page_rois(img, f"{hs_key}_p{page}", slots=slots_by_page[page])
            except Exception as exc:  # noqa: BLE001 - one bad page must not abort the class
                page_images[page] = None
                page_error[page] = str(exc)
                continue
            page_images[page] = img
            page_boxes[page] = found["matched"]
            if found["skew_warning"]:
                print(f"[ocr] {hs_key} trang {page}: {found['skew_warning']}", flush=True)
            if found["missing"]:
                page_error[page] = f"không thấy khung {', '.join(found['missing'])}"
                print(
                    f"[ocr] {hs_key} trang {page}: không dò được khung cho "
                    f"{', '.join(found['missing'])} — chuyển sang giáo viên xem lại.",
                    flush=True,
                )

        for roi in rois:
            page = _roi_page(roi)
            img = page_images.get(page)
            box = page_boxes.get(page, {}).get(roi["cau_key"])
            if img is None or box is None:
                entries[roi["cau_key"]] = {
                    "status": REGION_NOT_FOUND,
                    "content": {"lines": []},
                    "reason": page_error.get(page, "không dò được khung trên trang này"),
                }
            else:
                # `box` là pixel trên chính ảnh của em này (module1 trả về sau
                # khi ghép), nên crop thẳng, không qua ảnh warp nào.
                entries[roi["cau_key"]] = _cau_entry_for_roi(
                    {**roi, **box}, img, crop_dir, hs_key, save_crops
                )

            # Read the exam code off the paper rather than trusting the folder
            # the images came in. Only overrides the configured code when OCR
            # actually returned something parseable: a blank or unreadable box
            # must fall back, because the wrong rubric scores every question
            # of that student wrong while looking like a normal result.
            if roi["cau_key"] == MA_DE_KEY:
                read = _parse_ma_de(
                    (entries[MA_DE_KEY].get("content") or {}).get("lines") or []
                )
                if read:
                    entries["ma_de"] = read
                    if read != configured_ma_de:
                        print(
                            f"[ocr] {hs_key}: mã đề đọc từ ảnh là {read!r}, "
                            f"khác mã đề của thư mục ({configured_ma_de!r}) — dùng {read!r}.",
                            flush=True,
                        )
                else:
                    print(
                        f"[ocr] {hs_key}: không đọc được mã đề từ ảnh, "
                        f"giữ {configured_ma_de!r} theo thư mục.",
                        flush=True,
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
