"""
Module 1 — ROI Detection (chỉ bảng biểu).

Port từ notebook gốc: mmlab-module1-roi-detection.ipynb — nhưng đã BỎ HOÀN
TOÀN phần dò "dòng chấm/gạch" (dotted-line detection: preprocess_image /
extract_dotted_lines / group_dotted_bboxes / pad_dotted_bboxes trong bản gốc).
Module này giờ chỉ còn dò KHUNG BẢNG, không lọc theo nội dung:

    extract_tables    -> tìm mọi khung bảng bằng morphology
    pad_tables         -> mở rộng (padding) tọa độ mọi khung tìm được
    map_and_sort_rois  -> gộp các bbox bảng, sắp xếp theo thứ tự đọc
    process_image      -> hàm tổng, gọi 3 hàm trên theo thứ tự

Không còn bước lọc bảng đề bài theo mật độ chữ (text_density) — mọi khung
bảng dò được (kể cả bảng đề, bảng đáp án, khung "MÃ ĐỀ", khung thông tin
sinh viên...) đều được giữ và trả về nguyên vẹn. Việc chọn khung nào là ô
đáp án là việc của người dùng (RoiMapper) hoặc của is_first_page (chỉ bỏ
2 khung đầu trang 1) — không phải việc của Module 1 nữa.

Dùng đúng opencv-python + numpy như notebook (không viết lại thuật toán bằng
ngôn ngữ khác), chỉ đổi input/output từ (folder ảnh -> file JSON) thành (ảnh
upload qua HTTP -> JSON response) để FastAPI có thể serve.

=== PHẦN THÊM MỚI (so với bản gốc chỉ có các hàm xử lý) ===
Thêm một CLI/hàm tiện ích để chạy trực tiếp trên Kaggle (hoặc máy local):
  - Đọc 1 ảnh từ path (vd: /kaggle/input/.../page1.png)
  - Chạy pipeline process_image
  - Ghi kết quả ROI ra file JSON (mặc định cạnh ảnh, đuôi .roi.json)
  - Vẽ các khung ROI lên ảnh, lưu ảnh preview (.roi.png)
  - Hiển thị ảnh preview (matplotlib) — hữu ích trong Kaggle notebook
"""

import argparse
import json
import os

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


def extract_tables(img):
    """
    Nhận diện và trích xuất khung bảng biểu bằng phương pháp hình thái học (Morphology).
    Trả về mọi khung tìm được, không lọc theo nội dung bên trong.
    """
    gray_table = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    binary_table = cv2.adaptiveThreshold(
        gray_table, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 5
    )

    img_height, img_width = binary_table.shape
    scale = page_scale(img_height)

    kernel_scale = 40
    horizontal_size = max(20, img_width // kernel_scale)
    vertical_size = max(20, img_height // kernel_scale)

    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (horizontal_size, 1))
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, vertical_size))

    horizontal_lines = cv2.morphologyEx(binary_table, cv2.MORPH_OPEN, horizontal_kernel)
    vertical_lines = cv2.morphologyEx(binary_table, cv2.MORPH_OPEN, vertical_kernel)

    table_mask = cv2.add(horizontal_lines, vertical_lines)

    kernel_dilate = np.ones((3, 3), np.uint8)
    table_mask = cv2.dilate(table_mask, kernel_dilate, iterations=1)

    contours_table, _ = cv2.findContours(table_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    table_bboxes = []

    # NOTE: bản gốc dùng `min_table_area = (img_width*img_height)*0.01`
    # (1% diện tích CẢ TRANG) cộng ngưỡng cố định `w>100 and h>50`. Ngưỡng đó
    # được canh cho các bảng lớn (bảng thông tin, bảng chữ ký...) và vô tình
    # loại mất các khung câu trả lời một dòng nhỏ (vd khung "MÃ ĐỀ", khung
    # "Câu 1: điền một số" ~190x45px) — những khung này có diện tích chỉ
    # ~0.5-0.6% trang nên bị lọc mất dù là ROI hợp lệ. Vì module đã bỏ hẳn
    # bước lọc theo nội dung (không còn phân biệt bảng đề/bảng đáp án), ngưỡng
    # lọc kích thước ở đây chỉ nên nhằm loại nhiễu (vệt mực nhỏ, viền trang,
    # đường kẻ lẻ) chứ không nên loại khung câu trả lời hợp lệ. Đổi sang
    # ngưỡng min width/height co giãn theo kích thước trang (dùng lại
    # page_scale, giống cách padding đã co giãn) và bỏ ngưỡng "1% cả trang".
    min_box_w = max(20, round(40 * scale))
    min_box_h = max(15, round(25 * scale))
    min_table_area = min_box_w * min_box_h

    for cnt in contours_table:
        x, y, w, h = cv2.boundingRect(cnt)
        area = w * h

        if w > min_box_w and h > min_box_h and area > min_table_area:
            table_bboxes.append({"x": x, "y": y, "w": w, "h": h})

    return table_bboxes


def pad_tables(table_bboxes, img_height, img_width):
    """
    Mở rộng (padding) tọa độ cho mọi khung bảng tìm được — không lọc bớt
    khung nào theo nội dung bên trong (đã bỏ bước lọc bảng đề theo mật độ
    chữ so với bản trước).

    Chỉ nới theo CHIỀU NGANG. Bản gốc nới thêm `pad` xuống dưới (`y + h + pad`)
    mà không nới lên trên, nên mọi khung đều phình xuống: đo trên trang 2 mã đề
    76 (2216x3260) pad là 82px trong khi khe giữa hai khung liền nhau chỉ 89px,
    nên đáy khung câu 6 tụt xuống cách đỉnh khung câu 7 đúng 7px và nuốt trọn
    dòng chữ in "Question 7:" nằm trong khe đó. Ảnh cắt vì thế kèm tiêu đề của
    câu kế tiếp, và OCR đọc nó thành một dòng bài làm.
    """
    padded_table_bboxes = []

    for box in table_bboxes:
        x, y, w, h = box["x"], box["y"], box["w"], box["h"]

        # Fixed-pixel problem: 50px is 6% of a 816px page and 2% of a
        # 2400px one — expressed relative to the page instead.
        pad = round(50 * page_scale(img_height))

        y_start = y
        y_end = y + h

        x_start = x - pad
        x_end = x + w + pad

        x_start = max(0, x_start)
        y_start = max(0, y_start)
        x_end = min(img_width, x_end)
        y_end = min(img_height, y_end)

        new_w = x_end - x_start
        new_h = y_end - y_start

        padded_table_bboxes.append(
            {"x": x_start, "y": y_start, "w": new_w, "h": new_h, "type": "table"}
        )

    return padded_table_bboxes


def map_and_sort_rois(padded_table_bboxes, y_tolerance=30):
    """
    Sắp xếp các ROI bảng biểu theo thứ tự không gian: từ trên xuống dưới,
    từ trái qua phải (các bbox có center_y gần nhau được coi là cùng một
    "hàng" và sắp theo x trong hàng đó).
    """
    all_rois = []

    for box in padded_table_bboxes:
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


# Trang đầu tiên của mỗi học sinh luôn có 2 khung không phải ô đáp án: khung
# "MÃ ĐỀ" và khung thông tin sinh viên (STT/MSSV/Họ tên) — xem MMLAB_TEST.pdf,
# trang 1. Vì Module 1 giờ không còn lọc theo nội dung, cả hai khung này (và
# bảng đề bài, nếu có) đều được giữ nguyên trong kết quả; chúng vẫn lọt vào
# danh sách ROI như hai khung đầu tiên theo thứ tự đọc (trên xuống, trái sang
# phải) mà map_and_sort_rois trả về.
N_HEADER_BOXES_FIRST_PAGE = 2


def drop_first_page_header_boxes(sorted_rois, n=N_HEADER_BOXES_FIRST_PAGE):
    """
    Bỏ n khung đầu tiên (theo thứ tự đọc) khỏi danh sách ROI đã sort — dùng
    cho trang đầu tiên của mỗi học sinh, nơi 2 khung đầu luôn là "MÃ ĐỀ" và
    "thông tin sinh viên" chứ không phải ô đáp án.
    """
    return sorted_rois[n:]


# =====================================================================
# ======  GẮN KHUNG DÒ ĐƯỢC VÀO TỪNG CÂU (thay cho align module 2)  ===
# =====================================================================
#
# Trước đây toạ độ ROI được đo MỘT LẦN trên tờ đề mẫu sạch, rồi mọi bài của
# học sinh được warp về đúng khung tờ mẫu đó (module2.align_images) để dùng
# chung toạ độ. Cách đó hỏng cả trang khi ảnh chụp chéo hoặc nghiêng: đo trên
# phiên chấm thật, HS_16 (41/750 điểm khớp, ảnh chụp chéo thành hình thang) và
# HS_29 (22/750, nghiêng 5.97°) mất trắng 4 câu mỗi em, và hệ thống báo là
# "học sinh không làm bài".
#
# Giờ ROI được dò trực tiếp trên tờ của chính học sinh, nên không còn bước
# warp nào để hỏng. Đổi lại phải trả lời được "khung này là câu mấy" mà không
# có toạ độ chung. Cách làm: người dùng khai bố cục MỘT LẦN dưới dạng TỈ LỆ
# trang (0..1) thay vì pixel, rồi mỗi khung dò được ghép với ô bố cục chồng
# lên nó nhiều nhất.
#
# Không gán theo thứ tự đọc: bộ dò không phải lúc nào cũng ra đúng số khung.
# Trên 19 bài thật của 3 mã đề, 18 bài ra đúng 3+4 khung, riêng HS_24 ra 5 —
# khung thừa là dải mép giấy bên phải (x=1947, w=157, h=3148 = suốt chiều cao
# trang). Tâm dọc của dải đó rơi vào giữa trang nên nó chen vào vị trí thứ 3,
# đẩy khung câu 9 thật xuống thứ 4. Gán theo thứ tự thì cả trang lệch một nấc
# mà không có dấu hiệu gì. Ghép theo tỉ lệ thì dải mép không chồng đủ lên ô
# nào nên bị loại, và câu 9 vẫn về đúng chỗ.

# Ngưỡng chồng lấn tối thiểu để coi một khung là ứng viên của một ô bố cục.
# Trên dữ liệu thật, khung đúng chồng lên ô của nó 0.85-0.95; dải mép giấy của
# HS_24 chồng cao nhất 0.06. Khoảng cách giữa hai nhóm rất rộng nên 0.35 nằm
# giữa mà không sát mép nào.
MIN_LAYOUT_OVERLAP = 0.35

# Phép canh bố cục (fit_layout_to_page) chỉ được xê dịch tối đa chừng này theo
# mỗi trục, tính theo tỉ lệ trang. Lệch do khung ảnh chụp đo được trên dữ liệu
# thật là 0.04, còn khoảng cách giữa hai ô liền nhau là 0.16 — chặn ở 0.10 nằm
# giữa hai mức đó. Không có chặn này, một trang chỉ dò ra vài khung sẽ bị trượt
# nguyên bố cục sang ô kế bên: cả trang vẫn "khớp", vẫn ra điểm, nhưng mỗi câu
# chấm bằng bài của câu khác — hỏng âm thầm, đúng kiểu ta đang tránh.
MAX_LAYOUT_SHIFT = 0.10


def to_relative(box, img_width: int, img_height: int) -> dict:
    """Đổi toạ độ pixel sang tỉ lệ trang (0..1) để so được giữa các ảnh khác cỡ."""
    return {
        "x": box["x"] / img_width,
        "y": box["y"] / img_height,
        "w": box["w"] / img_width,
        "h": box["h"] / img_height,
    }


def to_absolute(rel, img_width: int, img_height: int) -> dict:
    """Ngược của `to_relative` — tỉ lệ trang về pixel của một ảnh cụ thể."""
    x = round(rel["x"] * img_width)
    y = round(rel["y"] * img_height)
    return {
        "x": max(0, x),
        "y": max(0, y),
        "w": min(img_width - max(0, x), round(rel["w"] * img_width)),
        "h": min(img_height - max(0, y), round(rel["h"] * img_height)),
    }


def overlap_ratio(a, b) -> float:
    """
    Tỉ lệ chồng lấn (IoU) của hai hình chữ nhật cùng hệ toạ độ tỉ lệ.

    Dùng IoU chứ không dùng "phần giao / diện tích ô" vì chỉ IoU mới phạt được
    khung to quá khổ: dải mép giấy của HS_24 phủ suốt chiều cao trang nên nó
    chứa trọn nhiều ô, "phần giao / diện tích ô" sẽ ra 1.0 và ghép nhầm hết.
    """
    ax2, ay2 = a["x"] + a["w"], a["y"] + a["h"]
    bx2, by2 = b["x"] + b["w"], b["y"] + b["h"]

    inter_w = min(ax2, bx2) - max(a["x"], b["x"])
    inter_h = min(ay2, by2) - max(a["y"], b["y"])
    if inter_w <= 0 or inter_h <= 0:
        return 0.0

    inter = inter_w * inter_h
    union = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return inter / union if union > 0 else 0.0


def _center(box):
    return box["x"] + box["w"] / 2, box["y"] + box["h"] / 2


def _shift_slots(slots, sx, sy, dx, dy):
    """Co giãn + tịnh tiến bố cục quanh gốc toạ độ trang."""
    return [
        {**s, "x": s["x"] * sx + dx, "y": s["y"] * sy + dy, "w": s["w"] * sx, "h": s["h"] * sy}
        for s in slots
    ]


def _total_overlap(rel_rois, slots):
    return sum(max((overlap_ratio(r, s) for r in rel_rois), default=0.0) for s in slots)


def fit_layout_to_page(rel_rois, slots):
    """
    Canh bố cục đã khai về đúng vị trí trên trang này, trước khi ghép từng ô.

    Toạ độ tỉ lệ một mình không đủ, vì nó chuẩn hoá theo KHUNG ẢNH chứ không
    theo TỜ GIẤY: hai ảnh chụp cùng một tờ nhưng lấy nhiều/ít mặt bàn phía trên
    sẽ cho tỉ lệ khác nhau. Đo thật trên mã đề 38 trang 1, HS_21 và HS_31 lệch
    xuống 0.04 so với tờ mẫu, trong khi các khung câu 1-3 chỉ cao 0.031 — lệch
    hơn một thân khung nên chồng lấn về 0 và không ô nào ghép được, dù bố cục
    tờ giấy giống hệt.

    Ước lượng theo kiểu RANSAC thu nhỏ: mỗi cặp (khung, ô) đề cử một phép tịnh
    tiến, chấm điểm bằng tổng chồng lấn của cả bố cục, giữ phép tốt nhất, rồi
    tinh chỉnh thêm co giãn bằng bình phương tối thiểu trên các cặp đã khớp.
    Số khung mỗi trang chỉ vài cái nên duyệt hết mọi cặp vẫn rẻ.

    Trả về danh sách slots đã canh (vẫn theo tỉ lệ trang).
    """
    if not rel_rois or not slots:
        return slots

    best = (_total_overlap(rel_rois, slots), slots)
    for roi in rel_rois:
        rcx, rcy = _center(roi)
        for slot in slots:
            scx, scy = _center(slot)
            dx, dy = rcx - scx, rcy - scy
            if abs(dx) > MAX_LAYOUT_SHIFT or abs(dy) > MAX_LAYOUT_SHIFT:
                continue
            moved = _shift_slots(slots, 1.0, 1.0, dx, dy)
            score = _total_overlap(rel_rois, moved)
            if score > best[0]:
                best = (score, moved)

    aligned = best[1]

    # Tinh chỉnh: khớp thô ở trên chỉ tịnh tiến, còn ảnh chụp gần/xa làm tờ
    # giấy to nhỏ khác nhau (~2% trên dữ liệu thật). Lấy các cặp đã khớp, hồi
    # quy tuyến tính tâm-ô theo tâm-khung cho mỗi trục.
    pairs = []
    for slot_index, slot in enumerate(aligned):
        candidate = max(rel_rois, key=lambda r: overlap_ratio(r, slot))
        if overlap_ratio(candidate, slot) >= MIN_LAYOUT_OVERLAP:
            pairs.append((slots[slot_index], candidate))
    if len(pairs) < 2:
        return aligned

    def fit(axis):
        src = [_center(s)[axis] for s, _ in pairs]
        dst = [_center(r)[axis] for _, r in pairs]
        n = len(src)
        mean_s, mean_d = sum(src) / n, sum(dst) / n
        var = sum((v - mean_s) ** 2 for v in src)
        if var < 1e-9:
            return 1.0, mean_d - mean_s
        cov = sum((s - mean_s) * (d - mean_d) for s, d in zip(src, dst))
        scale = cov / var
        # Ảnh chụp cùng tờ giấy thì tỉ lệ phải gần 1; ra ngoài khoảng này nghĩa
        # là hồi quy bám vào cặp khớp sai, thà giữ tịnh tiến thuần.
        if not 0.9 <= scale <= 1.1:
            return 1.0, mean_d - mean_s
        return scale, mean_d - scale * mean_s

    sx, dx = fit(0)
    sy, dy = fit(1)
    if abs(dx) > MAX_LAYOUT_SHIFT or abs(dy) > MAX_LAYOUT_SHIFT:
        return aligned
    refined = _shift_slots(slots, sx, sy, dx, dy)
    return refined if _total_overlap(rel_rois, refined) >= best[0] else aligned


def match_rois_to_layout(rois, img_width, img_height, slots, min_overlap=MIN_LAYOUT_OVERLAP):
    """
    Ghép danh sách khung dò được trên MỘT trang với bố cục đã khai của trang đó.

    `slots` là list dict, mỗi cái có `cau_key` cùng `x`/`y`/`w`/`h` theo TỈ LỆ
    trang. Trả về:

        {
          "matched":   {cau_key: {"x","y","w","h","overlap"} (pixel của ảnh này)},
          "unmatched": [khung dò được nhưng không thuộc ô nào (pixel)],
          "missing":   [cau_key không tìm được khung nào],
        }

    Ghép tham lam theo độ chồng lấn giảm dần, mỗi khung và mỗi ô chỉ dùng một
    lần — nên hai ô sát nhau không thể cùng nhận một khung.

    `missing` phải được báo lên như "cần xem lại", KHÔNG được coi là học sinh
    bỏ trống: đó chính là kiểu nhầm lẫn đã khiến HS_16/HS_29 bị chấm 0 oan.
    """
    rel_rois = [to_relative(r, img_width, img_height) for r in rois]
    slots = fit_layout_to_page(rel_rois, slots)

    pairs = []
    for roi_index, rel in enumerate(rel_rois):
        for slot_index, slot in enumerate(slots):
            score = overlap_ratio(rel, slot)
            if score >= min_overlap:
                pairs.append((score, roi_index, slot_index))

    pairs.sort(key=lambda p: p[0], reverse=True)

    used_rois: set[int] = set()
    used_slots: set[int] = set()
    matched: dict = {}
    for score, roi_index, slot_index in pairs:
        if roi_index in used_rois or slot_index in used_slots:
            continue
        used_rois.add(roi_index)
        used_slots.add(slot_index)
        matched[slots[slot_index]["cau_key"]] = {**rois[roi_index], "overlap": round(score, 4)}

    return {
        "matched": matched,
        "unmatched": [r for i, r in enumerate(rois) if i not in used_rois],
        "missing": [s["cau_key"] for i, s in enumerate(slots) if i not in used_slots],
    }


def detect_page_rois(
    img,
    filename: str,
    slots=None,
    is_first_page: bool = False,
    skew_threshold: float = 2.0,
):
    """
    Bước dò ROI hoàn chỉnh cho MỘT trang của MỘT học sinh — gộp việc trước đây
    chia cho module1 (dò khung) và module2 (căn ảnh).

    Không warp ảnh nữa; thay vào đó dò khung ngay trên ảnh gốc rồi ghép với
    `slots` (bố cục theo tỉ lệ trang). Vẫn gọi `module2.check_image_skew` để
    cảnh báo ảnh chụp nghiêng: ảnh nghiêng nhiều thì khung dò ra cũng méo, và
    người chấm cần biết điều đó thay vì nhận một ảnh cắt xộc xệch không lời
    giải thích. Đây là CẢNH BÁO, không phải lỗi chặn — khác hẳn module2 cũ,
    nơi nghiêng quá ngưỡng là vứt cả trang.

    `slots=None` thì chỉ trả về danh sách khung thô (dùng cho màn khai bố cục).
    """
    # Nhập tại chỗ: module2 kéo theo nhánh align nặng, còn module1 vẫn phải
    # dùng được độc lập (CLI `--suggest-rois`, test) khi không cần tới nó.
    from ocr_modules.module2 import check_image_skew

    img_height, img_width = img.shape[:2]

    page = process_image(img, filename=filename, is_first_page=is_first_page)

    skew_ok, skew_angle = check_image_skew(img, skew_threshold=skew_threshold)
    page["skew"] = round(float(skew_angle), 2)
    page["skew_warning"] = (
        None if skew_ok else f"Ảnh chụp nghiêng {skew_angle:.1f}° — khung cắt có thể lệch."
    )

    if slots is None:
        return page

    page.update(match_rois_to_layout(page["rois"], img_width, img_height, slots))
    return page


def process_image(img, filename: str, is_first_page: bool = False):
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

    Không lọc khung theo nội dung — mọi khung bảng dò được (kể cả bảng đề
    bài) đều nằm trong "rois".

    `is_first_page=True` khi ảnh này là trang đầu tiên của một học sinh: sau
    khi sort, 2 ROI đầu tiên (khung "MÃ ĐỀ" + khung thông tin sinh viên) luôn
    bị bỏ — xem `drop_first_page_header_boxes`. Các trang sau của cùng học
    sinh không có 2 khung này nên gọi với `is_first_page=False` (mặc định).
    """
    img_height, img_width = img.shape[:2]

    # --- DÒ KHUNG BẢNG (KHÔNG LỌC) ---
    table_bboxes = extract_tables(img)
    padded_table_bboxes = pad_tables(table_bboxes, img_height, img_width)

    # --- GOM NHÓM & SẮP XẾP ---
    sorted_rois = map_and_sort_rois(padded_table_bboxes)

    # --- BỎ 2 KHUNG ĐẦU TRANG (MÃ ĐỀ + THÔNG TIN SV) NẾU LÀ TRANG ĐẦU ---
    if is_first_page:
        sorted_rois = drop_first_page_header_boxes(sorted_rois)

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
            "tables": len(rois),
        },
    }


# =====================================================================
# ===================  PHẦN CLI: chạy trên 1 ảnh path  ================
# =====================================================================

def draw_rois(img, rois, color=(0, 0, 255), thickness=2, show_index=True):
    """
    Vẽ các khung ROI lên một bản sao của ảnh gốc và trả về ảnh đã vẽ.
    Mỗi khung được đánh số theo thứ tự trong danh sách `rois` (thứ tự đọc:
    trên xuống, trái qua phải — đúng như map_and_sort_rois đã sắp).
    """
    vis = img.copy()
    for idx, r in enumerate(rois):
        x, y, w, h = r["x"], r["y"], r["w"], r["h"]
        cv2.rectangle(vis, (x, y), (x + w, y + h), color, thickness)
        if show_index:
            label = str(idx)
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
            cv2.rectangle(vis, (x, y - th - 8), (x + tw + 6, y), color, -1)
            cv2.putText(
                vis, label, (x + 3, y - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA,
            )
    return vis


def run_on_image_path(
    image_path: str,
    output_dir: str | None = None,
    is_first_page: bool = False,
    display: bool = True,
    save_preview: bool = True,
):
    """
    Chạy toàn bộ pipeline trên MỘT ảnh, từ path trên đĩa (vd: một path
    trong /kaggle/input/... hoặc /kaggle/working/...).

    - Đọc ảnh bằng cv2.imread (hỗ trợ path Unicode nếu cần, xem imread_unicode)
    - Chạy process_image -> lấy danh sách ROI
    - Ghi kết quả ra file JSON: <output_dir>/<tên_ảnh>.roi.json
    - Vẽ khung ROI lên ảnh, lưu ảnh preview: <output_dir>/<tên_ảnh>.roi.png
    - Nếu display=True: hiển thị ảnh preview bằng matplotlib (dùng tốt trong
      Kaggle/Jupyter notebook)

    Trả về (result_dict, output_json_path, output_preview_path).
    """
    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"Không tìm thấy ảnh: {image_path}")

    img = cv2.imread(image_path)
    if img is None:
        # cv2.imread trả None âm thầm nếu path chứa ký tự Unicode trên một số
        # hệ thống, hoặc nếu file không phải ảnh hợp lệ -> thử đọc lại bằng
        # np.fromfile + cv2.imdecode để chắc chắn hơn.
        data = np.fromfile(image_path, dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Không đọc được ảnh (file lỗi hoặc không phải ảnh): {image_path}")

    filename = os.path.basename(image_path)
    result = process_image(img, filename=filename, is_first_page=is_first_page)

    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(image_path))
    os.makedirs(output_dir, exist_ok=True)

    stem = os.path.splitext(filename)[0]
    json_path = os.path.join(output_dir, f"{stem}.roi.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    preview_path = None
    vis = draw_rois(img, result["rois"])

    if save_preview:
        preview_path = os.path.join(output_dir, f"{stem}.roi.png")
        cv2.imwrite(preview_path, vis)

    if display:
        try:
            import matplotlib.pyplot as plt
            vis_rgb = cv2.cvtColor(vis, cv2.COLOR_BGR2RGB)
            plt.figure(figsize=(10, 14))
            plt.imshow(vis_rgb)
            plt.axis("off")
            plt.title(f"{filename} — {result['stats']['tables']} ROI(s)")
            plt.show()
        except ImportError:
            print("matplotlib chưa được cài, bỏ qua bước hiển thị (đã lưu ảnh preview ra file).")

    print(f"[OK] {filename}: tìm thấy {result['stats']['tables']} ROI")
    print(f"  -> JSON:    {json_path}")
    if preview_path:
        print(f"  -> Preview: {preview_path}")

    return result, json_path, preview_path


def _build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Chạy Module 1 (ROI detection) trên một ảnh path, xuất file JSON và ảnh preview có vẽ khung ROI."
    )
    parser.add_argument("image_path", type=str, nargs="?", default=None,
                         help="Đường dẫn tới ảnh (vd: /kaggle/input/.../page1.png)")
    parser.add_argument(
        "--output-dir", type=str, default=None,
        help="Thư mục lưu file .roi.json và .roi.png (mặc định: cùng thư mục với ảnh gốc; "
             "trên Kaggle, input là read-only nên nên đặt vd --output-dir /kaggle/working)",
    )
    parser.add_argument(
        "--first-page", action="store_true",
        help="Đánh dấu ảnh này là trang đầu tiên của học sinh (sẽ bỏ 2 khung đầu: MÃ ĐỀ + thông tin SV)",
    )
    parser.add_argument("--no-display", action="store_true", help="Không hiển thị ảnh preview (chỉ lưu file)")
    parser.add_argument("--no-save-preview", action="store_true", help="Không lưu ảnh preview ra file")
    return parser


def main(argv=None):
    """
    Entry point cho CLI.

    Trên Jupyter/Colab/Kaggle notebook, khi file này được chạy qua `%run` hoặc
    `exec(open(...).read())`, IPython sẽ tự thêm các tham số riêng của kernel
    vào sys.argv (vd `-f /root/.local/share/jupyter/runtime/kernel-xxx.json`).
    argparse mặc định sẽ crash vì không nhận ra `-f`. Dùng parse_known_args()
    để bỏ qua các tham số lạ đó thay vì raise SystemExit.

    Nếu không có image_path hợp lệ nào được truyền vào (trường hợp thường gặp
    khi chạy trong notebook mà không set sys.argv thủ công), in hướng dẫn gọi
    trực tiếp run_on_image_path(...) thay vì cố chạy rồi lỗi khó hiểu.
    """
    if argv is None:
        import sys
        argv = sys.argv[1:]

    # Jupyter/Colab/Kaggle inject `-f <path-to-kernel-connection-file.json>`
    # into sys.argv. parse_known_args() alone isn't enough because the
    # connection-file path itself gets picked up as our positional
    # `image_path` (nargs='?' greedily takes the first bare token). Strip
    # `-f <value>` explicitly before parsing so it never reaches argparse.
    cleaned = []
    skip_next = False
    for tok in argv:
        if skip_next:
            skip_next = False
            continue
        if tok == "-f":
            skip_next = True
            continue
        cleaned.append(tok)

    parser = _build_arg_parser()
    args, unknown = parser.parse_known_args(cleaned)

    if args.image_path is None:
        print(
            "Không có image_path. Nếu đang chạy trong Jupyter/Colab/Kaggle notebook, "
            "gọi trực tiếp hàm thay vì chạy file này như một script:\n\n"
            "    from module1_roi_detection import run_on_image_path\n"
            "    run_on_image_path('/kaggle/input/.../page1.png', output_dir='/kaggle/working')\n"
        )
        return

    run_on_image_path(
        image_path=args.image_path,
        output_dir=args.output_dir,
        is_first_page=args.first_page,
        display=not args.no_display,
        save_preview=not args.no_save_preview,
    )


if __name__ == "__main__":
    main()
