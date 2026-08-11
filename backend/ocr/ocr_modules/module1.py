"""
Module 1 — ROI Detection.

Port gần như nguyên vẹn (1:1) từ notebook gốc:
mmlab-module1-roi-detection.ipynb

Không "viết lại" thuật toán bằng ngôn ngữ khác — dùng đúng opencv-python +
numpy như notebook, chỉ đổi input/output từ (folder ảnh -> file JSON)
thành (ảnh upload qua HTTP -> JSON response) để FastAPI có thể serve.
"""

import cv2
import numpy as np

# The notebook's thresholds were absolute pixel counts, tuned on the scans it
# was written against: a dot at most 10px, a bbox padded by 60px upward. Those
# only hold at one resolution. On an A4 page rendered at ~72 DPI (595x816, what
# this repo's exam PNGs actually are) a 60px pad is 7% of the page height, so
# every answer region swallowed the paragraph above it, and the 10px dot filter
# matched Vietnamese diacritics — the dot of an "i", a dấu nặng — which then
# chained into phantom "dotted lines" running through body text.
#
# Everything below is expressed relative to the page instead. This constant is
# the height the original numbers were calibrated for; it only converts those
# numbers into ratios, and is not a size anything is resized to.
REFERENCE_PAGE_HEIGHT = 2000

# Below this, detection is upscaled first (see `process_image`). Scaling the
# thresholds down is not enough on its own: on the 595x816 exam renders in this
# repo a printed dotted line survives as 1-2px smudges, mostly wider than they
# are tall, so the squareness test throws them away and a line ends up with
# fewer than the 4 dots a chain needs. The information is missing from the
# pixels, not mis-measured — no threshold recovers it, but interpolating the
# page back up to a workable size does.
MIN_WORKING_HEIGHT = 1600
MAX_UPSCALE = 3

# A chain of 4+ evenly spaced dots is not enough on its own to mean "answer
# line": Vietnamese diacritics sit in rows too, so body text produces short
# chains that used to become regions over the middle of a code listing. On the
# exam pages here every real dotted line runs at least 6.9% of the page width
# while every text-derived chain stops at 3.4%, so requiring a minimum run
# separates them cleanly. It is a length test, not a content test — a genuinely
# short printed blank would need this lowered.
MIN_SEGMENT_WIDTH_RATIO = 0.04

# A printed dotted line is a long, perfectly flat run: its bounding box is one
# dot tall and dozens of dots wide. A chain accidentally formed from body text
# is short, and taller than it looks because punctuation and diacritics sit at
# slightly different heights. Measured on page 1, where the three real regions
# and the two phantom ones were previously indistinguishable by width alone:
# every real segment is at least 24.5 times wider than tall, every phantom at
# most 12.5. The threshold sits in that gap.
MIN_SEGMENT_ASPECT = 18.0


def page_scale(img_height: int) -> float:
    """How much to shrink/grow the notebook's pixel thresholds for this page."""
    return img_height / REFERENCE_PAGE_HEIGHT


# ==========================================
# CELL 2: TIỀN XỬ LÝ ẢNH
# ==========================================
def preprocess_image(img):
    """
    Hàm tiền xử lý ảnh: Chuyển ảnh màu thành ảnh nhị phân (đen/trắng)
    để chuẩn bị cho việc tìm contours.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 1. LÀM MỜ (BLUR): Xóa nhiễu bề mặt giấy
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # 2. ADAPTIVE THRESHOLDING: Nhị phân hóa cắt ngưỡng thông minh
    binary = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 21, 25
    )

    return binary


def extract_dotted_lines(binary):
    """
    Tìm và trích xuất các đoạn nét đứt (cả ngắn và dài) từ ảnh nhị phân.

    Returns:
        valid_short_lines: [{'x','y','w','h'}, ...]
        avg_h: chiều cao trung bình của 1 dấu chấm
    """
    contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    # Was a flat `<= 10`. Scaled, so the filter means the same physical size on
    # a 72-DPI render as on a 300-DPI scan.
    max_dot = max(3, round(10 * page_scale(binary.shape[0])))

    dots = []
    avg_h = 0
    if len(contours) > 0:
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            if 1 <= h <= max_dot and 1 <= w <= max_dot:
                aspect_ratio = w / float(h)
                if 0.6 <= aspect_ratio <= 1.6:
                    dots.append({"x": x, "y": y, "w": w, "h": h, "cx": x + w // 2, "cy": y + h // 2})

    if len(dots) > 0:
        avg_h = sum([d["h"] for d in dots]) / len(dots)
        avg_h = max(3, avg_h)

    GAP_MULT_MIN = 0.5
    # Was 2.5. On these pages a printed dotted line spaces its dots about 3x the
    # dot height apart, so the old ceiling broke every real line into 4-5 stubs,
    # none long enough to be recognised — pages 2, 3, 5 and 8 yielded nothing at
    # all. Measured across all 9 pages: 4.5 finds regions on every page, while
    # 6.0 starts chaining unrelated punctuation together again.
    GAP_MULT_MAX = 4.5
    Y_DIFF_TOLERANCE = 1.0
    min_segment_width = binary.shape[1] * MIN_SEGMENT_WIDTH_RATIO

    valid_short_lines = []

    def keep(chain):
        """A chain becomes a segment only if it is long enough to be a blank."""
        if len(chain) < 4:
            return
        min_x = chain[0]["x"]
        max_x = chain[-1]["x"] + chain[-1]["w"]
        width = max_x - min_x
        if width < min_segment_width:
            return
        min_y = min(d["y"] for d in chain)
        max_y = max(d["y"] + d["h"] for d in chain)
        height = max(1, max_y - min_y)
        if width / height < MIN_SEGMENT_ASPECT:
            return
        valid_short_lines.append({"x": min_x, "y": min_y, "w": width, "h": max_y - min_y})

    if len(dots) > 1:
        dots_y_sorted = sorted(dots, key=lambda d: d["cy"])

        current_y_line = dots_y_sorted[0]["cy"]
        row_dots = [dots_y_sorted[0]]

        raw_lines = []
        for i in range(1, len(dots_y_sorted)):
            d = dots_y_sorted[i]
            if abs(d["cy"] - current_y_line) <= (avg_h * Y_DIFF_TOLERANCE):
                row_dots.append(d)
            else:
                if len(row_dots) >= 2:
                    raw_lines.append(sorted(row_dots, key=lambda d: d["x"]))
                row_dots = [d]
                current_y_line = d["cy"]
        if len(row_dots) >= 2:
            raw_lines.append(sorted(row_dots, key=lambda d: d["x"]))

        for line in raw_lines:
            current_chain = [line[0]]
            for i in range(1, len(line)):
                d1 = current_chain[-1]
                d2 = line[i]

                gap_x = d2["x"] - (d1["x"] + d1["w"])

                if (avg_h * GAP_MULT_MIN) <= gap_x <= (avg_h * GAP_MULT_MAX):
                    current_chain.append(d2)
                else:
                    keep(current_chain)
                    current_chain = [d2]

            keep(current_chain)

    return valid_short_lines, avg_h, len(dots)


def group_dotted_bboxes(valid_short_lines, avg_h):
    """
    Gom các đoạn nét đứt rời rạc thành các block (đoạn văn/vùng điền đáp án lớn).
    """
    final_bboxes = []

    # --- 1. GOM CÁC BBOX THEO CHIỀU NGANG ---
    horizontal_merged_lines = []

    if len(valid_short_lines) > 0:
        sorted_by_y = sorted(valid_short_lines, key=lambda b: (b["y"], b["x"]))
        current_hline = sorted_by_y[0]

        for i in range(1, len(sorted_by_y)):
            next_box = sorted_by_y[i]
            if abs(next_box["y"] - current_hline["y"]) <= (avg_h * 2):
                min_x = min(current_hline["x"], next_box["x"])
                min_y = min(current_hline["y"], next_box["y"])
                max_x = max(current_hline["x"] + current_hline["w"], next_box["x"] + next_box["w"])
                max_y = max(current_hline["y"] + current_hline["h"], next_box["y"] + next_box["h"])
                current_hline = {"x": min_x, "y": min_y, "w": max_x - min_x, "h": max_y - min_y}
            else:
                horizontal_merged_lines.append(current_hline)
                current_hline = next_box
        horizontal_merged_lines.append(current_hline)

    # --- 2. GOM CÁC BBOX THEO CHIỀU DỌC (TẠO BLOCK) ---
    final_blocks = []

    if len(horizontal_merged_lines) > 0:
        horizontal_merged_lines = sorted(horizontal_merged_lines, key=lambda b: b["y"])
        current_block = [horizontal_merged_lines[0]]
        expected_gap = None

        for i in range(1, len(horizontal_merged_lines)):
            prev_box = current_block[-1]
            next_box = horizontal_merged_lines[i]

            gap_y = next_box["y"] - (prev_box["y"] + prev_box["h"])
            width_ratio = min(prev_box["w"], next_box["w"]) / max(prev_box["w"], next_box["w"])

            overlap_x = max(
                0,
                min(prev_box["x"] + prev_box["w"], next_box["x"] + next_box["w"])
                - max(prev_box["x"], next_box["x"]),
            )

            min_w = min(prev_box["w"], next_box["w"])
            overlap_ratio = overlap_x / min_w if min_w > 0 else 0

            right_diff = abs((prev_box["x"] + prev_box["w"]) - (next_box["x"] + next_box["w"]))
            is_right_aligned = right_diff <= (avg_h * 5)

            is_x_valid = (width_ratio >= 0.7) or (overlap_ratio >= 0.8) or is_right_aligned

            is_gap_valid = False
            if gap_y > 0 and gap_y < (avg_h * 30):
                if expected_gap is None:
                    is_gap_valid = True
                else:
                    if abs(gap_y - expected_gap) <= (avg_h * 5):
                        is_gap_valid = True

            if is_x_valid and is_gap_valid:
                current_block.append(next_box)
                if len(current_block) >= 2:
                    gaps = [
                        current_block[k]["y"] - (current_block[k - 1]["y"] + current_block[k - 1]["h"])
                        for k in range(1, len(current_block))
                    ]
                    expected_gap = sum(gaps) / len(gaps)
            else:
                final_blocks.append(current_block)
                current_block = [next_box]
                expected_gap = None

        final_blocks.append(current_block)

    # --- 3. TẠO BBOX TO CHO TỪNG BLOCK ---
    for block in final_blocks:
        min_x = min([b["x"] for b in block])
        min_y = min([b["y"] for b in block])
        max_x = max([b["x"] + b["w"] for b in block])
        max_y = max([b["y"] + b["h"] for b in block])

        final_bboxes.append({"x": min_x, "y": min_y, "w": max_x - min_x, "h": max_y - min_y})

    return final_bboxes


def pad_dotted_bboxes(final_bboxes, img_height, img_width, avg_h=0):
    """
    Mở rộng (padding) cho các bbox nét đứt để bao trọn vùng không gian rộng hơn.

    Padding is a multiple of the dot height rather than a fixed 60/20/50/100
    pixels. `avg_h` is already this module's unit of scale (the gap and
    alignment rules are all multiples of it), and it tracks the page's actual
    print size, so the region grows with the writing rather than with an
    assumption about DPI. The multipliers below are the notebook's pixel values
    divided by the ~8px dot they were tuned against, so the shape of the result
    is unchanged at that resolution.
    """
    expanded_bboxes = []
    unit = avg_h if avg_h and avg_h > 0 else max(3, 8 * page_scale(img_height))

    pad_top = round(unit * 7.5)
    pad_bottom = round(unit * 2.5)
    pad_left = round(unit * 6.25)
    pad_right = round(unit * 12.5)

    for box in final_bboxes:
        x, y, w, h = box["x"], box["y"], box["w"], box["h"]

        y_start = y - pad_top
        y_end = y + h + pad_bottom

        x_start = x - pad_left
        x_end = x + w + pad_right

        x_start = max(0, x_start)
        y_start = max(0, y_start)
        x_end = min(img_width, x_end)
        y_end = min(img_height, y_end)

        new_w = x_end - x_start
        new_h = y_end - y_start

        expanded_bboxes.append(
            {"x": x_start, "y": y_start, "w": new_w, "h": new_h, "type": "fill_in_blank"}
        )

    return expanded_bboxes


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
            # Same fixed-pixel problem as pad_dotted_bboxes: 50px is 6% of a
            # 816px page and 2% of a 2400px one.
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


def map_and_sort_rois(expanded_bboxes, expanded_answer_table_bboxes, y_tolerance=30):
    """
    Gom chung tất cả các loại ROI (nét đứt, bảng biểu) vào một danh sách,
    sau đó sắp xếp thứ tự không gian từ trên xuống dưới, từ trái qua phải.
    """
    all_rois = []

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


def process_image(img, filename: str):
    """
    Chạy toàn bộ pipeline Module 1 cho một ảnh (đã cv2.imdecode), trả về dict
    theo đúng shape mà frontend (PageResult trong module1.ts) đang mong đợi:

    {
        "filename": str,
        "width": int,
        "height": int,
        "rois": [{"x","y","w","h","type"}, ...],
        "stats": {"dots","segments","blocks","tables"}
    }
    """
    img_height, img_width = img.shape[:2]

    # Detect on an upscaled copy when the page is too small for a printed dotted
    # line to survive as separate dots, then divide the boxes back down so the
    # caller still gets coordinates in the original page's pixels — roi_config
    # and every crop downstream are expressed against that, not against
    # whatever size detection happened to run at.
    upscale = 1
    if img_height < MIN_WORKING_HEIGHT:
        upscale = min(MAX_UPSCALE, max(1, round(MIN_WORKING_HEIGHT / img_height)))
    if upscale > 1:
        img = cv2.resize(img, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_CUBIC)
    work_height, work_width = img.shape[:2]

    # --- QUY TRÌNH NÉT ĐỨT ---
    binary_clean = preprocess_image(img)
    valid_short_lines, avg_h, dot_count = extract_dotted_lines(binary_clean)
    final_bboxes = group_dotted_bboxes(valid_short_lines, avg_h)
    expanded_bboxes = pad_dotted_bboxes(final_bboxes, work_height, work_width, avg_h)

    # --- QUY TRÌNH BẢNG BIỂU ---
    table_bboxes, binary_table, table_mask = extract_tables(img)
    expanded_answer_table_bboxes = filter_and_pad_tables(
        table_bboxes, binary_table, table_mask, work_height, work_width
    )

    # --- GOM NHÓM & SẮP XẾP ---
    sorted_rois = map_and_sort_rois(expanded_bboxes, expanded_answer_table_bboxes)

    rois = [
        {
            "x": round(r["x"] / upscale),
            "y": round(r["y"] / upscale),
            "w": round(r["w"] / upscale),
            "h": round(r["h"] / upscale),
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
            "dots": dot_count,
            "segments": len(valid_short_lines),
            "blocks": len(final_bboxes),
            "tables": len(expanded_answer_table_bboxes),
        },
    }
