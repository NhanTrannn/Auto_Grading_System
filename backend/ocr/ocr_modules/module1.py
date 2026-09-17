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
    """
    padded_table_bboxes = []

    for box in table_bboxes:
        x, y, w, h = box["x"], box["y"], box["w"], box["h"]

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
