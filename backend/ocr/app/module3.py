"""
Module 3 — Handwriting OCR.

Prompt/JSON-repair logic port 1:1 từ 3 notebook gốc (đối chiếu trực tiếp,
không có sai lệch về logic):
- qwenver15update-shorttext.ipynb  (task_type: short_text)
- ocr-longtext.ipynb               (task_type: long_text)
- qwenver15update-table.ipynb      (task_type: table)
- task_type "code" lấy đúng theo prompt đã có sẵn trong get_ocr_prompt() của
  cả 3 notebook trên (nội dung giống hệt nhau ở cả 3 file).

**Khác bản vendor gốc**: bản gốc chạy Qwen3-VL-8B-Instruct local (4-bit qua
transformers/bitsandbytes, cần GPU/CUDA). File này gọi thẳng Qwen3-VL-32B
qua API (OpenAI-compatible chat completions, vd OpenRouter) thay vì load
model in-process — xem `_call_qwen_vl()`. Không còn cần GPU/CUDA/torch/
transformers/bitsandbytes/qwen_vl_utils cho module này nữa, chỉ cần
`LLM_API_KEY`/`LLM_MODEL_API`/`LLM_MODEL_NAME` trong `.env` (cùng file `.env`
mà `backend/pipeline.py` đã dùng).
"""

from __future__ import annotations

import ast
import asyncio
import base64
import json
import re
from typing import Any, Optional

TaskType = str  # "short_text" | "long_text" | "code" | "table"

# ---------------------------------------------------------------------------
# Prompt builders — port 1:1 từ get_ocr_prompt() trong notebook.
# ---------------------------------------------------------------------------

_SHORT_TEXT = """[VAI TRÒ] OCR chữ viết tay môn lập trình C++ của học sinh Việt Nam.
[NHIỆM VỤ] Chỉ lấy chữ VIẾT TAY đè lên dòng chấm/gạch (".....", "____").
[LOẠI TRỪ]
- Chữ in sẵn đề bài, kể cả khi nằm ngay sát hoặc liền trước dòng chấm (vd "Đáp số:", "a =", "là:")
- Mực đỏ, dấu chấm/gạch nền ('......', '_____')
- Chữ đã bị gạch xóa/bôi đen (dù đọc được, vẫn bỏ qua hoàn toàn)
[TRỐNG] Nếu ô này không có chữ viết tay nào, trả về mảng rỗng: {"lines": []}
[VÍ DỤ]
"Kết quả là: .......15....." → chỉ lấy "15" (không lẫn chữ in, không sót dấu chấm)
Viết "12" gạch xóa, viết lại "15" → chỉ lấy "15"
"Kết quả là: .............." → trả về mảng rỗng: {"lines": []}
[KIỂM TRA] Trước khi xuất, rà lại: đúng là chữ tay (không phải chữ in/bị gạch), đã sạch dấu chấm/gạch chưa, đủ số dòng theo đúng thứ tự chưa.
[ĐỊNH DẠNG ĐẦU RA]
CHỈ trả về một đối tượng JSON thô khớp với cấu trúc sau:
{
  "lines": [
    "dòng chữ viết tay thứ nhất (đã dọn sạch dấu chấm nền)",
    "dòng chữ viết tay thứ hai (đã dọn sạch dấu chấm nền)"
  ]
}""".strip()

_LONG_TEXT = """[VAI TRÒ] OCR chữ viết tay môn lập trình C++ của học sinh Việt Nam.
[NHIỆM VỤ] Chỉ lấy chữ VIẾT TAY đè lên dòng chấm/gạch (".....", "__"). OCR HẾT TẤT CẢ các chữ viết tay có trong vùng làm bài, KHÔNG BỎ SÓT bất cứ chữ nào (trừ các trường hợp bị gạch bỏ ở phần LOẠI TRỪ). Tuyệt đối KHÔNG tự động bổ sung, chỉnh sửa, thêm thắt bất cứ gì, chỉ lấy ra chính xác những chữ viết tay có trong ảnh. Đặc biệt: Nếu chữ bị gạch ngang/gạch đè bởi nét MỰC ĐỎ (do giáo viên chấm bài), tự động lờ đi nét mực đỏ và VẪN TRÍCH XUẤT chữ viết tay bên dưới.
[LOẠI TRỪ]
- Chữ in sẵn đề bài.
- Mực đỏ (điểm số, chữ ký, nét chấm bài), dấu chấm/gạch nền.
- Chữ do học sinh TỰ gạch xóa, gạch chéo, gạch rối hoặc bôi đen bằng mực thường (dù vẫn đọc được, bắt buộc bỏ qua hoàn toàn).
[NGÔN NGỮ HỖN HỢP] Bài làm có cả tiếng Anh (từ khóa C++, tên biến, hàm: int, cout,...) và tiếng Việt (giải thích, chú thích). Đọc CHÍNH XÁC từng từ theo đúng ngôn ngữ gốc. Nếu học sinh viết tiếng Việt có dấu, BẮT BUỘC giữ nguyên dấu, không tự ý lược bỏ hay sửa lỗi chính tả.
[TRỐNG] Nếu ô không có chữ viết tay, trả về {"lines": []}
[VÍ DỤ]
- Chữ bị giáo viên gạch đỏ: Học sinh viết "nguoi = 3" và bị gạch ngang bằng nét mực đỏ → lờ đi nét đỏ, VẪN LẤY "nguoi = 3".
- Chữ bị học sinh gạch xóa: Viết "Input : nhập đầu 6 dau = 6", trong đó "nhập đầu 6" bị gạch đè bằng mực xanh/đen → CHỈ LẤY "Input : dau = 6".
- Gạch xóa nhiều lần trên một dòng: Viết "Người 3 nguoi = 3", trong đó "Người 3" bị học sinh gạch chéo đè lên → CHỈ LẤY "nguoi = 3".
- Giữ nhãn do học sinh tự viết: Ảnh có chữ tay "* Biến : int dau, chan ;" → PHẢI LẤY đầy đủ "* Biến : int dau, chan ;".
- Bỏ chữ in sẵn & mực đỏ: Có dòng in sẵn "a. Đặt tên..." và nét gạch đỏ chấm bài đè lên chữ tay "Out Put : nguoi = 3" → BỎ chữ in sẵn và nét đỏ, CHỈ LẤY "Out Put : nguoi = 3".
[KIỂM TRA] Trước khi xuất: đúng chữ tay (không phải chữ in/bị học sinh tự gạch xóa), KHÔNG BỎ SÓT CHỮ NÀO, BẮT BUỘC lấy cả những chữ bị gạch mực đỏ, sạch dấu nền, giữ đúng tiếng Việt có dấu, không tự động bổ sung hay chỉnh sửa, đủ số dòng đúng thứ tự.
[ĐỊNH DẠNG ĐẦU RA] CHỈ trả về JSON thô:
{
  "lines": [
    "dòng chữ viết tay thứ nhất",
    "dòng chữ viết tay thứ hai"
  ]
}""".strip()

_CODE = """[VAI TRÒ] OCR mã nguồn C++ viết tay của học sinh Việt Nam.
[NHIỆM VỤ] Trích xuất chính xác từng dòng code viết tay, giữ nguyên y hệt bản gốc.
[LOẠI TRỪ]
- Chữ in sẵn của đề thi, bất kể màu mực
- Mực đỏ (chấm điểm)
- Đoạn code đã bị gạch bỏ/bôi đen (dù đọc được, vẫn bỏ qua hoàn toàn)
[GIỮ NGUYÊN - KHÔNG TỰ SỬA]
- Không sửa lỗi cú pháp, lỗi chính tả, không tự thêm dấu chấm phẩy còn thiếu
- Không xóa dấu chấm là toán tử hợp lệ của C++ (vd: "a[i].DTB", "cin.ignore()") — chỉ xóa dấu chấm là ký tự đệm nền, không phải chấm toán tử
- Giữ nguyên comment Tiếng Việt của học sinh, kể cả viết sai chính tả
[THỨ TỰ ĐỌC] Học sinh thường viết thành 2 cột trên cùng 1 dải hàng ngang. Đọc đúng thứ tự logic của chương trình:
theo từng hàm/khối lệnh từ trên xuống dưới, trong mỗi hàng đọc từ trái sang phải theo đúng cột —
KHÔNG đọc lẫn lộn giữa 2 cột hoặc đảo thứ tự dòng.
[TRỐNG] Nếu không có code viết tay hợp lệ, trả về mảng rỗng: {"lines": []}
[KIỂM TRA] Trước khi xuất, rà lại: đúng là code viết tay (không phải chữ in/bị gạch), chưa tự sửa cú pháp, đúng thứ tự đọc theo logic chương trình chưa.
[ĐỊNH DẠNG ĐẦU RA]
CHỈ trả về một đối tượng JSON thô khớp với cấu trúc sau:
{
  "lines": [
    "dòng code 1 y hệt bản gốc",
    "dòng code 2 y hệt bản gốc"
  ]
}""".strip()


def build_table_skeleton(n_rows: int, n_cols: int) -> dict:
    return {
        "table_extracted": [
            {f"col_{c}": "" for c in range(1, n_cols + 1)} for _ in range(n_rows)
        ]
    }


def _table_prompt(n_rows: int, n_cols: int, skeleton_content: Optional[dict]) -> str:
    if not isinstance(n_rows, int) or not isinstance(n_cols, int) or n_rows <= 0 or n_cols <= 0:
        raise ValueError(
            f"task_type='table' yêu cầu n_rows và n_cols là số nguyên dương hợp lệ "
            f"(nhận được n_rows={n_rows}, n_cols={n_cols})."
        )

    col_keys = [f"col_{c}" for c in range(1, n_cols + 1)]
    example_row_full = "{" + ", ".join(f'"{k}": "..."' for k in col_keys) + "}"
    example_row_empty = "{" + ", ".join(f'"{k}": ""' for k in col_keys) + "}"

    if n_cols >= 2:
        partial_example_parts = []
        for idx, k in enumerate(col_keys):
            if idx == 0:
                partial_example_parts.append(f'"{k}": "12"')
            elif idx == 1:
                partial_example_parts.append(f'"{k}": ""')
            else:
                partial_example_parts.append(f'"{k}": "7"' if idx == 2 else f'"{k}": ""')
        example_row_partial = "{" + ", ".join(partial_example_parts) + "}"
        partial_example_line = f"Hàng có {n_cols} cột, cột thứ 2 chưa điền → {example_row_partial}\n            "
    else:
        partial_example_line = ""

    skeleton_block = ""
    if skeleton_content:
        skeleton_json_str = json.dumps(skeleton_content, ensure_ascii=False)
        skeleton_block = f"""
            Đây là khung cấu trúc bảng đã xác định trước (rỗng, cần bạn điền vào):
            {skeleton_json_str}
            Hãy giữ NGUYÊN cấu trúc này (đúng {n_rows} hàng, đúng các khóa col_1...col_{n_cols} trong mỗi hàng), chỉ thay giá trị rỗng "" bằng nội dung đọc được từ ảnh theo đúng quy tắc bên dưới.
            """

    return f"""OCR chữ viết tay môn C++ trong bảng. Bảng có phần TIÊU ĐỀ (in sẵn) và phần DỮ LIỆU (viết tay).
Vùng DỮ LIỆU có ĐÚNG {n_rows} hàng và ĐÚNG {n_cols} cột (không tính hàng/cột tiêu đề). Không tự đếm lại.
{skeleton_block}
Các bước:
1. Loại bỏ hoàn toàn vùng TIÊU ĐỀ (chữ in sẵn: tên cột, STT, "Đáp số:", "a ="...) khỏi kết quả.
2. Dựa vào đường kẻ/khung thực tế, định vị đúng {n_rows} hàng x {n_cols} cột trong vùng DỮ LIỆU. Quét trái→phải, trên→dưới.
3. Ở mỗi ô: bỏ qua vệt đỏ và chữ đã gạch xóa/bôi đen.
4. Sau khi bỏ (3), nếu ô không còn nét viết tay thật → gán "" (vẫn giữ đúng vị trí cột). Nếu còn → đọc nội dung, giữ nguyên ký hiệu (/, -, .) nếu là nét học sinh viết.
5. Gán vào đúng khóa "col_1"..."col_{n_cols}" theo thứ tự trái→phải (không dùng tên tiêu đề thật). Mỗi hàng phải đủ {n_cols} khóa, không gộp/bỏ sót cột nào.

QUY TẮC RANH GIỚI CỘT:
Nhiều cụm số/chữ cách xa nhau trong CÙNG một ô (do viết lệch tâm, chữ to, ô dư chỗ) → vẫn là MỘT giá trị col_n duy nhất, nối cách nhau bằng dấu cách. TUYỆT ĐỐI không tách cột chỉ vì khoảng trắng lớn — chỉ tách khi có đường kẻ dọc thật sự cắt giữa 2 cụm. Nếu số giá trị trong 1 hàng > {n_cols} → đã tách nhầm, phải gộp lại cho đúng {n_cols}.

LƯU Ý: "/" và "7" dễ nhầm "1" — "/" là nét dài xen giữa 2 cụm số (hay gặp ở ngày/tháng); "7" có nét ngang trên đỉnh rồi chéo xuống, đôi khi có gạch ngang ngắn giữa thân.

Ví dụ: "12" gạch xóa viết lại "15"→"15" | "12" có vệt đỏ, số còn→"12" | "12 14 16" gạch 12,14→"16" | Chỉ nhãn in+vệt đỏ→"" | "6" và "18" cách xa, không kẻ giữa→"6 18" | {partial_example_line}Cả hàng gạch xóa→{example_row_empty}

CHỈ trả JSON, đúng {n_rows} hàng, mỗi hàng đúng {n_cols} khóa:
{{
  "table_extracted": [
    {example_row_full},
    {example_row_full}
  ]
}}""".strip()


def get_ocr_prompt(
    task_type: TaskType,
    n_rows: Optional[int] = None,
    n_cols: Optional[int] = None,
    skeleton_content: Optional[dict] = None,
) -> str:
    if task_type == "short_text":
        return _SHORT_TEXT
    if task_type == "long_text":
        return _LONG_TEXT
    if task_type == "code":
        return _CODE
    if task_type == "table":
        return _table_prompt(n_rows, n_cols, skeleton_content)
    raise ValueError(f"task_type không hợp lệ: '{task_type}'")


def get_review_prompt(
    task_type: TaskType,
    pass1_str: str,
    n_rows: Optional[int] = None,
    n_cols: Optional[int] = None,
) -> str:
    """Pass 2 — prompt review/reflection. Port 1:1 từ notebook."""
    if task_type == "table":
        return (
            f"Nhiệm vụ DUY NHẤT của bạn: xóa các ký tự bị gạch xóa khỏi JSON OCR dưới đây, không làm gì khác.\n\n"
            f"Bảng có ĐÚNG {n_rows} hàng, ĐÚNG {n_cols} cột (col_1 đến col_{n_cols}) — không được thay đổi.\n\n"
            f"JSON gốc:\n\n{pass1_str}\n\n"
            f"Cách làm: nhìn lại ảnh, đối chiếu từng giá trị. Nếu phần nào bị nét gạch/bôi đen đè lên (thực sự bị hủy bỏ), "
            f"xóa đúng phần đó khỏi value. Nếu cả ô bị gạch xóa, đặt value = \"\".\n\n"
            f"Ràng buộc bắt buộc:\n"
            f"1. CHỈ ĐƯỢC XÓA — không thêm, không sửa chính tả, không sửa lỗi đọc sai. Giữ nguyên 100% các ký tự "
            f"không liên quan đến gạch xóa, kể cả khi bạn thấy nó không khớp ảnh.\n"
            f"2. Vệt mực đỏ, gạch chân, chữ đậm/lem mực KHÔNG phải gạch xóa — không đụng vào.\n"
            f"3. Không chắc là gạch xóa → giữ nguyên, không xóa.\n"
            f"4. Không có gì bị gạch xóa → trả nguyên JSON gốc, không đổi gì.\n"
            f"5. Giữ nguyên cấu trúc JSON, chỉ được sửa value.\n\n"
            f"Chỉ trả về 1 block JSON, không giải thích."
        )

    return (
        f"Bạn là một chuyên gia đối chiếu và làm sạch dữ liệu OCR.\n"
        f"Đây là kết quả trích xuất JSON ban đầu từ hình ảnh:\n\n"
        f"{pass1_str}\n\n"
        f"Nhiệm vụ: Hãy nhìn kỹ lại hình ảnh một lần nữa và đối chiếu với JSON trên. Hãy LÀM SẠCH KẾT QUẢ theo các quy tắc khắt khe sau:\n"
        f"1. CHỈ GIỮ LẠI CHỮ VIẾT TAY: Xóa bỏ hoàn toàn các phần chữ in của đề bài. Tuyệt đối không đưa các nhãn có sẵn như 'a =', 'là:','Câu' vào JSON.\n"
        f"2. DỌN RÁC: Xóa sạch các ký tự đệm dưới chữ (ví dụ: '.....', '_____').\n"
        f"3. SỬA LỖI: Nếu phần chữ viết tay bị nhận diện sai (chính tả, đọc nhầm số/chữ), hãy sửa lại cho chính xác tuyệt đối với hình ảnh.\n"
        f"4. CHỐT KẾT QUẢ: Nếu JSON đã sạch (chỉ chứa nội dung học sinh tự điền, hoặc rỗng hợp lệ) và chính xác, hãy giữ nguyên.\n"
        f"Yêu cầu bắt buộc: CHỈ trả về đúng 1 block mã JSON, không kèm bất kỳ văn bản giải thích nào khác."
    )


# ---------------------------------------------------------------------------
# extract_and_repair_json / validate_table_structure — port 1:1 từ notebook
# (bao gồm cả bước fallback ast.literal_eval mà bản TS trước đây thiếu).
# ---------------------------------------------------------------------------

def extract_and_repair_json(raw_text: str) -> Optional[dict]:
    clean_text = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL)
    clean_text = re.sub(r"```json\s*", "", clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r"```\s*", "", clean_text)
    clean_text = clean_text.strip()

    json_match = re.search(r"\{.*\}", clean_text, flags=re.DOTALL)
    if not json_match:
        return None
    json_str = json_match.group(0)

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    json_str_fixed = re.sub(r",\s*([\]}])", r"\1", json_str)
    try:
        return json.loads(json_str_fixed)
    except json.JSONDecodeError:
        pass

    open_braces = json_str_fixed.count("{")
    close_braces = json_str_fixed.count("}")
    open_brackets = json_str_fixed.count("[")
    close_brackets = json_str_fixed.count("]")
    if open_brackets > close_brackets:
        json_str_fixed += "]" * (open_brackets - close_brackets)
    if open_braces > close_braces:
        json_str_fixed += "}" * (open_braces - close_braces)

    try:
        return json.loads(json_str_fixed)
    except json.JSONDecodeError:
        pass

    try:
        py_str = json_str_fixed.replace("true", "True").replace("false", "False").replace("null", "None")
        parsed_dict = ast.literal_eval(py_str)
        if isinstance(parsed_dict, dict):
            return parsed_dict
    except Exception:
        pass

    return None


def validate_table_structure(parsed: Any, n_rows: int, n_cols: int) -> tuple[bool, Optional[str]]:
    if not isinstance(parsed, dict) or "table_extracted" not in parsed:
        return False, "Thiếu khóa 'table_extracted'"
    rows = parsed["table_extracted"]
    if not isinstance(rows, list):
        return False, "'table_extracted' không phải là list"
    if len(rows) != n_rows:
        return False, f"Sai số hàng: kỳ vọng {n_rows}, nhận được {len(rows)}"
    expected = sorted(f"col_{c}" for c in range(1, n_cols + 1))
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            return False, f"Hàng {i} không phải dict"
        keys = sorted(row.keys())
        if keys != expected:
            return False, f"Hàng {i} sai khóa cột: kỳ vọng {', '.join(expected)}, nhận {', '.join(keys)}"
    return True, None


# ---------------------------------------------------------------------------
# Gọi Qwen3-VL qua API (OpenAI-compatible chat completions, vd OpenRouter) —
# THAY cho load model local bằng transformers/bitsandbytes ở bản gốc. Đọc
# cùng `.env` mà `backend/pipeline.py` dùng (`LLM_API_KEY`/`LLM_MODEL_API`/
# `LLM_MODEL_NAME`) qua python-dotenv's load_dotenv() tìm ngược lên trên, nên
# chỉ cần 1 `.env` ở gốc repo cho cả 2 phần — theo CLAUDE.md, LLM_MODEL_NAME ở
# đó vốn đã là "qwen/qwen3-vl-32b-instruct". Không còn cần GPU/CUDA/torch/
# transformers/bitsandbytes/qwen_vl_utils cho module này nữa.
# ---------------------------------------------------------------------------

import os

import requests
from dotenv import load_dotenv

load_dotenv()

LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL_API = os.environ.get("LLM_MODEL_API", "")
LLM_MODEL_NAME = os.environ.get("LLM_MODEL_NAME", "")


class LLMConfigError(RuntimeError):
    """LLM_API_KEY/LLM_MODEL_API/LLM_MODEL_NAME thiếu hoặc rỗng trong .env."""


def is_configured() -> bool:
    return bool(LLM_API_KEY and LLM_MODEL_API and LLM_MODEL_NAME)


def _call_qwen_vl(image_bytes: bytes, prompt: str, temperature: float, max_tokens: int = 1500) -> str:
    """1 lượt gọi API — ảnh + prompt text, trả về raw text từ model (chưa parse JSON)."""
    if not is_configured():
        raise LLMConfigError(
            "Module 3 chưa được cấu hình — thiếu LLM_API_KEY/LLM_MODEL_API/LLM_MODEL_NAME trong .env."
        )

    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    headers = {"Content-Type": "application/json"}
    if LLM_API_KEY:
        headers["Authorization"] = f"Bearer {LLM_API_KEY}"

    resp = requests.post(
        LLM_MODEL_API,
        headers=headers,
        json={
            "model": LLM_MODEL_NAME,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_image}"}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=180,
    )
    resp.raise_for_status()
    data = resp.json()
    return (data.get("choices", [{}])[0].get("message", {}).get("content", "") or "").strip()


# ---------------------------------------------------------------------------
# Suy luận 2-pass (self-reflection) cho 1 ảnh — port của run_qwen_inference(),
# rút gọn về batch_size=1 (mỗi request FastAPI xử lý đúng 1 ảnh crop). Mỗi
# pass giờ là 1 lượt gọi API thay vì model.generate() local; chạy trong
# asyncio.to_thread() vì `requests` là blocking I/O.
# ---------------------------------------------------------------------------

async def run_ocr_single(
    image_bytes: bytes,
    task_type: TaskType,
    n_rows: Optional[int] = None,
    n_cols: Optional[int] = None,
    temperature: float = 0.2,
) -> dict:
    """
    Chạy OCR 2-pass (Pass 1 trích xuất + Pass 2 self-reflection) cho 1 ảnh crop.
    Trả về dict khớp shape frontend đang dùng (xem src/routes/module-3.tsx):
    { status, confidence, pass1_content, content, structure_warning }
    """
    if task_type == "table" and (not isinstance(n_rows, int) or not isinstance(n_cols, int) or n_rows <= 0 or n_cols <= 0):
        raise ValueError(
            f"task_type='table' yêu cầu n_rows và n_cols là số nguyên dương hợp lệ "
            f"(nhận được n_rows={n_rows}, n_cols={n_cols})."
        )

    skeleton = build_table_skeleton(n_rows, n_cols) if task_type == "table" else None
    prompt = get_ocr_prompt(task_type, n_rows=n_rows, n_cols=n_cols, skeleton_content=skeleton)

    raw1 = await asyncio.to_thread(_call_qwen_vl, image_bytes, prompt, temperature)
    pass1 = extract_and_repair_json(raw1)

    structure_warning: Optional[str] = None
    if task_type == "table" and pass1 is not None:
        ok, reason = validate_table_structure(pass1, n_rows, n_cols)
        if not ok:
            structure_warning = reason

    pass1_str = (
        json.dumps(pass1, ensure_ascii=False, indent=2)
        if pass1 is not None
        else "(Lần trích xuất trước bị lỗi định dạng nghiêm trọng, không có JSON hợp lệ để hiển thị)"
    )
    review_prompt = get_review_prompt(task_type, pass1_str, n_rows=n_rows, n_cols=n_cols)

    raw2 = await asyncio.to_thread(_call_qwen_vl, image_bytes, review_prompt, 0.1)
    final = extract_and_repair_json(raw2)

    if final is None:
        return {
            "status": "failed_all_samples",
            "confidence": 0.0,
            "pass1_content": pass1,
            "content": {"error": "Lỗi Parse JSON ở cả 2 lượt và đã thất bại khi chạy hàm auto-repair."},
            "structure_warning": structure_warning,
        }

    return {
        "status": "completed",
        "confidence": 1.0,
        "pass1_content": pass1,
        "content": final,
        "structure_warning": structure_warning,
    }
