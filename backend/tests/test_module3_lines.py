"""`normalize_lines` — Module 3 phải trả `lines` đúng kiểu đã khai.

Bài học từ phiên chấm thật `2383172375244d12aab871a88f1c5ff6`: model gói mỗi
dòng thành `{"text": "..."}` ở 3/205 dòng, `pipeline.py` lọc theo
`isinstance(l, str)` nên vứt sạch, và học sinh bị chấm "không làm bài" dù OCR
đã đọc được chữ. Giữ các case dưới đây khi sửa module3 — đặc biệt case thụt
lề, vì pipeline so khớp nguyên văn và không được phép cắt khoảng trắng.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ocr"))

from ocr_modules.module3 import normalize_lines  # noqa: E402


def test_giu_nguyen_chuoi_va_thut_le():
    content = {"lines": ["144", "    out = self.conv1(x)", ""]}
    assert normalize_lines(content)["lines"] == ["144", "    out = self.conv1(x)", ""]


def test_mo_hop_text():
    """Dạng đã gặp thật trên HS_25 câu 1 và HS_14 câu 3."""
    assert normalize_lines({"lines": [{"text": "144"}]})["lines"] == ["144"]


def test_khoa_dong_nghia_va_so():
    content = {"lines": [{"line": "a"}, {"content": "b"}, {"value": 3}, 7040]}
    assert normalize_lines(content)["lines"] == ["a", "b", "3", "7040"]


def test_bo_rac_nhung_giu_chu():
    content = {"lines": ["ok", None, [], {"khong_biet": 1}, "ok2"]}
    assert normalize_lines(content)["lines"] == ["ok", "ok2"]


def test_lines_khong_phai_list():
    assert normalize_lines({"lines": "144"})["lines"] == []


def test_khong_dung_toi_bang_va_loi():
    """Nhánh bảng dùng `table_extracted`, nhánh lỗi dùng `error` — phải nguyên vẹn."""
    table = {"table_extracted": [{"col_1": "a"}]}
    assert normalize_lines(table) == table
    err = {"error": "Lỗi Parse JSON"}
    assert normalize_lines(err) == err


def test_prompt_luot_2_rang_buoc_cau_truc():
    """Prompt lượt 2 của nhánh chữ phải cấm model tự bọc dòng thành object."""
    from ocr_modules.module3 import get_review_prompt

    prompt = get_review_prompt("code", "{}")
    assert '"lines": ["dòng 1", "dòng 2"]' in prompt
    assert "{\"text\": ...}" in prompt
