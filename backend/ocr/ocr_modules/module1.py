"""
Module 1 — ROI Detection (chỉ bảng biểu).

Port từ notebook gốc: mmlab-module1-roi-detection.ipynb — nhưng đã BỎ HOÀN
TOÀN phần dò "dòng chấm/gạch" (dotted-line detection: preprocess_image /
extract_dotted_lines / group_dotted_bboxes / pad_dotted_bboxes trong bản gốc).
Module này dò DÒNG CHẤM và KHUNG BẢNG:

    extract_dotted_lines      -> tìm các dòng chấm để điền đáp án
    group_dotted_bboxes       -> gom các dòng chấm thành từng vùng trả lời
    extract_tables             -> tìm mọi khung bảng bằng morphology
    map_and_sort_rois          -> gộp các bbox, sắp xếp theo thứ tự đọc
    process_image             -> hàm tổng, gọi 3 hàm trên theo thứ tự

Dùng đúng opencv-python + numpy như notebook (không viết lại thuật toán bằng
ngôn ngữ khác), chỉ đổi input/output từ (folder ảnh -> file JSON) thành (ảnh
upload qua HTTP -> JSON response) để FastAPI có thể serve.
"""

import cv2
import numpy as np

# The notebook's fixed-pixel padding (50px) was tuned on the scans it was
# written against: only holds at one resolution. On an A4 page rendered at
# ~72 DPI (595x816, what this repo's exam PNGs actually are) a fixed 50px pad
# is 6% of the page height; on a 2400px scan it's 2%. Expressing it relative
# to the page instead keeps the same physical padding regardless of DPI. This
# constant is the height the original number was calibrated for; it only
# converts that number into a ratio, and is not a size anything is resized to.
REFERENCE_PAGE_HEIGHT = 2000


def page_scale(img_height: int) -> float:
    """How much to shrink/grow the notebook's pixel thresholds for this page."""
    return img_height / REFERENCE_PAGE_HEIGHT


def preprocess_image(img: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    return cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 21, 25
    )


def extract_dotted_lines(binary: np.ndarray) -> tuple[list[dict], float]:
    """Find short, regularly spaced marks that form printed answer lines."""
    contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    scale = max(0.5, binary.shape[0] / REFERENCE_PAGE_HEIGHT)
    dots = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        min_size = max(1, round(scale))
        max_size = max(10, round(10 * scale))
        if min_size <= h <= max_size and min_size <= w <= max_size:
            aspect_ratio = w / float(h)
            if 0.6 <= aspect_ratio <= 1.6:
                dots.append({"x": x, "y": y, "w": w, "h": h, "cx": x + w // 2, "cy": y + h // 2})

    if not dots:
        return [], 0.0

    avg_h = max(3 * scale, sum(dot["h"] for dot in dots) / len(dots))
    rows = []
    for dot in sorted(dots, key=lambda item: item["cy"]):
        if not rows or abs(dot["cy"] - rows[-1][0]["cy"]) > avg_h:
            rows.append([dot])
        else:
            rows[-1].append(dot)

    lines = []
    for row in rows:
        row = sorted(row, key=lambda item: item["x"])
        chain = [row[0]]
        for dot in row[1:]:
            gap = dot["x"] - (chain[-1]["x"] + chain[-1]["w"])
            if 0.5 * avg_h <= gap <= 4.5 * avg_h:
                chain.append(dot)
            else:
                if len(chain) >= 4:
                    lines.append(_bbox(chain))
                chain = [dot]
        if len(chain) >= 4:
            lines.append(_bbox(chain))
    return lines, avg_h


def _bbox(items: list[dict]) -> dict:
    x1 = min(item["x"] for item in items)
    y1 = min(item["y"] for item in items)
    x2 = max(item["x"] + item["w"] for item in items)
    y2 = max(item["y"] + item["h"] for item in items)
    return {"x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1}


def group_dotted_bboxes(lines: list[dict], avg_h: float) -> list[dict]:
    """Combine adjacent dotted rows into answer areas without using a template."""
    if not lines:
        return []
    scale = max(0.5, avg_h / 3) if avg_h else 1.0
    merged = []
    for line in sorted(lines, key=lambda item: (item["y"], item["x"])):
        if merged and abs(line["y"] - merged[-1]["y"]) <= 2 * avg_h:
            merged[-1] = _union(merged[-1], line)
        else:
            merged.append(line.copy())

    blocks = []
    for line in merged:
        if blocks:
            previous = blocks[-1][-1]
            gap = line["y"] - (previous["y"] + previous["h"])
            overlap = max(0, min(previous["x"] + previous["w"], line["x"] + line["w"]) - max(previous["x"], line["x"]))
            overlap_ratio = overlap / max(1, min(previous["w"], line["w"]))
            width_ratio = min(previous["w"], line["w"]) / max(previous["w"], line["w"])
            if 0 < gap < 30 * scale and (width_ratio >= 0.7 or overlap_ratio >= 0.8):
                blocks[-1].append(line)
                continue
        blocks.append([line])

    return [_bbox(block) for block in blocks]


def _union(first: dict, second: dict) -> dict:
    return _bbox([first, second])


def pad_dotted_bboxes(boxes: list[dict], img_height: int, img_width: int) -> list[dict]:
    pad_x = round(50 * page_scale(img_height))
    pad_right = round(100 * page_scale(img_height))
    pad_top = round(60 * page_scale(img_height))
    pad_bottom = round(20 * page_scale(img_height))
    output = []
    for box in boxes:
        if box["w"] >= img_width * 0.75:
            continue
        x1 = max(0, box["x"] - pad_x)
        y1 = max(0, box["y"] - pad_top)
        x2 = min(img_width, box["x"] + box["w"] + pad_right)
        y2 = min(img_height, box["y"] + box["h"] + pad_bottom)
        if x2 - x1 >= img_width * 0.75:
            continue
        output.append({"x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1, "type": "fill_in_blank"})
    return output


def extract_tables(img):
    """
    Nhận diện và trích xuất khung bảng biểu bằng phương pháp hình thái học (Morphology).
    """
    gray_table = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    binary_table = cv2.adaptiveThreshold(
        gray_table, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 5
    )

    img_height, img_width = binary_table.shape

    scale = 40
    horizontal_size = max(20, img_width // scale)
    vertical_size = max(20, img_height // scale)

    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (horizontal_size, 1))
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, vertical_size))

    horizontal_lines = cv2.morphologyEx(binary_table, cv2.MORPH_OPEN, horizontal_kernel)
    vertical_lines = cv2.morphologyEx(binary_table, cv2.MORPH_OPEN, vertical_kernel)

    table_mask = cv2.add(horizontal_lines, vertical_lines)

    kernel_dilate = np.ones((3, 3), np.uint8)
    table_mask = cv2.dilate(table_mask, kernel_dilate, iterations=1)

    contours_table, _ = cv2.findContours(table_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    table_bboxes = []
    min_table_area = (img_width * img_height) * 0.01

    for cnt in contours_table:
        x, y, w, h = cv2.boundingRect(cnt)
        area = w * h

        if w > 100 and h > 50 and area > min_table_area:
            table_bboxes.append({"x": x, "y": y, "w": w, "h": h})

    return table_bboxes, binary_table, table_mask


def filter_and_pad_tables(table_bboxes, binary_table, table_mask, img_height, img_width, text_density_threshold=2.0):
    """
    Lọc bỏ các bảng chứa nội dung đề bài (nhiều chữ) và mở rộng (padding)
    tọa độ cho các bảng để học sinh điền đáp án (ít/không có chữ).
    """
    expanded_answer_table_bboxes = []

    for box in table_bboxes:
        x, y, w, h = box["x"], box["y"], box["w"], box["h"]

        roi_binary = binary_table[y : y + h, x : x + w]
        roi_grid = table_mask[y : y + h, x : x + w]
        roi_text_only = cv2.subtract(roi_binary, roi_grid)
        text_pixels = cv2.countNonZero(roi_text_only)

        text_density = (text_pixels / (w * h)) * 100

        if text_density < text_density_threshold:
            # Fixed-pixel problem: 50px is 6% of a 816px page and 2% of a
            # 2400px one — expressed relative to the page instead.
            pad = round(50 * page_scale(img_height))

            y_start = y
            y_end = y + h + pad

            x_start = x - pad
            x_end = x + w + pad

            x_start = max(0, x_start)
            y_start = max(0, y_start)
            x_end = min(img_width, x_end)
            y_end = min(img_height, y_end)

            new_w = x_end - x_start
            new_h = y_end - y_start

            expanded_answer_table_bboxes.append(
                {"x": x_start, "y": y_start, "w": new_w, "h": new_h, "type": "table"}
            )
        # else: đây là bảng đề bài -> bỏ qua không padding

    return expanded_answer_table_bboxes


def map_and_sort_rois(expanded_bboxes, expanded_answer_table_bboxes=None, y_tolerance=None):
    """
    Sắp xếp các ROI bảng biểu theo thứ tự không gian: từ trên xuống dưới,
    từ trái qua phải (các bbox có center_y gần nhau được coi là cùng một
    "hàng" và sắp theo x trong hàng đó).
    """
    all_rois = []
    expanded_answer_table_bboxes = expanded_answer_table_bboxes or []
    if y_tolerance is None:
        y_tolerance = 30

    for box in expanded_bboxes:
        all_rois.append(
            {
                "x": box["x"],
                "y": box["y"],
                "w": box["w"],
                "h": box["h"],
                "type": box.get("type", "fill_in_blank"),
                "center_y": box["y"] + box["h"] // 2,
            }
        )

    for box in expanded_answer_table_bboxes:
        all_rois.append(
            {
                "x": box["x"],
                "y": box["y"],
                "w": box["w"],
                "h": box["h"],
                "type": box.get("type", "table"),
                "center_y": box["y"] + box["h"] // 2,
            }
        )

    sorted_rois = []

    if len(all_rois) > 0:
        all_rois.sort(key=lambda b: b["center_y"])

        current_row = [all_rois[0]]
        for i in range(1, len(all_rois)):
            box = all_rois[i]
            if abs(box["center_y"] - current_row[-1]["center_y"]) <= y_tolerance:
                current_row.append(box)
            else:
                sorted_rois.extend(sorted(current_row, key=lambda b: b["x"]))
                current_row = [box]

        sorted_rois.extend(sorted(current_row, key=lambda b: b["x"]))

    return sorted_rois


def detect_answer_regions(img: np.ndarray) -> list[dict]:
    """Detect answer regions on the image itself, without a blank template."""
    img_height, img_width = img.shape[:2]
    binary = preprocess_image(img)
    dotted_lines, avg_h = extract_dotted_lines(binary)
    dotted_boxes = pad_dotted_bboxes(
        group_dotted_bboxes(dotted_lines, avg_h), img_height, img_width
    )
    table_bboxes, binary_table, table_mask = extract_tables(img)
    table_boxes = filter_and_pad_tables(
        table_bboxes, binary_table, table_mask, img_height, img_width
    )

    return map_and_sort_rois(
        dotted_boxes,
        table_boxes,
        y_tolerance=max(30, round(30 * page_scale(img_height))),
    )


def process_image(img, filename: str):
    """
    Chạy pipeline Module 1 (chỉ bảng biểu) cho một ảnh (đã cv2.imdecode), trả
    về dict theo shape mà frontend (PageResult trong module1.ts) đang mong đợi:

    {
        "filename": str,
        "width": int,
        "height": int,
        "rois": [{"x","y","w","h","type"}, ...],
        "stats": {"tables": int}
    }
    """
    img_height, img_width = img.shape[:2]
    sorted_rois = detect_answer_regions(img)

    rois = [
        {
            "x": r["x"],
            "y": r["y"],
            "w": r["w"],
            "h": r["h"],
            "type": r["type"],
        }
        for r in sorted_rois
    ]

    return {
        "filename": filename,
        "width": img_width,
        "height": img_height,
        "rois": rois,
        "stats": {
            "tables": sum(r["type"] == "table" for r in sorted_rois),
            "regions": len(sorted_rois),
        },
    }
