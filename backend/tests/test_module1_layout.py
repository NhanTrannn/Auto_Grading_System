"""Module 1 — dò ROI trên chính bài của học sinh, không align về tờ mẫu nữa.

Các ca dưới đây đều lấy từ dữ liệu chấm thật (3 mã đề, 19 học sinh, 171 ô).
Giữ chúng khi sửa module1: mỗi ca là một kiểu hỏng đã thực sự xảy ra, và cả
ba kiểu đều hỏng ÂM THẦM — bài vẫn ra điểm, chỉ là điểm của khung khác.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ocr"))

from ocr_modules.module1 import (  # noqa: E402
    fit_layout_to_page,
    match_rois_to_layout,
    overlap_ratio,
    pad_tables,
    to_relative,
)

PAGE_W, PAGE_H = 2200, 3260


def _slot(cau_key, y, h, x=0.11, w=0.80):
    return {"cau_key": cau_key, "x": x, "y": y, "w": w, "h": h}


def _px(rel):
    """Ô theo tỉ lệ -> khung pixel, để nạp vào match_rois_to_layout."""
    return {
        "x": round(rel["x"] * PAGE_W),
        "y": round(rel["y"] * PAGE_H),
        "w": round(rel["w"] * PAGE_W),
        "h": round(rel["h"] * PAGE_H),
    }


# Bố cục trang 2 mã đề 76, đo từ tờ thật.
LAYOUT = [
    _slot("Cau_06", 0.071, 0.160),
    _slot("Cau_07", 0.233, 0.160),
    _slot("Cau_08", 0.396, 0.227),
    _slot("Cau_09", 0.626, 0.160),
]


def test_khong_noi_xuong_duoi():
    """Nới đáy 82px nuốt trọn dòng in 'Question 7:' trong khe 89px giữa hai khung."""
    box = {"x": 300, "y": 1000, "w": 1600, "h": 500}
    out = pad_tables([box], PAGE_H, PAGE_W)[0]
    assert out["y"] == 1000
    assert out["y"] + out["h"] == 1500, "đáy phải đúng bằng đáy khung dò được"
    assert out["x"] < 300 and out["x"] + out["w"] > 1900, "chiều ngang vẫn nới hai bên"


def test_dai_mep_giay_khong_chiem_o_nao():
    """HS_24: dải x=1947 w=157 cao suốt trang, chen vào giữa danh sách đã sort."""
    sliver = {"x": 1947, "y": 0, "w": 157, "h": PAGE_H}
    for slot in LAYOUT:
        assert overlap_ratio(to_relative(sliver, PAGE_W, PAGE_H), slot) < 0.1


def test_bo_khung_thua_va_van_ghep_du():
    """Khung thừa bị loại, 4 ô thật vẫn về đúng chỗ — không bị đẩy lệch một nấc."""
    rois = [_px(s) for s in LAYOUT]
    rois.insert(3, {"x": 1947, "y": 0, "w": 157, "h": PAGE_H})

    out = match_rois_to_layout(rois, PAGE_W, PAGE_H, LAYOUT)

    assert set(out["matched"]) == {"Cau_06", "Cau_07", "Cau_08", "Cau_09"}
    assert out["missing"] == []
    assert len(out["unmatched"]) == 1
    assert out["unmatched"][0]["w"] == 157
    assert out["matched"]["Cau_09"]["y"] == _px(LAYOUT[3])["y"]


def test_anh_chup_lech_khung_van_ghep_dung():
    """HS_21/HS_31 lệch xuống 0.04 trang — hơn một thân khung câu 1 (0.031)."""
    shifted = [_px({**s, "y": s["y"] + 0.04}) for s in LAYOUT]
    out = match_rois_to_layout(shifted, PAGE_W, PAGE_H, LAYOUT)
    assert out["missing"] == []
    assert set(out["matched"]) == {"Cau_06", "Cau_07", "Cau_08", "Cau_09"}


def test_anh_chup_gan_xa_khac_nhau():
    """Chụp gần/xa làm tờ giấy to nhỏ ~2%; canh phải bù được cả co giãn."""
    scaled = [_px({**s, "y": s["y"] * 0.97 + 0.02, "h": s["h"] * 0.97}) for s in LAYOUT]
    out = match_rois_to_layout(scaled, PAGE_W, PAGE_H, LAYOUT)
    assert out["missing"] == []


def test_thieu_khung_thi_bao_thieu_chu_khong_ghep_bua():
    """Ô không có khung phải vào `missing` — đây là ca HS_16/HS_29 mất trang 2.

    Báo thiếu để hiện 'cần xem lại'; coi là học sinh bỏ trống chính là lỗi cũ.
    """
    rois = [_px(s) for s in LAYOUT if s["cau_key"] != "Cau_08"]
    out = match_rois_to_layout(rois, PAGE_W, PAGE_H, LAYOUT)
    assert out["missing"] == ["Cau_08"]
    assert "Cau_08" not in out["matched"]
    assert set(out["matched"]) == {"Cau_06", "Cau_07", "Cau_09"}


def test_hai_o_khong_cung_nhan_mot_khung():
    """Ghép tham lam: mỗi khung chỉ thuộc về một ô."""
    rois = [_px(LAYOUT[0])]
    out = match_rois_to_layout(rois, PAGE_W, PAGE_H, LAYOUT)
    assert len(out["matched"]) == 1
    assert sorted(out["missing"]) == ["Cau_07", "Cau_08", "Cau_09"]


def test_it_khung_khong_lam_truot_bo_cuc_sang_o_ben():
    """Ca nguy hiểm nhất: một khung duy nhất kéo cả bố cục lệch một nấc.

    Không chặn biên độ thì phép canh sẽ trượt bố cục cho tới khi khung đó rơi
    vào Cau_07, và cả trang vẫn ra điểm — chỉ là điểm của câu khác. Ô cách nhau
    0.16 trang, lệch do khung ảnh thật chỉ 0.04, nên MAX_LAYOUT_SHIFT chặn giữa.
    """
    only_cau_06 = [_px(LAYOUT[0])]
    out = match_rois_to_layout(only_cau_06, PAGE_W, PAGE_H, LAYOUT)
    assert list(out["matched"]) == ["Cau_06"], "khung câu 6 không được gán sang câu khác"

    only_cau_08 = [_px(LAYOUT[2])]
    out = match_rois_to_layout(only_cau_08, PAGE_W, PAGE_H, LAYOUT)
    assert list(out["matched"]) == ["Cau_08"]


def test_khong_co_khung_nao_thi_thieu_het():
    out = match_rois_to_layout([], PAGE_W, PAGE_H, LAYOUT)
    assert out["matched"] == {}
    assert len(out["missing"]) == len(LAYOUT)


def test_fit_khong_lam_hong_truong_hop_da_khop():
    """Trang đã trùng khít thì phép canh không được đẩy nó đi đâu cả."""
    rel = [to_relative(_px(s), PAGE_W, PAGE_H) for s in LAYOUT]
    fitted = fit_layout_to_page(rel, LAYOUT)
    for before, after in zip(LAYOUT, fitted):
        assert abs(before["y"] - after["y"]) < 0.01
