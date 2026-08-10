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

    dots = []
    avg_h = 0
    if len(contours) > 0:
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            if 1 <= h <= 10 and 1 <= w <= 10:
                aspect_ratio = w / float(h)
                if 0.6 <= aspect_ratio <= 1.6:
                    dots.append({"x": x, "y": y, "w": w, "h": h, "cx": x + w // 2, "cy": y + h // 2})

    if len(dots) > 0:
        avg_h = sum([d["h"] for d in dots]) / len(dots)
        avg_h = max(3, avg_h)

    GAP_MULT_MIN = 0.5
    GAP_MULT_MAX = 2.5
    Y_DIFF_TOLERANCE = 1.0

    valid_short_lines = []

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
                    if len(current_chain) >= 4:
                        min_x = current_chain[0]["x"]
                        max_x = current_chain[-1]["x"] + current_chain[-1]["w"]
                        min_y = min([d["y"] for d in current_chain])
                        max_y = max([d["y"] + d["h"] for d in current_chain])
                        valid_short_lines.append(
                            {"x": min_x, "y": min_y, "w": max_x - min_x, "h": max_y - min_y}
                        )
                    current_chain = [d2]

            if len(current_chain) >= 4:
                min_x = current_chain[0]["x"]
                max_x = current_chain[-1]["x"] + current_chain[-1]["w"]
                min_y = min([d["y"] for d in current_chain])
                max_y = max([d["y"] + d["h"] for d in current_chain])
                valid_short_lines.append(
                    {"x": min_x, "y": min_y, "w": max_x - min_x, "h": max_y - min_y}
                )

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


def pad_dotted_bboxes(final_bboxes, img_height, img_width):
    """
    Mở rộng (padding) cho các bbox nét đứt để bao trọn vùng không gian rộng hơn.
    """
    expanded_bboxes = []

    for box in final_bboxes:
        x, y, w, h = box["x"], box["y"], box["w"], box["h"]

        y_start = y - 60
        y_end = y + h + 20

        x_start = x - 50
        x_end = x + w + 100

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
            y_start = y
            y_end = y + h + 50

            x_start = x - 50
            x_end = x + w + 50

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

    # --- QUY TRÌNH NÉT ĐỨT ---
    binary_clean = preprocess_image(img)
    valid_short_lines, avg_h, dot_count = extract_dotted_lines(binary_clean)
    final_bboxes = group_dotted_bboxes(valid_short_lines, avg_h)
    expanded_bboxes = pad_dotted_bboxes(final_bboxes, img_height, img_width)

    # --- QUY TRÌNH BẢNG BIỂU ---
    table_bboxes, binary_table, table_mask = extract_tables(img)
    expanded_answer_table_bboxes = filter_and_pad_tables(
        table_bboxes, binary_table, table_mask, img_height, img_width
    )

    # --- GOM NHÓM & SẮP XẾP ---
    sorted_rois = map_and_sort_rois(expanded_bboxes, expanded_answer_table_bboxes)

    rois = [
        {"x": r["x"], "y": r["y"], "w": r["w"], "h": r["h"], "type": r["type"]} for r in sorted_rois
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
