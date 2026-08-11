"""
Module 2 — Alignment & Crop.

Port 1:1 từ notebook gốc do người dùng cung cấp: mmlab-module2-alignment.ipynb
(cell 7 = verify_homography, cell 8 = check_image_skew,
 cell 9 = module_1_align_images).

Trước đây phần này bị viết lại thủ công bằng TypeScript thuần (tự cài đặt lại
ORB, RANSAC, warpPerspective...) trong src/lib/roi/orb.ts + homography.ts,
khiến kết quả sai lệch so với notebook gốc. File này thay thế hoàn toàn cách
tiếp cận đó: gọi đúng cv2.ORB_create, cv2.DescriptorMatcher (Hamming),
cv2.findHomography(cv2.RANSAC), cv2.warpPerspective — y hệt từng dòng trong
notebook — chỉ đổi input/output từ (đọc/ghi file trên disk theo folder) sang
(ảnh upload qua HTTP -> JSON response) để FastAPI serve được, giống cách
module1.py đã làm cho Module 1.

Các đoạn có đánh dấu "[GIỮ NGUYÊN THEO NOTEBOOK]" là copy gần như nguyên văn
công thức/tham số trong notebook — KHÔNG tự ý đổi số liệu (threshold, kernel
size, borderValue...) dù trông có vẻ "hợp lý hơn" theo cách khác, để đảm bảo
kết quả giống hệt bản gốc đã được người dùng thử nghiệm và tinh chỉnh.
"""

from typing import Optional

import cv2
import numpy as np


# ==========================================
# CELL 7: verify_homography — kiểm tra ma trận H có hợp lý không
# ==========================================
def verify_homography(H: Optional[np.ndarray], template_shape: tuple) -> tuple[bool, str]:
    if H is None:
        return False, "H_matrix is None"

    # [GIỮ NGUYÊN THEO NOTEBOOK] det chỉ tính trên block 2x2 góc trên-trái của H
    det = float(np.linalg.det(H[0:2, 0:2]))
    if det <= 0.05 or det >= 15.0:
        return False, f"Định thức H bất thường ({det:.2f}), ảnh bị bóp méo quá mức."

    # Chặn lỗi ma trận "ảo giác" làm méo giấy thành hình thoi
    h, w = template_shape[:2]
    pts_template = np.float32([[0, 0], [0, h - 1], [w - 1, h - 1], [w - 1, 0]]).reshape(-1, 1, 2)
    pts_student = cv2.perspectiveTransform(pts_template, H).reshape(-1, 2)

    p0, p1, _p2, p3 = pts_student[0], pts_student[1], pts_student[2], pts_student[3]
    v01 = p1 - p0  # cạnh trái
    v03 = p3 - p0  # cạnh trên

    def cosine_angle(vA, vB):
        norm_a, norm_b = np.linalg.norm(vA), np.linalg.norm(vB)
        if norm_a == 0 or norm_b == 0:
            return 1.0
        return float(np.dot(vA, vB) / (norm_a * norm_b))

    cos_theta = cosine_angle(v01, v03)

    # Nới lỏng ngưỡng: cho phép lệch đến ~11.5 độ (cos(78.5) ≈ 0.20).
    if abs(cos_theta) > 0.20:
        angle_deg = float(np.degrees(np.arccos(np.clip(cos_theta, -1.0, 1.0))))
        return False, f"Lỗi Skew Toán học: Ma trận làm biến dạng giấy quá lố ({angle_deg:.1f}°)."

    return True, "Hợp lệ"


# ==========================================
# CELL 8: check_image_skew — dò góc nghiêng bằng Text Block Contours
# ==========================================
def check_image_skew(aligned_img: np.ndarray, skew_threshold: float = 2.0) -> tuple[bool, float]:
    """
    Dò góc nghiêng bằng phương pháp Text Block Contours (đóng khối chữ).
    Bất chấp nét đứt, chữ viết tay loằng ngoằng và bỏ qua các đường gạch chéo.
    """
    gray = cv2.cvtColor(aligned_img, cv2.COLOR_BGR2GRAY)

    # 1. Binarize — adaptive threshold để bóc tách chữ khỏi nền giấy
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 21, 10
    )

    # 2. Bôi nhòe theo chiều ngang — kết dính chữ & nét đứt thành dải ruy-băng
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 3))
    dilated = cv2.dilate(thresh, kernel, iterations=1)

    # 3. Tìm khối hình học (chỉ contour ngoài — RETR_EXTERNAL, giống notebook)
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    angles: list[float] = []

    for cnt in contours:
        rect = cv2.minAreaRect(cnt)
        box = cv2.boxPoints(rect)

        p0, p1, p2, p3 = box
        edges = [(p0, p1), (p1, p2), (p2, p3), (p3, p0)]
        longest_edge = max(edges, key=lambda e: (e[0][0] - e[1][0]) ** 2 + (e[0][1] - e[1][1]) ** 2)

        dx = longest_edge[1][0] - longest_edge[0][0]
        dy = longest_edge[1][1] - longest_edge[0][1]

        length = float(np.sqrt(dx**2 + dy**2))
        if length < 100:
            continue

        angle = float(np.degrees(np.arctan2(dy, dx)))

        # Đưa góc về chuẩn [-90, 90]
        if angle > 90:
            angle -= 180
        elif angle < -90:
            angle += 180

        # Chỉ xét dải nằm ngang [-45, 45] — tự động bỏ qua gạch chéo đỏ của GV
        if -45 < angle < 45:
            angles.append(angle)

    # 4. Kiểm định an toàn — bỏ qua nếu trang giấy không có đủ chữ
    if len(angles) < 3:
        return True, 0.0

    median_angle = float(np.median(angles))

    if abs(median_angle) > skew_threshold:
        return False, abs(median_angle)

    return True, abs(median_angle)


# ==========================================
# CELL 9: module_1_align_images — pipeline align chính (ORB + RANSAC homography)
# ==========================================
def align_images(
    template_img: np.ndarray,
    student_img: np.ndarray,
    max_features: int = 5000,
    match_percent: float = 0.15,
) -> dict:
    """
    Căn chỉnh `student_img` về đúng khung của `template_img`.

    Port trực tiếp `module_1_align_images` trong notebook. Trả về dict thay
    vì tuple (aligned_img, error_info) như notebook, để thuận tiện serialize
    JSON qua FastAPI:

      {
        "image": np.ndarray (BGR, kích thước = template),
        "H": np.ndarray | None,
        "matches": int,     # số điểm khớp còn lại sau lọc match_percent
        "inliers": int,     # số điểm RANSAC coi là inlier (thêm cho UI, notebook gốc không dùng)
        "skew": float,
        "error": {"error_type": str, "reason": str} | None,
      }
    """
    gray_temp = cv2.cvtColor(template_img, cv2.COLOR_BGR2GRAY)
    gray_stud = cv2.cvtColor(student_img, cv2.COLOR_BGR2GRAY)

    orb = cv2.ORB_create(max_features)
    keypoints_temp, descriptors_temp = orb.detectAndCompute(gray_temp, None)
    keypoints_stud, descriptors_stud = orb.detectAndCompute(gray_stud, None)

    # [LỖI LỚP 1]: KHÔNG THỂ WARP
    if descriptors_temp is None or descriptors_stud is None:
        return {
            "image": student_img,
            "H": None,
            "matches": 0,
            "inliers": 0,
            "skew": 0.0,
            "error": {"error_type": "FEATURE_ERROR", "reason": "Ảnh quá mờ hoặc trống."},
        }

    matcher = cv2.DescriptorMatcher_create(cv2.DESCRIPTOR_MATCHER_BRUTEFORCE_HAMMING)
    matches = list(matcher.match(descriptors_stud, descriptors_temp))
    matches = sorted(matches, key=lambda x: x.distance)

    num_good_matches = int(len(matches) * match_percent)
    matches = matches[:num_good_matches]

    # [LỖI LỚP 2]: KHÔNG THỂ WARP
    if len(matches) < 10:
        return {
            "image": student_img,
            "H": None,
            "matches": len(matches),
            "inliers": 0,
            "skew": 0.0,
            "error": {"error_type": "MATCH_ERROR", "reason": f"Quá ít điểm khớp ({len(matches)})."},
        }

    points_stud = np.zeros((len(matches), 2), dtype=np.float32)
    points_temp = np.zeros((len(matches), 2), dtype=np.float32)
    for i, match in enumerate(matches):
        points_stud[i, :] = keypoints_stud[match.queryIdx].pt
        points_temp[i, :] = keypoints_temp[match.trainIdx].pt

    # [GIỮ NGUYÊN THEO NOTEBOOK] không truyền reprojThreshold -> dùng mặc định
    # của OpenCV (đúng bằng 3.0), giống hệt hành vi notebook.
    h_matrix, mask = cv2.findHomography(points_stud, points_temp, cv2.RANSAC)

    # [LỖI LỚP 3]: KHÔNG THỂ WARP
    if h_matrix is None:
        return {
            "image": student_img,
            "H": None,
            "matches": len(matches),
            "inliers": 0,
            "skew": 0.0,
            "error": {"error_type": "HOMOGRAPHY_ERROR", "reason": "Không thể tính toán ma trận."},
        }

    inliers = int(mask.sum()) if mask is not None else 0

    # Đã có ma trận là ép warp luôn, dù ma trận tốt hay xấu (giống notebook)
    h, w = template_img.shape[:2]
    aligned_img = cv2.warpPerspective(student_img, h_matrix, (w, h), borderValue=(255, 255, 255))

    base = {"image": aligned_img, "H": h_matrix, "matches": len(matches), "inliers": inliers}

    # [LỖI LỚP 4]: TRẢ VỀ ẢNH WARP KÌ DỊ
    is_valid, reason = verify_homography(h_matrix, template_img.shape)
    if not is_valid:
        return {**base, "skew": 0.0, "error": {"error_type": "GEOMETRY_WARP_ERROR", "reason": reason}}

    # [LỖI LỚP 5]: TRẢ VỀ ẢNH WARP BỊ NGHIÊNG DÒNG KẺ
    is_hough_safe, actual_skew = check_image_skew(aligned_img, skew_threshold=1.5)
    if not is_hough_safe:
        return {
            **base,
            "skew": actual_skew,
            "error": {
                "error_type": "HOUGH_SKEW_ERROR",
                "reason": f"Dòng kẻ thực tế bị xiên {actual_skew:.1f}°.",
            },
        }

    # THÀNH CÔNG
    return {**base, "skew": actual_skew, "error": None}


def encode_png(img_bgr: np.ndarray) -> Optional[bytes]:
    ok, buf = cv2.imencode(".png", img_bgr)
    if not ok:
        return None
    return buf.tobytes()
