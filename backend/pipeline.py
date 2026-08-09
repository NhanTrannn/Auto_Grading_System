"""
Multi-format Rubric-based Grading Pipeline
==========================================
Fixed version — addresses 11 issues from code review.
"""

import re
import ast
import operator
import json
import os
import sys
import time
import requests
import argparse

from dotenv import load_dotenv

load_dotenv()

from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union

import pandas as pd

pd.set_option("display.max_colwidth", 200)

# ============================================================================
# FIX #10: API key từ env var, không hardcode
# ============================================================================
CFG = {
    "model_name": os.environ.get("LLM_MODEL_NAME", "qwen2.5vlinstruct"),
    "base_url": os.environ.get("LLM_BASE_URL", ""),
    "model_api": os.environ.get("LLM_MODEL_API", ""),
    "api_key": os.environ.get("LLM_API_KEY", ""),
    "use_finetuned_model": False,
    "teacher_review_threshold": 0.65,
    "enable_static_analysis": True,
    # Chain-of-Thought: bật để LLM suy luận (THINK) trước khi ra quyết định
    # (DECIDE) qua 2 lần gọi riêng; tắt thì gọi LLM 1 lần duy nhất (rẻ/nhanh
    # hơn nhưng kém chính xác hơn với câu cần suy luận nhiều bước).
    # FIX: trước đây flag này tồn tại nhưng không có code nào đọc nó — CoT
    # luôn luôn chạy bất kể giá trị. Đã nối flag vào grade_with_llm_advised();
    # default = True vì đây là hành vi đã verify đạt 9.5/10 trên test_input_perfect.
    "use_chain_of_thought": True,
    "cot_max_tokens_think": 600,
    "cot_max_tokens_decide": 500,
    # FIX: model nhỏ (SaoLa-Llama3.1-planner) flaky giữa các lần gọi giống nhau
    # (vd: câu 11 đáp án "20" cố định ra lúc đúng lúc sai qua 4 lần chạy liên tiếp).
    # Gọi lại N lần độc lập, lấy status đa số để giảm rủi ro 1 lần suy luận lệch.
    "cot_self_consistency_n": 3,
    # Trọng số heuristic khi blend với điểm LLM ở grade_with_llm_advised:
    # final_score = heuristic_weight*heuristic_score + (1-heuristic_weight)*llm_score.
    # Mặc định dùng cho Matching (heuristic có điểm thật, đáng tin — so khớp
    # chuỗi/token cụ thể).
    "heuristic_weight": 0.5,
    # Override theo question_type — Logical và Table heuristic KHÔNG BAO GIỜ
    # tính điểm thật (Logical: score luôn 0, chỉ quét keyword; Table: score
    # luôn 0 trừ ca ô bỏ trống). Blend "heuristic_weight" mặc định (0.5) với
    # 1 placeholder-0 sẽ luôn kéo điểm cuối xuống còn nửa dù LLM chấm đúng
    # 100% — đã tái hiện thật trên output_perfect (T13A/T13B/T13C/T14A/T14B/
    # T14C/T15A: llm_score=max, llm_status="correct", nhưng score cuối chỉ
    # còn 50%). Đặt 0.0 để bỏ hẳn ảnh hưởng của heuristic ở 2 loại này, dùng
    # thẳng llm_score làm điểm cuối.
    "heuristic_weight_by_type": {
        "matching":0.5,
        "logical": 0.0,
        "table": 0.0,
    },
}


# ============================================================================
# BAREM LOADER — FIX #3: flatten sub_questions → sub_criteria thành flat list
# ============================================================================


def flatten_criteria(entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Flatten một barem entry thành danh sách phẳng các criterion để grader duyệt.

    Hỗ trợ 2 format:
      Format mới: entry["grading_rule"] = [criterion/sub-question objects]
      Format cũ:  entry["sub_questions"] = [sub-question objects]
                  hoặc entry trực tiếp có criterion_id ở top-level (câu đơn cũ)

    Cấu trúc mỗi item trong grading_rule/sub_questions:
      item
        ├─ sub_criteria[]  → yield từng criterion con với kế thừa
        │                    part_label/question_type/slot_ids từ item cha
        │                    (nếu criterion con không tự khai báo riêng);
        │                    grader_note thì GỘP cả 2 cấp (cha + con), không
        │                    ghi đè — cả item cha lẫn từng sub_criterion đều
        │                    có thể tự khai grader_note riêng, chỉ thị của
        │                    bên nào cũng phải tới được LLM.
        └─ (không có)      → yield chính item như 1 criterion
    """
    flat = []
    items = entry.get("grading_rule") or entry.get("sub_questions", [])

    if not items:
        # Format cũ: câu đơn có criterion_id trực tiếp ở entry
        flat.append(entry)
        return flat

    for item in items:
        sub_criteria = item.get("sub_criteria", [])
        if sub_criteria:
            group_all_or_nothing = bool(item.get("all_or_nothing"))
            for sc in sub_criteria:
                criterion = dict(sc)
                if "part_label" not in criterion:
                    criterion["part_label"] = item.get("part_label") or item.get(
                        "sub_label"
                    )
                if "question_type" not in criterion:
                    criterion["question_type"] = item.get(
                        "question_type", entry.get("question_type")
                    )
                # FIX: kế thừa slot_ids từ item cha nếu criterion con không tự
                # khai báo — trước đây thiếu dòng này, khiến mọi sub_criteria
                # (VD T13A1, T13A2, T15C1...) sau khi flatten đều mất
                # slot_ids, buộc get_student_evidence_for_slot() phải lùi về
                # lọc theo part_label (kém chính xác hơn, không phân biệt
                # được nếu 1 part có nhiều slot).
                if "slot_ids" not in criterion or not criterion.get("slot_ids"):
                    if item.get("slot_ids"):
                        criterion["slot_ids"] = item["slot_ids"]
                # Gộp grader_note ở cả 2 cấp — cha (item, VD T13A) lẫn con
                # (sub_criteria, VD T13A1/T13A2) đều có thể tự khai grader_note
                # riêng. Nếu chỉ kế thừa/ghi đè 1 chiều sẽ làm mất chỉ thị của
                # 1 trong 2 cấp (VD T13A cần nói "SV viết chung 1 hàm cũng
                # được, chấm 2 phần riêng trong hàm đó" — chỉ thị này áp dụng
                # chung cho cả T13A1 lẫn T13A2, trong khi mỗi đứa con có thể
                # còn có ghi chú riêng của chính nó) — nên nối cả 2, không cái
                # nào bị bỏ qua.
                parent_note = item.get("grader_note")
                child_note = criterion.get("grader_note")
                if parent_note and child_note:
                    criterion["grader_note"] = f"{parent_note}\n{child_note}"
                elif parent_note:
                    criterion["grader_note"] = parent_note
                if group_all_or_nothing:
                    criterion["group_id"] = item.get("criterion_id")
                    criterion["group_all_or_nothing"] = True
                    criterion["group_max_score"] = item.get("score", 0)
                flat.append(criterion)
        else:
            criterion = dict(item)
            if "part_label" not in criterion:
                criterion["part_label"] = item.get("sub_label") or item.get(
                    "part_label"
                )
            flat.append(criterion)

    return flat


KNOWN_QUESTION_TYPES = {
    "matching",
    "logical",
    "table",
    "visual",
}

# Status transient — heuristic "chưa có kết luận, chờ LLM/Vision LLM quyết
# định". Nếu status này còn tồn tại ở criterion result CUỐI CÙNG (VD LLM gọi
# thất bại, fallback về nguyên heuristic_result), nghĩa là chưa từng có ai
# thực sự ra quyết định cho tiêu chí đó — không được coi là "wrong" thầm lặng.
TRANSIENT_REVIEW_STATUSES = {
    "needs_teacher_review",
    "needs_vision_teacher_review",
}








# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def _grader_intro(subject: str = "") -> str:
    """Câu mở đầu chuẩn cho mọi prompt LLM: 'Bạn là giáo viên chấm thi môn
    {subject}' nếu barem có khai `subject` (gắn vào criterion qua
    `load_barem`), fallback về 'Bạn là giáo viên chấm thi' (không có mệnh đề
    'môn ...' treo lơ lửng) nếu barem không khai `subject`."""
    return f"Bạn là giáo viên chấm thi môn {subject}" if subject else "Bạn là giáo viên chấm thi"


def value_matches_student_text(value: str, student_text: str) -> bool:
    """
    FIX #6: kiểm tra expected_value có xuất hiện trong bài làm học sinh.
    Trước đây dùng substring thô (`value in student_text`) — dễ false
    positive, VD giá trị "TimMax" khớp nhầm bên trong "TimMax2" hay
    "khongDungTimMax". Với giá trị dạng định danh (chỉ chữ/số/gạch dưới —
    tên hàm, tên biến...) giờ bắt buộc khớp NGUYÊN TỪ (word boundary).
    Với giá trị có khoảng trắng/ký tự khác (cụm từ, câu mô tả logic) vẫn
    dùng substring vì word-boundary không áp dụng được cho cụm từ tự do.

    Không normalize bên nào cả — cả `value` (vế đáp án, từ barem) lẫn
    `student_text` đều so khớp NGUYÊN VĂN, phân biệt hoa/thường. (Trước đây
    có lowercase riêng vế `value` ở nơi gọi — đã bỏ vì tự phá vỡ chính mục
    đích của nó: student_text không hề được lowercase theo, nên value đã
    lowercase gần như không bao giờ khớp được chuỗi gốc còn giữ hoa/thường,
    kể cả khi học sinh viết y hệt — xác nhận bằng test thực tế trước khi bỏ.)
    """
    if not value:
        return False
    if re.fullmatch(r"[A-Za-z0-9_]+", value):
        pattern = r"(?<![A-Za-z0-9_])" + re.escape(value) + r"(?![A-Za-z0-9_])"
        return re.search(pattern, student_text) is not None
    return value in student_text


def clamp_score(
    score: float, min_score: float = 0, max_score: Optional[float] = None
) -> float:
    if max_score is not None:
        return max(min_score, min(score, max_score))
    return max(min_score, score)


_SAFE_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}
_SAFE_COMPAREOPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}


def safe_eval_condition(expr: str, variables: Dict[str, Any]) -> Any:
    """
    Dùng để xử lí hàm công thức toán học  (VD "student_index % 4 == 0",
    "correct_token_count in [2, 3]") bằng AST, KHÔNG dùng eval()/exec().

    Ví dụ: điều kiện student_index % 4 == 0
                                So sánh (==)
                                    / \
                                   /   \
                                  /     \
                    Phép chia dư (%)      0
                    / \
                   /   \
                  /     \
        student_index      4

    Lưu ý:
        - Dùng được cho mọi công thức chỉ cần: số học cơ bản (+ - * / // %),
            so sánh (== != < <= > >= in not in), logic (and or not), và biến lấy từ variables truyền vào.
        - Không dùng được nếu công thức cần: gọi hàm (kể cả hàm "vô hại" như str(), abs(), len()),
          lũy thừa **, phép bit (& | ^ >> <<), truy cập thuộc tính/index (x.y, x[0])
        - NGOẠI LỆ DUY NHẤT: cho phép gọi ".isdigit()" (không tham số) trên
          chuỗi, VD "value.isdigit() and value % 4 == 0" — không mở hẳn cho
          gọi hàm/method tùy ý, chỉ whitelist đúng method này.

    Hướng phát triển:
        - Có thể mở rộng dùng LLM để hỗ trợ parse công thức phức tạp hơn
        - Dùng thêm phương pháp symbolic execution để đánh giá công thức với nhiều biến, hoặc generate test cases.
    """
    for var, value in variables.items():
        if isinstance(value, str) and value.isdigit():
            variables[var] = int(value)
    try:
        node = ast.parse(expr, mode="eval").body
    except SyntaxError as e:
        raise ValueError(f"Invalid condition syntax: {expr!r} ({e})")

    def _eval(n: ast.AST) -> Any:
        if isinstance(n, ast.Constant):
            return n.value
        if isinstance(n, ast.Name):
            if n.id not in variables:
                raise ValueError(f"Unknown variable in condition: '{n.id}'")
            return variables[n.id]
        if isinstance(n, (ast.List, ast.Tuple)):
            return [_eval(el) for el in n.elts]
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub):
            return -_eval(n.operand)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not):
            return not _eval(n.operand)
        if isinstance(n, ast.BinOp) and type(n.op) in _SAFE_BINOPS:
            return _SAFE_BINOPS[type(n.op)](_eval(n.left), _eval(n.right))
        if isinstance(n, ast.BoolOp):
            values = [_eval(v) for v in n.values]
            if isinstance(n.op, ast.And):
                return all(values)
            if isinstance(n.op, ast.Or):
                return any(values)
        if isinstance(n, ast.Compare):
            left = _eval(n.left)
            for op_node, comparator in zip(n.ops, n.comparators):
                if type(op_node) not in _SAFE_COMPAREOPS:
                    raise ValueError(
                        f"Unsupported comparison operator: {type(op_node).__name__}"
                    )
                right = _eval(comparator)
                if not _SAFE_COMPAREOPS[type(op_node)](left, right):
                    return False
                left = right
            return True
        if isinstance(n, ast.Call):
            if (
                isinstance(n.func, ast.Attribute)
                and n.func.attr == "isdigit"
                and not n.args
                and not n.keywords
            ):
                obj = _eval(n.func.value)
                if not isinstance(obj, str):
                    raise ValueError(
                        f"isdigit() chỉ áp dụng được cho chuỗi (str), "
                        f"không phải {type(obj).__name__}"
                    )
                return obj.isdigit()
            raise ValueError(
                "Chỉ hỗ trợ gọi .isdigit() (không tham số) — không hỗ trợ gọi hàm/method khác."
            )
        raise ValueError(f"Unsupported expression in condition: {type(n).__name__}")

    return _eval(node)


# ============================================================================
# STUDENT EVIDENCE EXTRACTION: Lấy thông tin người dùng
# ============================================================================


def get_student_evidence_for_slot(
    sample: Dict[str, Any], part_label: str = None, slot_ids: List[str] = None
) -> Dict[str, Any]:
    """
    Trích xuất câu trả lời của SV cho một slot/part cụ thể.

    Ưu tiên lọc theo slot_ids (chính xác — 1 slot_id chỉ ứng với đúng 1
    phần dữ liệu, không lẫn part khác). Nếu chỉ có part_label mà không có
    slot_ids (caller không truy xuất được slot_ids), fallback lọc theo
    part_label — kém chính xác hơn vì 1 part có thể chứa nhiều slot con
    (VD part "a" có "a_S1", "a_S2"), fallback này chỉ lọc đúng khi
    part_label và slot_id trùng nhau (part không chia slot con).

    Returns:
        {
            "student_answer": str,   # đã ghép các dòng cùng slot/part bằng "\n"
            "tokens": [...],
            "tables": [...],
            "visual_answers": [...],
            "part_label": str,
            "type": "full" | "slot_matched" | "part_matched" | "blank" | "fallback",
            "found": bool
        }
    """
    student_answer = sample.get("student_answer", {}) or {}
    all_lines = student_answer.get("lines", []) or []
    all_tokens = student_answer.get("tokens", []) or []
    all_tables = student_answer.get("tables", []) or []
    all_visuals = student_answer.get("visual_answers", []) or []

    # Trường hợp không có part_label và slot_ids → trả về full_text, type = "full" nghĩa là không có part hay slot nào match, nhưng vẫn có full_text
    if not part_label and not slot_ids:
        return {
            "student_answer": student_answer.get("full_text", "") or "",
            "tokens": all_tokens,
            "tables": all_tables,
            "visual_answers": all_visuals,
            "part_label": None,
            "type": "full",
            "found": bool(student_answer.get("full_text", "")),
        }

    explicit_blank = False
    slot_ids_matched_nothing = False

    # Có slot_ids → lọc theo slot_id (ưu tiên, chính xác).
    if slot_ids:
        slot_id_set = set(slot_ids)

        slot_lines = [
            l
            for l in all_lines
            if l.get("slot_id") in slot_id_set and not l.get("is_blank", False)
        ]
        slot_tokens = [t for t in all_tokens if t.get("slot_id") in slot_id_set]
        slot_tables = [tb for tb in all_tables if tb.get("slot_id") in slot_id_set]
        slot_visuals = [
            v
            for v in all_visuals
            if v.get("slot_id") in slot_id_set and not v.get("is_blank", False)
        ]

        if slot_lines or slot_tokens or slot_tables or slot_visuals:
            # KHÔNG lọc bỏ dòng text rỗng ở đây — dòng trống là 1 dòng thật
            # trong code nhiều dòng của học sinh (VD dòng trống ngăn cách),
            # lọc bỏ sẽ làm lệch cấu trúc dòng. KHÔNG .strip() nữa — giữ
            # nguyên y hệt những gì học sinh viết, kể cả khoảng trắng/dòng
            # trống ở đầu/cuối khối.
            text = "\n".join(l.get("text", "") for l in slot_lines)
            if not text and slot_tokens:
                text = " ".join(
                    t.get("text", "") for t in slot_tokens if t.get("text", "")
                )
            return {
                "student_answer": text,
                "tokens": slot_tokens,
                "tables": slot_tables,
                "visual_answers": slot_visuals,
                "part_label": part_label,
                "type": "slot_matched",
                "found": True,
            }

        explicit_blank = any(
            l.get("slot_id") in slot_id_set and l.get("is_blank", False)
            for l in all_lines
        ) or any(
            v.get("slot_id") in slot_id_set and v.get("is_blank", False)
            for v in all_visuals
        )
        slot_ids_matched_nothing = not explicit_blank

    # FIX: slot_ids khai báo nhưng KHÔNG khớp gì cả — không content, không cả
    # is_blank marker (VD barem đổi slot_ids sau khi gộp sub_criteria nhưng
    # data OCR sinh slot_id theo quy ước cũ, không còn khớp) — trước đây rơi
    # thẳng xuống fallback full_text (TOÀN BỘ câu, gộp lẫn part khác), có thể
    # lấy nhầm nội dung của 1 part hoàn toàn khác rồi chấm nhầm cho part này
    # (tái hiện thật: T14B match sai slot_ids, fallback full_text lấy nhầm
    # nguyên văn nội dung phần a "struct Sinhvien..." để chấm phần b).
    # Giờ thử thêm 1 bước trung gian AN TOÀN HƠN trước khi tới full_text: lọc
    # theo part_label (nếu có) — vẫn đúng scope 1 part, chỉ kém chính xác
    # hơn slot_id khi part đó có nhiều slot con.
    if part_label and (not slot_ids or slot_ids_matched_nothing):
        part_label_set = {part_label}

        part_lines = [
            l
            for l in all_lines
            if l.get("part_label") in part_label_set and not l.get("is_blank", False)
        ]
        part_tokens = [t for t in all_tokens if t.get("part_label") in part_label_set]
        part_tables = [
            tb for tb in all_tables if tb.get("part_label") in part_label_set
        ]
        part_visuals = [
            v
            for v in all_visuals
            if v.get("part_label") in part_label_set and not v.get("is_blank", False)
        ]

        if part_lines or part_tokens or part_tables or part_visuals:
            # Xem ghi chú ở nhánh slot_ids phía trên — không lọc bỏ dòng rỗng,
            # không .strip().
            text = "\n".join(l.get("text", "") for l in part_lines)
            if not text and part_tokens:
                text = " ".join(
                    t.get("text", "") for t in part_tokens if t.get("text", "")
                )
            return {
                "student_answer": text,
                "tokens": part_tokens,
                "tables": part_tables,
                "visual_answers": part_visuals,
                "part_label": part_label,
                "type": "part_matched",
                "found": True,
            }

        explicit_blank = any(
            l.get("part_label") in part_label_set and l.get("is_blank", False)
            for l in all_lines
        ) or any(
            v.get("part_label") in part_label_set and v.get("is_blank", False)
            for v in all_visuals
        )

    if explicit_blank:
        # Bỏ trống có chủ ý — KHÔNG fallback full_text
        return {
            "student_answer": "",
            "tokens": [],
            "tables": [],
            "visual_answers": [],
            "part_label": part_label,
            "type": "blank",
            "found": False,
            "is_blank": True,
        }

    # Fallback: trả về full_text (không có thông tin part nào)
    full_text = student_answer.get("full_text", "") or ""
    return {
        "student_answer": full_text,
        "tokens": all_tokens,
        "tables": all_tables,
        "visual_answers": all_visuals,
        "part_label": part_label,
        "type": "fallback",
        "found": False,
    }


# ============================================================================
# LLM API — FIX #9: robust JSON extraction thay vì greedy regex
# ============================================================================


def _extract_json_from_text(text: str) -> Optional[Dict]:
    """
    FIX #9: Extract JSON object từ LLM response một cách an toàn.
    Thử JSONDecoder.raw_decode trước, fallback regex.
    """
    text = text.strip()

    # Strip markdown code fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    # Thử parse trực tiếp
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Thử raw_decode từ vị trí đầu tiên có '{'
    decoder = json.JSONDecoder()
    start = text.find("{")
    if start != -1:
        try:
            obj, _ = decoder.raw_decode(text, start)
            return obj
        except json.JSONDecodeError:
            pass

    # Last resort: greedy regex (original behavior)
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None


# ============================================================================
# VALIDATION
# ============================================================================


def validate_sample_schema(
    sample: Dict[str, Any],
    after_routing: bool = False,
    barem_dict: Dict[int, List[Dict]] = None,
) -> Dict[str, Any]:
    """
    Dùng để validate sample trước khi đưa vào hệ thống chấm.
    Yêu cầu:
        1) sample có đầy đủ các field bắt buộc:
            - sample_id
            - question.text
            - student_answer
            - max_score
        2) Nếu sample có question_number, kiểm tra barem_dict có criteria cho question_number đó
        3) Nếu after_routing=True, kiểm tra question_type không còn là "unknown" nữa

    """
    errors = []
    warnings = []

    # FIX #1: bỏ 'teacher_barem' — nó có thể nằm ở barem_dict bên ngoài
    required_fields = ["sample_id", "question", "student_answer", "max_score"]

    for field in required_fields:
        if field not in sample:
            errors.append(f"Missing required field: '{field}'")

    if "question" in sample:
        if "text" not in sample["question"]:
            errors.append("Missing question.text")
        if "parts" not in sample["question"]:
            warnings.append("Missing question.parts (optional but recommended)")

    # Kiểm tra có criteria không (từ sample hoặc barem_dict)
    q_num = sample.get("question_number")
    has_criteria = bool(sample.get("teacher_barem"))
    if not has_criteria and barem_dict and q_num:
        has_criteria = bool(barem_dict.get(q_num))
    if not has_criteria:
        warnings.append("No criteria found in sample or barem_dict for this question.")

    qtype = sample.get("question_type")

    if after_routing:
        if not qtype or qtype in ["unknown"]:
            warnings.append(
                "question_type is still unknown after routing. "
                "Consider setting it from parem lookup."
            )
    else:
        if not qtype or qtype in ["unknown"]:
            warnings.append(
                "question_type is null/unknown before routing — acceptable."
            )

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}

def validate_input(
    samples: List[Dict[str, Any]], barem_dict: Dict[int, List[Dict]] = None
) -> Dict[str, Any]:
    """
    Validate toàn bộ input samples trước khi chấm.
    1)
    """
    errors: List[str] = []
    warnings: List[str] = []

    for i, sample in enumerate(samples):
        sid = sample.get("sample_id", f"sample_{i}")
        v = validate_sample_schema(sample, after_routing=False, barem_dict=barem_dict)
        errors.extend(f"{sid}: {e}" for e in v["errors"])
        for w in v["warnings"]:
            # "question_type null trước routing" luôn đúng ở giai đoạn này
            # (routing chưa chạy) — không actionable, không đáng in ra.
            if "question_type is null/unknown before routing" in w:
                continue
            warnings.append(f"{sid}: {w}")

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}

def validate_barem(
    barem_dict: Dict[int, List[Dict[str, Any]]], declared_total: Optional[float] = None
) -> Dict[str, Any]:
    """
    Kiểm tra tính nhất quán của barem đã flatten (per criterion), bổ sung cho
    validate_sample_schema() — trước đây chỉ sample được validate, barem thì
    không, nên lỗi cấu hình (VD sub_criteria thuộc group all_or_nothing có
    score=null nhưng group_max_score không khớp nhau) lọt xuống tận báo cáo
    cuối mà không ai biết.
    """
    errors: List[str] = []
    warnings: List[str] = []

    seen_criterion_ids: Dict[str, int] = {}
    groups: Dict[str, List[Dict[str, Any]]] = {}
    computed_total = 0.0

    for q_num, criteria in barem_dict.items():
        q_total = 0.0
        q_groups_seen: set = set()

        for c in criteria:
            cid = c.get("criterion_id")
            if not cid:
                errors.append(
                    f"Q{q_num}: có criterion thiếu criterion_id (content='{c.get('content', '')[:50]}')"
                )
                continue

            seen_criterion_ids[cid] = seen_criterion_ids.get(cid, 0) + 1

            qtype = c.get("question_type")
            if not qtype:
                warnings.append(f"Q{q_num}/{cid}: thiếu question_type")
            elif qtype not in KNOWN_QUESTION_TYPES:
                warnings.append(
                    f"Q{q_num}/{cid}: question_type lạ '{qtype}' (không nằm trong {sorted(KNOWN_QUESTION_TYPES)})"
                )

            if c.get("group_all_or_nothing"):
                gid = c.get("group_id")
                if not gid:
                    errors.append(
                        f"Q{q_num}/{cid}: group_all_or_nothing=True nhưng thiếu group_id"
                    )
                    continue
                groups.setdefault(gid, []).append(c)
                if gid not in q_groups_seen:
                    q_groups_seen.add(gid)
                    q_total += c.get("group_max_score", 0) or 0
            else:
                score = c.get("score")
                if score is None:
                    errors.append(
                        f"Q{q_num}/{cid}: score=null nhưng KHÔNG thuộc group all_or_nothing "
                        f"(sub_criteria trong group phải khai báo 'all_or_nothing': true ở tiêu chí cha)"
                    )
                elif score < 0:
                    errors.append(f"Q{q_num}/{cid}: score âm ({score})")
                else:
                    q_total += score

        computed_total += q_total

    # Duplicate criterion_id
    for cid, count in seen_criterion_ids.items():
        if count > 1:
            errors.append(f"criterion_id trùng lặp: '{cid}' xuất hiện {count} lần")

    # Consistency trong từng group all_or_nothing
    for gid, members in groups.items():
        max_scores = {m.get("group_max_score") for m in members}
        if len(max_scores) > 1:
            errors.append(
                f"Group '{gid}': group_max_score không nhất quán giữa các thành viên: {max_scores}"
            )
        if len(members) < 2:
            warnings.append(
                f"Group '{gid}': chỉ có 1 thành viên — all_or_nothing không có ý nghĩa"
            )

    # Tổng điểm toàn barem so với total_score khai báo
    if declared_total is not None:
        computed_total = round(computed_total, 4)
        if abs(computed_total - declared_total) > 0.01:
            errors.append(
                f"Tổng điểm tính từ barem ({computed_total}) khác total_score khai báo ({declared_total})"
            )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "computed_total": round(computed_total, 4),
    }


# ============================================================================
# ROUTING
# ============================================================================
def apply_question_routing(
    sample: Dict[str, Any], barem_dict: Dict[int, List[Dict]] = None
) -> Dict[str, Any]:
    """
    Lấy question_type từ parem.
    Return:
        {
            "question_type": str,
            "routing": {
                "question_type": str,
                "confidence": float,
                "reason": str,
                "candidates": list,
                "uses_llm": bool,
                "method": str
            }
        }
    """
    routed = dict(sample)

    q_num = sample.get("question_number")
    first_criterion: Dict[str, Any] = {}
    if barem_dict and q_num and barem_dict.get(q_num):
        first_criterion = barem_dict[q_num][0]
    parem_qtype = first_criterion.get("question_type")

    if parem_qtype and parem_qtype not in [None, "unknown"]:
        routed["question_type"] = parem_qtype
        routed["routing"] = {
            "question_type": parem_qtype,
            "confidence": 1.0,
            "reason": f"question_type from parem (criterion {first_criterion.get('criterion_id')})",
            "candidates": [],
            "uses_llm": False,
            "method": "parem_lookup",
        }
        return routed

    # Trường hợp không có thì báo lỗi
    routed["question_type"] = "unknown"
    routed["routing"] = {
        "question_type": "unknown",
        "confidence": 0.0,
        "reason": "Lacking question_type in parem; cannot determine question type.",
        "candidates": [],
        "uses_llm": False,
        "method": "missing_question_type",
    }
    return routed


# =====================================================================================================
# Grader 1: Dùng cho Mode: Matching - expected_outputs / expected_output_tokens, partial_credit_rule, conditional_outputs
# Các hàm cần dùng:
#   + parse_self_reported_index() — đọc số thứ tự học sinh tự ghi ở 1 slot khác trong cùng câu
#   + prepare_conditional_output() — chuẩn bị conditional_outputs cho đúng student_index
#   + get_student_evidence_for_slot() — đọc text/tokens/tables/visual_answers cho đúng slot_ids
#   + _check_expected_output() — check expected_output / expected_output_tokens, partial_credit_rule, conditional_outputs
#   + grade_expected_output_criterion() — chấm 1 criterion có expected_output / expected_output_tokens, partial_credit_rule, conditional_outputs

# =====================================================================================================


def parse_self_reported_index(
    sample: Dict[str, Any], slot_ids: List[str]
) -> Optional[int]:
    """
    Nhận thẳng slot_ids (đọc từ criterion.get("slot_ids") hoặc
    condition_source.get("slot_ids") ở nơi gọi) — KHÔNG tự dựng slot_id theo
    công thức nữa (trước đây dựng f"cau_{q_num}_001_{part_label}", dễ vỡ nếu
    quy ước đặt tên thay đổi).

    Trả về None nếu không đọc được số nào (bỏ trống, chữ viết tay không rõ...).
    Return:
        int: số thứ tự học sinh tự ghi (1, 2, 3...) nếu đọc được
        None: nếu không đọc được số nào
    """
    evidence = get_student_evidence_for_slot(sample, "", slot_ids)
    text = (evidence.get("student_answer") or "").strip()
    match = re.search(r"-?\d+", text)
    if not match:
        return None
    return int(match.group())


def prepare_conditional_output(
    sample: Dict[str, Any], criterion: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Chuẩn bị đáp án conditional — chỉ TRA đáp án đúng (expected_outputs/tokens)
    cho đúng student_index, chuẩn bị dữ liệu cho grade_exact_expected_token()
    chấm tiếp. VD: Số thứ tự là 3 → expected_outputs là ["A"], Số thứ tự là 4
    → expected_outputs là ["B"].

    CHỈ được gọi khi criterion đã xác nhận CÓ conditional_outputs (nơi gọi —
    grade_expected_output_criterion — lọc trước điều này). Nếu hàm này bị
    gọi mà thiếu conditional_outputs thì đó là lỗi logic ở nơi gọi, không
    phải vấn đề dữ liệu barem — nên báo lỗi ngay thay vì âm thầm fallback.
    """

    conditional_outputs = criterion.get("conditional_outputs", [])

    if not conditional_outputs:
        raise ValueError(
            f"prepare_conditional_output() được gọi cho criterion "
            f"'{criterion.get('criterion_id')}' nhưng criterion KHÔNG có "
            f"conditional_outputs — lỗi logic ở nơi gọi (phải kiểm tra "
            f"criterion.get('conditional_outputs') trước khi gọi hàm này)."
        )

    # Bước 1: Xác định nguồn của con số dùng để tra conditional_outputs, qua
    # field tổng quát "condition_source" — hỗ trợ 2 loại:
    #   {"type": "sample_field", "field": "student_index"}
    #       → đọc thẳng 1 field có sẵn trong sample (mặc định nếu criterion
    #         không khai condition_source: field="student_index", tức STT
    #         ground truth).
    #   {"type": "self_reported", "slot_ids": ["cau_3_001_main_S1"]}
    #       → đọc số học sinh TỰ GHI ở 1 slot khác trong cùng câu (chấm theo
    #         cái học sinh THỰC SỰ dùng để tính, không phải giá trị ground
    #         truth — xem parse_self_reported_index() để hiểu lý do). Nhận
    #         thẳng slot_ids (không dựng công thức từ part_label nữa).
    # Biến kết quả gọi là "value"
    condition_source: Dict[str, Any] = criterion.get("condition_source")

    source_type = condition_source.get("type")

    if source_type == "self_reported":
        # Lấy giá trị từ slot_ids học sinh tự ghi — có thể là số hoặc chữ..
        target_slot_ids: List[str] = condition_source.get("slot_ids") or []
        evidence = get_student_evidence_for_slot(sample, "", target_slot_ids)
        value = evidence.get("student_answer") or ""

        # force_wrong: học sinh bỏ trống slot tự ghi → không có cơ sở gì để
        # xác minh, chấm thẳng "wrong", KHÔNG đẩy qua LLM/teacher review.
        if not value.strip():
            return {
                "matched": False,
                "force_wrong": True,
                "reason": "Không ghi giá trị ở slot tự báo cáo (bỏ trống) — không có cơ sở xác minh.",
            }

    elif source_type == "sample_field":
        # Lấy điều kiện từ field có sẵn trong sample
        value = sample.get(condition_source.get("field"))
        if value is None:
            raise ValueError(
                f"prepare_conditional_output(): condition_source.type "
                f"{source_type!r} nhưng sample không có field "
                f"{condition_source.get('field')!r} — kiểm tra barem và sample."
            )
    else:
        raise ValueError(
            f"prepare_conditional_output(): condition_source.type "
            f"{source_type!r} không hợp lệ ở criterion "
            f"'{criterion.get('criterion_id')}' — chỉ hỗ trợ "
            f"'sample_field' hoặc 'self_reported'."
        )

    # Bước 2: Dùng value để match với conditional_outputs (điều kiện toán
    # học, VD "value % 4 == 0", "value in [1,3,5,7,9]"), trả về
    # expected_outputs tương ứng.
    for cond in conditional_outputs:
        if "condition" in cond and value is not None:
            condition_expr = cond.get("condition", "")
            try:
                result = safe_eval_condition(condition_expr, {"value": value})
                if result:
                    return {
                        "expected_outputs": cond.get("expected_outputs", []),
                        "expected_output_tokens": cond.get(
                            "expected_output_tokens", []
                        ),
                        "partial_credit_rule": criterion.get("partial_credit_rule"),
                        "matched": True,
                        "reason": f"Matched condition: '{condition_expr}' with value={value}",
                    }
            except Exception as e:
                print(f"⚠ Condition eval failed: '{condition_expr}' — {e}")

    # Nếu không có điều kiện nào match, báo lỗi cảnh báo (để kiểm tra lại barem)
    print(
        f"⚠ prepare_conditional_output: criterion "
        f"'{criterion.get('criterion_id')}' có conditional_outputs nhưng "
        f"KHÔNG điều kiện nào khớp value={value!r} "
        f"— kiểm tra lại barem có thiếu case hoặc condition_source bị null/sai."
    )
    return {
        "expected_outputs": [],
        "expected_output_tokens": criterion.get("expected_output_tokens", []),
        "partial_credit_rule": criterion.get("partial_credit_rule"),
        "matched": False,
        "reason": "No matching conditional output found",
    }


def _check_exact_output_match(student_text: str, expected_outputs: List[str]) -> bool:
    """
    So khớp CHÍNH XÁC TUYỆT ĐỐI (byte-exact, ==) giữa student_text (đã ghép
    đúng theo các đường kẻ học sinh viết, nối bằng "\\n" — xem
    get_student_evidence_for_slot) và expected_outputs. KHÔNG qua bất kỳ
    normalize nào (không strip, không lowercase, không gộp/xóa khoảng trắng).

    FIX: trước đây dùng 1 bước normalize xóa TOÀN BỘ khoảng trắng để gọi là
    "khớp chính xác" — khiến "35 29" (2 số RIÊNG BIỆT, có thể là câu trả lời sai) và
    "3529" (1 số, đáp án đúng) bị coi là khớp — mâu thuẫn với chính tên gọi
    "exact match". Giờ so == tuyệt đối; các trường hợp lệch định dạng nhỏ
    sẽ rơi xuống Case 1 (token matching) hoặc Case 3 (review) thay vì được
    heuristic tự quyết định rủi ro ở đúng bước "chắc chắn 100%, bypass LLM".

    FIX: trước đây còn thử so KHỚP TỪNG DÒNG RIÊNG (để "cứu" trường hợp
    student_text gộp có lẫn nháp không khớp) — bỏ, vì đó là việc của tầng
    trích xuất dữ liệu/OCR (phải tách đúng nháp khỏi đáp án TRƯỚC khi đưa
    vào chấm), không phải việc của grading code tự dò từng dòng để đoán.
    """
    return bool(expected_outputs) and student_text in expected_outputs


def _grade_by_tokens(
    expected_output_tokens: List[str],
    student_text: str,
    max_score: float,
    partial_credit_rule: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]],
) -> Dict[str, Any]:
    """
    Kiểm tra tính điểm theo từng token - dùng khi _check_exact_output_match()
         thất bại (chuỗi thô không match expected_outputs) và có expected_output_tokens

    Tìm TUẦN TỰ từng expected_output_tokens trong student_text NGUYÊN VĂN
    (KHÔNG bỏ khoảng trắng) — tìm token kế tiếp ở bất kỳ đâu trong phần còn
    lại của chuỗi (từ sau vị trí token trước đó tìm được trở đi, không được
    nhảy lùi), giữ đúng THỨ TỰ token nhưng không đòi vị trí chính xác tuyệt
    đối. VD "0122395-8" vẫn tìm thấy "12" (ở vị trí 1-2, không phải ngay đầu
    chuỗi).

    Return:
        {
            "score": float,
            "status": "partially_correct" | "wrong",
            "reason": str,
            "expected_output_tokens": [...],   # đáp án đúng, theo thứ tự
            "student_tokens": [...],           # student_tokens[i] khớp expected_output_tokens[i]
                                                # (bằng expected token nếu đúng, None nếu không tìm thấy —
                                                # is_correct từng token = student_tokens[i] is not None)
            "detected_errors": [
                {
                    "error_type": "wrong_output_token",
                    "token_index": int,
                    "expected": str,
                    "student": str | None,
                    "message": str,
                },
            ],
        }
    """
    student_tokens: List[Optional[str]] = []
    token_evals = []
    correct_count = 0
    detected_errors = []
    pos = 0

    # Tìm kiếm so khớp từng expected_token trong student_text.
    for i, expected_token in enumerate(expected_output_tokens):
        idx = student_text.find(expected_token, pos)
        is_correct = idx != -1

        student_token = expected_token if is_correct else None
        if is_correct:
            correct_count += 1
            pos = idx + len(expected_token)
        student_tokens.append(student_token)
        token_evals.append(
            {
                "index": i,
                "token_index": idx,
                "expected": expected_token,
                "student": student_token,
                "is_correct": is_correct,
            }
        )
        if not is_correct:
            detected_errors.append(
                {
                    "error_type": "wrong_output_token",
                    "index": i,
                    "token_index": idx,
                    "expected": expected_token,
                    "student": student_token,
                    "message": f"Token {i}: expected='{expected_token}', student='{student_token}'",
                }
            )

    ratio = correct_count / max(1, len(expected_output_tokens))
    score = max_score * ratio

    if partial_credit_rule:
        rules = (
            partial_credit_rule
            if isinstance(partial_credit_rule, list)
            else [partial_credit_rule]
        )
        wrong_count = len(expected_output_tokens) - correct_count
        best_score = None

        for rule in rules:
            rule_type = rule.get("type", "")
            candidate = None
            try:
                if rule_type == "count_wrong_tokens":
                    cond = rule.get("condition", "")
                    if cond and safe_eval_condition(
                        cond, {"wrong_token_count": wrong_count}
                    ):
                        candidate = rule.get("partial_score", 0)

                elif rule_type == "count_correct_tokens":
                    cond = rule.get("condition", "")
                    if cond and safe_eval_condition(
                        cond, {"correct_token_count": correct_count}
                    ):
                        candidate = rule.get("partial_score", 0)

                elif rule_type == "date_partial_match":
                    # câu 12: tháng và năm đúng → 0.25
                    if "1" in [
                        t["expected"] for t in token_evals if t["is_correct"]
                    ] and "2026" in [
                        t["expected"] for t in token_evals if t["is_correct"]
                    ]:
                        candidate = rule.get("partial_score", 0)

                elif rule_type == "position_tolerance":
                    # câu 10: sai ở <=2 vị trí đầu hoặc <=2 cuối → 0.25
                    wrong_positions = [
                        i for i, t in enumerate(token_evals) if not t["is_correct"]
                    ]
                    n = len(expected_output_tokens)
                    if wrong_positions and all(
                        p < 2 or p >= n - 2 for p in wrong_positions
                    ):
                        candidate = rule.get("partial_score", 0)

                elif rule_type == "custom_condition":
                    cond = rule.get("condition", "")
                    if cond and safe_eval_condition(
                        cond,
                        {
                            "correct_token_count": correct_count,
                            "wrong_token_count": wrong_count,
                        },
                    ):
                        candidate = rule.get("partial_score", 0)

            except Exception as e:
                print(f"⚠ partial_credit_rule eval failed: {e}")

            if candidate is not None and (best_score is None or candidate > best_score):
                best_score = candidate

        score = best_score if best_score is not None else 0

    if score > 0:
        status = "partially_correct"
        wrong_tokens = ",\n".join(error["message"] for error in detected_errors)
        reason = f"{correct_count}/{len(expected_output_tokens)} tokens correct (partial credit applied). And wrong tokens are:\n{wrong_tokens}."
    else:
        status = "wrong"
        reason = "No output token correct."

    return {
        "score": round(score, 4),
        "status": status,
        "reason": reason,
        "expected_output_tokens": expected_output_tokens,
        "student_tokens": student_tokens,
        "detected_errors": detected_errors,
    }


def grade_exact_expected_token(
    student_text: str,
    expected_outputs: List[str],
    expected_output_tokens: List[str],
    max_score: float,
    partial_credit_rule: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Gộp 2 chiến lược chấm dựa trên "đáp án kỳ vọng đã biết trước"
    1. Thử khớp CHÍNH XÁC với expected_outputs trước (_check_exact_output_match)
        => Kết quả return 0 hoặc max_score, status="correct" nếu khớp.

    2. Nếu không khớp chính xác mà được phép chấm điểm bán phần (có expected_output_tokens) → chấm theo token
        => Kết quả return score theo token

    Trả về None nếu KHÔNG khớp chính xác VÀ KHÔNG có token nào để so — lúc
    đó không đủ cơ sở để chấm, dispatcher (grade_expected_output_criterion,
    nhánh "result is None") sẽ tự dựng kết quả needs_teacher_review.
    """
    if _check_exact_output_match(student_text, expected_outputs):
        return {
            "score": max_score,
            "status": "correct",
            "reason": "Student answer matches exactly accepted output.",
        }

    if partial_credit_rule and expected_output_tokens:
        return _grade_by_tokens(
            expected_output_tokens, student_text, max_score, partial_credit_rule
        )

    return None


def _build_conditioning_info(
    criterion: Dict[str, Any], resolved: Dict[str, Any]
) -> Dict[str, Any]:
    """Thông tin về conditional_outputs cho LLM biết: có phải câu điều kiện
    không (`has_conditional`), điều kiện dựa vào nguồn nào (`conditional_type`
    — "sample_field": field có sẵn trong sample, "self_reported": số học sinh
    tự ghi ở slot khác), và heuristic đã băm ra đáp án/điều kiện nào khớp
    (`heuristic_conditional_define`, từ `resolved` — kết quả của
    prepare_conditional_output). Luôn trả về đủ 3 key kể cả khi criterion
    không phải dạng conditional (has_conditional=False, 2 key kia = None) —
    để nơi gọi không phải tự check field có tồn tại hay không."""
    conditional_outputs = criterion.get("conditional_outputs")
    if not conditional_outputs:
        return {
            "has_conditional": False,
            "conditional_type": None,
            "heuristic_conditional_define": None,
        }
    condition_source = criterion.get("condition_source") or {}
    return {
        "has_conditional": True,
        "conditional_type": condition_source.get("type"),
        "heuristic_conditional_define": {
            "matched": resolved.get("matched", False),
            "expected_outputs": resolved.get("expected_outputs"),
            "expected_output_tokens": resolved.get("expected_output_tokens"),
            "reason": resolved.get("reason"),
        },
    }


def _build_output_criterion_result(
    criterion: Dict[str, Any],
    max_score: float,
    evidence: Dict[str, Any],
    resolved: Dict[str, Any],
    *,
    score: float,
    status: str,
    reason: Optional[str],
    expected_outputs: List[str],
    detected_errors: Optional[List[Dict[str, Any]]] = None,
    expected_output_tokens: Optional[List[str]] = None,
    student_tokens: Optional[List[Optional[str]]] = None,
) -> Dict[str, Any]:
    """Dựng dict kết quả chuẩn cho grade_expected_output_criterion — tất cả
    field đều khai báo tường minh (không gom qua **fields) để schema kết quả
    rõ ràng, dễ theo dõi field nào đến từ đâu.

    Không có `is_correct`/`teacher_review_required` riêng — cả 2 đều suy ra
    được 100% từ `status` (`is_correct` = status=="correct"; cần review =
    status=="needs_teacher_review", đã có trong TRANSIENT_REVIEW_STATUSES) ở
    mọi nhánh của grader này, giữ thêm chỉ là trùng lặp thông tin."""
    return {
        "criterion_id": criterion.get("criterion_id"),
        "part_label": criterion.get("part_label"),
        "criterion_content": criterion.get("content", ""),
        "score": round(score, 4),
        "max_score": max_score,
        "status": status,
        "reason": reason,
        "evidence": evidence,
        "expected_outputs": expected_outputs,
        "conditioning": _build_conditioning_info(criterion, resolved),
        "detected_errors": detected_errors if detected_errors is not None else [],
        "expected_output_tokens": expected_output_tokens,
        "student_tokens": student_tokens,
    }


def prepare_output_evidence(
    sample: Dict[str, Any],
    criterion: Dict[str, Any],
    extra_expected_outputs: List[str],
) -> Tuple[Dict[str, Any], str, List[str]]:
    """Lấy bằng chứng bài làm học sinh (evidence/student_text) và danh sách
    expected_outputs (gộp extra_expected_outputs — VD đáp án đã resolve từ
    conditional_outputs — vào đầu, không trùng lặp)."""
    evidence = get_student_evidence_for_slot(
        sample, criterion.get("part_label"), criterion.get("slot_ids", [])
    )
    student_text = evidence.get("student_answer", "")

    expected_outputs = list(criterion.get("expected_outputs", []))
    for index, expected_output in enumerate(expected_outputs):
        if isinstance(expected_output, str) and expected_output in sample:
            resolved_value = sample.get(expected_output)
            if resolved_value is not None:
                expected_outputs[index] = str(resolved_value)

    for value in reversed(extra_expected_outputs):
        if value not in expected_outputs:
            expected_outputs = [value] + expected_outputs

    return evidence, student_text, expected_outputs


def grade_expected_output_criterion(
    sample: Dict[str, Any], criterion: Dict[str, Any]
) -> Dict[str, Any]:
    """
    System 1 - Matching: Chấm các câu dạng expected output:
        Các hàm xử lí bao gồm các hàm theo thứ tự:
        1. prepare_conditional_output — chuẩn bị expected_output/tokens
            theo điều kiện (nếu có conditional_outputs).
        2. prepare_output_evidence — lấy evidence/student_text và danh sách
            expected_outputs.
        3. grade_exact_expected_token — chấm khớp chính xác, hoặc theo token +
            partial credit nếu có expected_output_tokens.
        4. _build_output_criterion_result — dựng dict kết quả chuẩn, tránh lặp
            lại danh sách field giống nhau ở mỗi nhánh (criterion_id, part_label,
            max_score, evidence, conditioning...).
    Luồng chạy:
        Bước 1: có conditional_outputs?
                   /                              \\
                 không                            có
                   |                                |
      dùng thẳng expected_output(s)/       có condition_source?
      tokens tĩnh của criterion              /                \\
                   |                       không               có
                   |                         |                   |
                   |          resolved={matched:False,   prepare_conditional_output()
                   |          reason:"thiếu condition_source"}    |
                   |                         \\                  /
                   |                          \\                /
                   |                       resolved.force_wrong?
                   |                     (VD self_reported bị bỏ trống —
                   |                      không có cơ sở xác minh)
                   |                          /            \\
                   |                        có             không
                   |                         |                |
                   |          return NGAY (score=0,   extra_expected_outputs/
                   |          status="wrong",          expected_output_tokens/
                   |          KHÔNG qua LLM)             partial_credit_rule
                   |                                     lấy từ resolved
                   |                                          |
                    \\                                       /
                     \\                                     /
                          Bước 2: prepare_output_evidence()
                     (evidence/student_text + expected_outputs gộp)
                                        |
                          Bước 3: grade_exact_expected_token()
                    (khớp chính xác HOẶC token+partial credit)
                                        |
                         kết quả None? (không khớp, không có token)
                            /                           \\
                          có                            không
                           |                               |
      tự dựng needs_teacher_review        (dùng thẳng kết quả vừa chấm)
      (KHÔNG đoán mò bằng fuzzy match)                       |
                            |                                |
                            \\                              /
                             \\                           /
                              _build_output_criterion_result()
                                        |
                                     return
    """

    max_score = criterion.get("score", 0)

    # Bước 1: Kiểm tra conditional_outputs (nếu có) để chuẩn bị expected_outputs/tokens
    if criterion.get("conditional_outputs"):
        if criterion.get("condition_source"):
            resolved = prepare_conditional_output(sample, criterion)
        else:
            resolved = {
                "matched": False,
                "reason": "Criterion has conditional_outputs but no condition_source defined.",
            }
        # force_wrong: Không có cơ sở xác minh (VD STT tự ghi bị bỏ trống) → chấm
        # thẳng "wrong", không qua grade_exact_expected_token/grade_no_match_review
        if resolved.get("force_wrong"):
            evidence = get_student_evidence_for_slot(
                sample, criterion.get("part_label") or "", criterion.get("slot_ids", [])
            )
            return _build_output_criterion_result(
                criterion,
                max_score,
                evidence,
                resolved,
                score=0,
                status="wrong",
                reason=resolved.get("reason"),
                expected_outputs=[],
                detected_errors=[],
            )

        extra_expected_outputs = resolved.get("expected_outputs", [])
        expected_output_tokens = resolved.get("expected_output_tokens", [])
        partial_credit_rule = resolved.get("partial_credit_rule")
    else:
        resolved = {"matched": False, "reason": "Not a conditional criterion"}
        extra_expected_outputs = []
        expected_output_tokens = criterion.get("expected_output_tokens", [])
        partial_credit_rule = criterion.get("partial_credit_rule")

    # Bước 2: Lấy thông tin evidence/student_text và danh sách expected_outputs
    # (gộp extra_expected_outputs — đáp án đã resolve từ conditional — vào đầu)
    evidence, student_text, expected_outputs = prepare_output_evidence(
        sample, criterion, extra_expected_outputs
    )

    # Bước 3: Chấm khớp chính xác hoặc theo token + partial credit
    result = grade_exact_expected_token(
        student_text,
        expected_outputs,
        expected_output_tokens,
        max_score,
        partial_credit_rule,
    )

    if result is None:
        return _build_output_criterion_result(
            criterion,
            max_score,
            evidence,
            resolved,
            score=0,
            status="needs_teacher_review",
            reason="No exact match and no expected_output_tokens to grade — requires LLM or teacher review.",
            expected_outputs=expected_outputs,
            detected_errors=[],
        )

    return _build_output_criterion_result(
        criterion,
        max_score,
        evidence,
        resolved,
        expected_outputs=expected_outputs,
        score=result["score"],
        status=result["status"],
        reason=result.get("reason"),
        detected_errors=result.get("detected_errors"),
        expected_output_tokens=result.get("expected_output_tokens"),
        student_tokens=result.get("student_tokens"),
    )


# ==========================================================================================================
# Grader 2: Dùng cho Mode: Logical Reasoning - self_reported_index, conditional_outputs, partial_credit_rule
# ==========================================================================================================


def grade_self_reported_index_criterion(
    sample: Dict[str, Any], criterion: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Chấm criterion có expected_value={"rule": "match_student_index"} — kiểm
    tra STT sinh viên TỰ GHI (ở chính slot_ids của criterion này) có khớp
    STT thật (sample["student_index"]) không. Khác với
    parse_self_reported_index() dùng ở nơi KHÁC (VD T3_main_s2, qua
    condition_source) để LẤY số tự ghi làm căn cứ tính tiếp — ở đây là chấm
    điểm trực tiếp cho việc ghi đúng/sai STT.
    """
    part_label = criterion.get("part_label") or ""
    max_score = criterion.get("score", 0)
    slot_ids = criterion.get("slot_ids", [])

    evidence = get_student_evidence_for_slot(sample, part_label, slot_ids)
    raw_text = evidence.get("student_answer") or ""
    self_reported = parse_self_reported_index(sample, slot_ids)
    true_index = sample.get("student_index")

    is_correct = raw_text == str(true_index)
    score = max_score if is_correct else 0

    if not raw_text:
        reason = "Không ghi STT (bỏ trống)."
    elif self_reported is None:
        reason = f"Ghi '{raw_text}' — không đọc được số nào."
    elif is_correct:
        reason = f"Ghi đúng '{raw_text}', khớp STT thật ({true_index})."
    elif self_reported == true_index:
        reason = (
            f"Ghi '{raw_text}' — đúng số ({self_reported}) nhưng SAI định dạng "
            f"(chỉ được ghi đúng số, VD '{true_index}', không thêm ký tự khác)."
        )
    else:
        reason = f"Ghi '{raw_text}' ({self_reported}) khác STT thật ({true_index})."

    return {
        "criterion_id": criterion.get("criterion_id"),
        "part_label": part_label,
        "criterion_content": criterion.get("content", ""),
        "score": score,
        "max_score": max_score,
        "status": "correct" if is_correct else "wrong",
        "is_correct": is_correct,
        "reason": reason,
        "detected_errors": (
            []
            if is_correct
            else [
                {
                    "error_type": "wrong_self_reported_index",
                    "self_reported": self_reported,
                    "true_index": true_index,
                    "message": reason,
                }
            ]
        ),
    }


def grade_expected_value_criterion(
    sample: Dict[str, Any], criterion: Dict[str, Any]
) -> Dict[str, Any]:
    """
    System 2 - Logical Reasoning: Chấm các câu dạng expected_value (không có
    expected_output/tokens). Hàm này KHÔNG tự quyết điểm — chỉ check từng
    keyword trong expected_value["keywords"] có xuất hiện trong bài làm
    không (matched/missing), dùng làm advisory context cho LLM (qua
    grade_with_llm_advised). Việc so khớp keyword ở đây quá thô
    (substring/word-boundary, không hiểu logic thật) để tin cậy dùng làm
    điểm heuristic thật — LLM mới là người quyết định điểm cuối cùng cho
    loại criterion này.

    `expected_value` chỉ có đúng 2 field khả dụng:
      - "keywords": List[str] — các từ khóa/cụm từ ngắn cần tìm trong bài
        làm, mỗi phần tử quét riêng qua value_matches_student_text().
      - "sample_solution": code mẫu tham khảo (giáo viên cung cấp để LLM đối
        chiếu logic) — KHÔNG bị quét matched/missing (so khớp substring với
        cả 1 khối code nhiều dòng gần như luôn "miss", tạo advisory sai
        lệch); vẫn được đưa vào prompt riêng qua khối "ĐÁP ÁN / LOGIC KỲ
        VỌNG" (_grade_with_llm_advised_core), chỉ không dùng ở đây.

    Các hàm xử lí bao gồm các hàm theo thứ tự:
        1. get_student_evidence_for_slot() — lấy evidence/student_text
        2. value_matches_student_text() — so khớp từng phần tử trong
           expected_value["keywords"] với student_text (KHÔNG normalize,
           dùng nguyên văn)
        3. Dựng dict kết quả: luôn status="needs_teacher_review",
           score=0, kèm matched/missing để LLM tham khảo.

    Không có `is_correct`/`teacher_review_required` riêng — status luôn cố
    định "needs_teacher_review" nên 2 field đó chỉ lặp lại đúng thông tin đã
    có trong status (đã bàn, chốt bỏ — áp dụng chung cho cả Matching/Table).

    Return:
        {
            "criterion_id": str,
            "part_label": str,
            "criterion_content": str,
            "score": 0,
            "max_score": float,
            "status": "needs_teacher_review",
            "matched": List[Dict[str, Any]],  # [{"value": keyword}, ...] đã tìm thấy
            "missing": List[Dict[str, Any]],  # [{"value": keyword}, ...] chưa tìm thấy
            "evidence": Dict[str, Any],  # evidence/student_text
            "reason": str,
            "detected_errors": List[Dict[str, Any]],  # list of detected errors
        }
    Luồng chạy:
        get_student_evidence_for_slot() → value_matches_student_text() cho từng keyword → dựng dict kết quả (score=0, needs_teacher_review)
    """

    part_label = criterion.get("part_label")
    max_score = criterion.get("score", 0)
    expected_value = criterion.get("expected_value", {})
    slot_ids = criterion.get("slot_ids", [])


    evidence = get_student_evidence_for_slot(
        sample, part_label, slot_ids
    )

    student_text = evidence.get("student_answer", "")

    if not expected_value:
        return {
            "criterion_id": criterion.get("criterion_id"),
            "part_label": part_label,
            "criterion_content": criterion.get("content", ""),
            "score": 0,
            "max_score": max_score,
            "status": "needs_teacher_review",
            "reason": "No expected_value provided.",
            "detected_errors": [],
        }

    keywords = expected_value.get("keywords", [])

    matched, missing = [], []
    for kw in keywords:
        if value_matches_student_text(str(kw), student_text):
            matched.append({"value": kw})
        else:
            missing.append({"value": kw})

    reason = (
        f"Found:{len(matched)}/{len(keywords)} expected keywords found: {', '.join(str(m['value']) for m in matched)}."
    )

    return {
        "criterion_id": criterion.get("criterion_id"),
        "part_label": part_label,
        "criterion_content": criterion.get("content", ""),
        "score": 0,
        "max_score": max_score,
        "status": "needs_teacher_review",
        "matched": matched,
        "missing": missing,
        "evidence": evidence,
        "reason": reason,
        "detected_errors": [
            {
                "error_type": "missing_expected_value",
                "expected": m["value"],
                "message": f"Không tìm thấy: {m['value']}.",
            }
            for m in missing
        ],
    }

# ==========================================================================================================
# Grader 3: Dùng cho Mode: Table Reasoning - row_id + column_map + expected_value (CẦN KIỂM TRA LẠI VÌ NÊN CHẤM THEO TỪNG Ô, KHÔNG NÊN CHẤM THEO CẢ HÀNG)
# ==========================================================================================================
def grade_table_criterion(
    sample: Dict[str, Any], criterion: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Chấm criterion dạng table reasoning (row_id + column_map + expected_value)
    1. Lấy evidence/student_text từ slot_ids của criterion (bài làm học sinh)
    2. Nếu không có table nào trong evidence → chấm score=0, status="wrong", reason="No table answer found."
    3. Nếu có table nhưng thiếu row_id/col_id/expected_value → chấm score=0, status="needs_teacher_review", reason="Table criterion thiếu row_id/col_id/expected_value — không xác định được ô
    nào để chấm."
    4. Nếu có đủ row_id + col_id + expected_value → gọi grade_table_row_criterion() để chấm đúng 1 ô, KHÔNG tự quyết correct/wrong bằng so khớp cứng với expected_value (expected_value chỉ là ví dụ gợi ý tham khảo, LLM mới là người quyết định thật).
    5. Trả về dict kết quả chuẩn:
        {
            "criterion_id": str,
            "part_label": str,
            "criterion_content": str,
            "score": float,
            "max_score": float,
            "status": "correct" | "wrong" | "needs_teacher_review",
            "reason": str,
            "evidence": Dict[str, Any],
            "detected_errors": List[Dict[str, Any]],  # list of detected errors
        }
    """
    part_label = criterion.get("part_label")
    max_score = criterion.get("score", 0)
    evidence = get_student_evidence_for_slot(
        sample, part_label, criterion.get("slot_ids", [])
    )
    tables = evidence.get("tables", [])

    if not tables:
        return {
            "criterion_id": criterion.get("criterion_id"),
            "part_label": part_label,
            "criterion_content": criterion.get("content", ""),
            "score": 0,
            "max_score": max_score,
            "status": "wrong",
            "reason": "No table answer found.",
            "detected_errors": [
                {
                    "error_type": "missing_table_answer",
                    "message": "No table answer found in student submission.",
                }
            ],
        }

    row_id = criterion.get("row_id")
    col_id = criterion.get("col_id")
    expected_value = criterion.get("expected_value")

    if row_id and col_id and expected_value is not None:
        return grade_table_row_criterion(
            criterion,
            tables,
            row_id,
            col_id,
            expected_value,
            evidence,
            part_label,
            max_score,
        )

    # Criterion table nhưng thiếu row_id/col_id/expected_value — không đủ cơ
    # sở để xác định chấm ô nào, không đoán mò (không còn nhánh gộp-toàn-bảng
    # thành 1 text để chấm chung — nếu cần kiểm "cả bảng có đủ giá trị hay
    # không", khai nhiều criterion 1-ô riêng rồi gộp all_or_nothing, như
    # T15B1..T15B5).
    return {
        "criterion_id": criterion.get("criterion_id"),
        "part_label": part_label,
        "criterion_content": criterion.get("content", ""),
        "score": 0,
        "max_score": max_score,
        "status": "needs_teacher_review",
        "reason": "Table criterion thiếu row_id/col_id/expected_value — không xác định được ô nào để chấm.",
        "evidence": evidence,
        "detected_errors": [
            {
                "error_type": "incomplete_table_criterion",
                "message": "Criterion table thiếu row_id/col_id/expected_value trong barem.",
            }
        ],
    }


def grade_table_row_criterion(
    criterion: Dict[str, Any],
    tables: List[Dict[str, Any]],
    row_id: str,
    col_id: str,
    expected_value: Any,
    evidence: Dict[str, Any],
    part_label: Optional[str],
    max_score: float,
) -> Dict[str, Any]:
    """
    Hàm chấm 1 ô cụ thể trong table reasoning criterion (row_id + col_id + expected_value).
    Chỉ check xem ô đó có bị bỏ trống hay không, KHÔNG tự quyết correct/wrong bằng so khớp cứng với expected_value (expected_value chỉ là ví dụ gợi ý tham khảo,
    LLM mới là người quyết định thật).
    """
    cells_by_id = {
        cell.get("cell_id"): cell for table in tables for cell in table.get("cells", [])
    }

    cell = cells_by_id.get(f"{row_id}{col_id}")
    cell_text = cell.get("text", "") if cell else ""
    is_blank = cell.get("is_blank", False) if cell else True

    if is_blank or not cell_text.strip():
        return {
            "criterion_id": criterion.get("criterion_id"),
            "part_label": part_label,
            "criterion_content": criterion.get("content", ""),
            "score": 0,
            "max_score": max_score,
            "status": "wrong",
            "row_id": row_id,
            "col_id": col_id,
            "evidence": evidence,
            "reason": f"Ô {row_id}{col_id} bị bỏ trống.",
            "detected_errors": [
                {
                    "error_type": "blank_cell",
                    "row_id": row_id,
                    "col_id": col_id,
                    "message": f"Ô {row_id}{col_id} bị bỏ trống.",
                }
            ],
        }

    return {
        "criterion_id": criterion.get("criterion_id"),
        "part_label": part_label,
        "criterion_content": criterion.get("content", ""),
        "score": 0,
        "max_score": max_score,
        "status": "needs_teacher_review",
        "row_id": row_id,
        "col_id": col_id,
        "student_cell_text": cell_text,
        "evidence": evidence,
        "reason": (
            f"Học sinh viết '{cell_text}' tại {row_id}{col_id} "
            f"(gợi ý mẫu: {expected_value!r}) — cần LLM verify logic, không so khớp cứng."
        ),
        "teacher_review_required": True,
        "detected_errors": [],
    }

# ==========================================================================================================
# Grader 4: Dùng cho Mode: Vision LLM - chấm dựa trên ảnh bài làm (có thể kết hợp với expected_value, grader_note)
# ==========================================================================================================

def _call_vision_llm_for_criterion(
    image_path: str, criterion: Dict[str, Any], retries: int = 2
) -> Dict[str, Any]:
    """Gọi Vision LLM để chấm một criterion dựa trên ảnh bài làm."""
    import base64

    model_name = CFG.get("model_name")
    model_api = CFG.get("model_api")
    api_key = CFG.get("api_key")
    if not model_name or not model_api:
        return {"error": "LLM not configured."}

    if not os.path.exists(image_path):
        return {"error": f"Image file not found: {image_path}"}

    ext = image_path.lower().rsplit(".", 1)[-1]
    mime = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
    }.get(ext, "image/jpeg")
    with open(image_path, "rb") as f:
        b64_image = base64.b64encode(f.read()).decode("utf-8")

    max_score = criterion.get("score", 0)
    criterion_content = criterion.get("content", "")
    grader_note = criterion.get("grader_note", "")
    expected_value = criterion.get("expected_value")

    # Build expected value section
    expected_val_text = ""
    if expected_value and isinstance(expected_value, dict):
        lines = []
        for k, v in expected_value.items():
            if k == "note":
                continue
            if isinstance(v, list):
                lines.append(f"- {k}: {', '.join(str(x) for x in v)}")
            else:
                lines.append(f"- {k}: {v}")
        if expected_value.get("note"):
            lines.append(f"- Lưu ý: {expected_value['note']}")
        expected_val_text = "\n".join(lines)
    elif expected_value:
        expected_val_text = str(expected_value)

    question_text = criterion.get("question_text", "")

    sections = [
        f"=== TIÊU CHÍ ===\n{criterion_content}",
    ]
    if question_text:
        sections.append(f"=== ĐỀ BÀI GỐC ===\n{question_text}")
    if expected_val_text:
        sections.append(f"=== ĐÁP ÁN / CÔNG THỨC KỲ VỌNG ===\n{expected_val_text}")
    if grader_note:
        sections.append(f"=== GHI CHÚ GIÁO VIÊN (BẮT BUỘC TUÂN THỦ) ===\n{grader_note}")
    sections.append(f"=== ĐIỂM TỐI ĐA ===\n{max_score}")

    context_block = "\n\n".join(sections)
    equivalence_note = (
        "NGUYÊN TẮC CHẤM: Chấp nhận mọi cách làm tương đương — "
        "code/công thức khác nhau về hình thức nhưng đúng về kết quả/logic đều được điểm đầy đủ. "
        "Không yêu cầu giống hệt đáp án mẫu."
    )

    # Bước 1 — THINK: suy luận tự do từ ảnh
    grader_intro = _grader_intro(criterion.get("subject", ""))
    think_prompt = (
        f"{grader_intro}. {equivalence_note}\n\n"
        f"{context_block}\n\n"
        "Hãy xem ảnh bài làm và suy luận chi tiết theo các bước:\n"
        "1. Đọc và nhận dạng những gì sinh viên đã viết/vẽ trong ảnh.\n"
        "2. So sánh với tiêu chí và đáp án kỳ vọng — kiểm tra tương đương toán học/logic nếu cần.\n"
        "3. Đánh giá mức độ đúng: hoàn toàn / một phần / sai.\n"
        "4. Kết luận sơ bộ: điểm dự kiến và lý do."
    )

    # Bước 2 — DECIDE: JSON
    decide_system = (
        "You are a grading assistant. Based on the reasoning provided, "
        "output ONLY a valid JSON object. No markdown, no explanation outside the JSON."
    )

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    image_content = {
        "type": "image_url",
        "image_url": {"url": f"data:{mime};base64,{b64_image}"},
    }

    last_error = None
    for attempt in range(retries):
        try:
            # --- THINK ---
            resp_think = requests.post(
                model_api,
                headers=headers,
                json={
                    "model": model_name,
                    "messages": [
                        {
                            "role": "system",
                            "content": f"{grader_intro}. Hãy suy luận chi tiết bằng tiếng Việt.",
                        },
                        {
                            "role": "user",
                            "content": [
                                image_content,
                                {"type": "text", "text": think_prompt},
                            ],
                        }
                    ],
                    "temperature": 0,
                    "max_tokens": CFG.get("cot_max_tokens_think", 600),
                },
                timeout=180,
            )
            resp_think.raise_for_status()
            resp_think_json = resp_think.json()
            cot_reasoning = (
                resp_think_json.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            ).strip()
            think_usage = resp_think_json.get("usage", {})

            if not cot_reasoning:
                raise ValueError("Empty CoT reasoning from Vision LLM.")

            # --- DECIDE ---
            decide_prompt = (
                f"Dựa trên phân tích sau:\n\n{cot_reasoning}\n\n"
                f"Điểm tối đa: {max_score}\n"
                f"Trả về JSON (chỉ JSON):\n"
                f'{{"score": <0 đến {max_score}>, "status": "correct"|"partially_correct"|"wrong", '
                f'"reasoning": "<tóm tắt 1-2 câu>", "confidence": <0.0-1.0>}}'
            )
            resp_decide = requests.post(
                model_api,
                headers=headers,
                json={
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": decide_system},
                        {"role": "user", "content": decide_prompt},
                    ],
                    "temperature": 0,
                    "max_tokens": CFG.get("cot_max_tokens_decide", 300),
                },
                timeout=60,
            )
            resp_decide.raise_for_status()
            resp_decide_json = resp_decide.json()
            decide_text = (
                resp_decide_json.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            ).strip()
            decide_usage = resp_decide_json.get("usage", {})

            parsed = _extract_json_from_text(decide_text)
            if parsed is not None:
                token_usage = {
                    "prompt_tokens": think_usage.get("prompt_tokens", 0)
                    + decide_usage.get("prompt_tokens", 0),
                    "completion_tokens": think_usage.get("completion_tokens", 0)
                    + decide_usage.get("completion_tokens", 0),
                    "total_tokens": think_usage.get("total_tokens", 0)
                    + decide_usage.get("total_tokens", 0),
                }
                parsed.setdefault("score", 0)
                parsed.setdefault("status", "wrong")
                parsed.setdefault("reasoning", "")
                parsed.setdefault("confidence", 0.5)
                parsed["score"] = max(
                    0.0, min(float(parsed["score"]), float(max_score))
                )
                parsed["cot_reasoning"] = cot_reasoning
                parsed["token_usage"] = token_usage
                return parsed

            last_error = f"Cannot parse JSON from decide: {decide_text[:200]}"
        except Exception as e:
            last_error = str(e)
            if attempt < retries - 1:
                continue

    return {"error": last_error}



def grade_visual_criterion(
    sample: Dict[str, Any], criterion: Dict[str, Any]
) -> Dict[str, Any]:
    part_label = criterion.get("part_label")
    max_score = criterion.get("score", 0)
    criterion_id = criterion.get("criterion_id")
    criterion_content = criterion.get("content", "")
    evidence = get_student_evidence_for_slot(
        sample, part_label, criterion.get("slot_ids", [])
    )
    visuals = evidence.get("visual_answers", [])

    if not visuals:
        return {
            "criterion_id": criterion_id,
            "part_label": part_label,
            "criterion_content": criterion_content,
            "score": 0,
            "max_score": max_score,
            "status": "wrong",
            "is_correct": False,
            "reason": "No visual answer found.",
            "teacher_review_required": True,
            "detected_errors": [
                {
                    "error_type": "missing_visual_answer",
                    "message": "No visual answer found.",
                }
            ],
        }

    # Dùng visual đầu tiên tìm được (mỗi slot_id chỉ có 1 ảnh)
    visual = visuals[0]
    image_path = visual.get("image_path", "")

    if not image_path:
        return {
            "criterion_id": criterion_id,
            "part_label": part_label,
            "criterion_content": criterion_content,
            "score": 0,
            "max_score": max_score,
            "status": "needs_vision_teacher_review",
            "is_correct": False,
            "reason": "No image path provided for visual answer.",
            "visual_answers": visuals,
            "teacher_review_required": True,
            "detected_errors": [],
        }

    llm_result = _call_vision_llm_for_criterion(image_path, criterion)

    if "error" in llm_result:
        return {
            "criterion_id": criterion_id,
            "part_label": part_label,
            "criterion_content": criterion_content,
            "score": 0,
            "max_score": max_score,
            "status": "needs_vision_teacher_review",
            "is_correct": False,
            "reason": f"Vision LLM error: {llm_result['error']}",
            "visual_answers": visuals,
            "teacher_review_required": True,
            "detected_errors": [
                {"error_type": "vision_llm_error", "message": llm_result["error"]}
            ],
        }

    score = float(llm_result.get("score", 0))
    status = llm_result.get("status", "wrong")
    confidence = float(llm_result.get("confidence", 0.5))
    reasoning = llm_result.get("reasoning", "")

    needs_review = confidence < CFG.get("teacher_review_threshold", 0.65)

    return {
        "criterion_id": criterion_id,
        "part_label": part_label,
        "criterion_content": criterion_content,
        "score": score,
        "max_score": max_score,
        "status": status,
        "is_correct": score >= max_score,
        "reason": reasoning,
        "confidence": confidence,
        "vision_llm_used": True,
        "image_path": image_path,
        "visual_answers": visuals,
        "teacher_review_required": needs_review,
        "detected_errors": [],
    }

#============================================================================================================
# Hàm phân loại mode chấm điểm dựa vào question_type của criterion, để grade_criterion() gọi đúng hàm grading
#============================================================================================================
def infer_criterion_grading_mode(criterion: Dict[str, Any]) -> str:
    """
    Quyết định mode chấm cho từng criterion, dựa vào question_type của
    CHÍNH CRITERION đó (mỗi ý a/b/c trong rubric tự khai báo question_type
    riêng, VD T15A1=logical, T15B1=table, T15C1=visual — validate_barem()
    đảm bảo mọi criterion đều có).
    """
    qtype = criterion.get("question_type") or "unknown"

    if qtype == "visual":
        return "visual"

    if qtype == "table":
        return "table"

    if qtype == "matching":
        return "expected_output"

    if qtype == "logical":
        return "expected_value"

    return "teacher_review"



# FIX #5: grade_criterion định nghĩa SAU tất cả v2 functions
def grade_criterion(
    sample: Dict[str, Any], criterion: Dict[str, Any]
) -> Dict[str, Any]:
    """Orchestrator: chọn hàm grading phù hợp."""
    mode = infer_criterion_grading_mode(criterion)

    if mode == "expected_output":
        return grade_expected_output_criterion(sample, criterion)
    if mode == "expected_value":
        return grade_expected_value_criterion(sample, criterion)
    if mode == "table":
        return grade_table_criterion(sample, criterion)
    if mode == "visual":
        return grade_visual_criterion(sample, criterion)

    # Needs teacher review
    return {
        "criterion_id": criterion.get("criterion_id"),
        "part_label": criterion.get("part_label"),
        "slot_ids": criterion.get("slot_ids", []),
        "criterion_content": criterion.get("content", ""),
        "score": 0,
        "max_score": criterion.get("score", 0),
        "status": "needs_teacher_review",
        "reason": f"No heuristic grader for this criterion (mode={mode}).",
        "detected_errors": [],
    }


# ============================================================================
# LLM CoT GRADER — FIX #6: tách riêng hàm call_llm_cot, chuẩn hóa output, thêm confidence
# ============================================================================
def call_llm_cot(
    question_context: str,
    criterion_content: str,
    expected_output: Optional[str],
    student_text: str,
    max_score: float,
    subject: str = "",
    retries: int = 3,
    accept_equivalent_solutions: bool = True,
) -> Dict[str, Any]:
    """
    Gọi LLM theo phương pháp Chain-of-Thought (CoT) hai bước:

    Bước 1 — THINK: LLM suy luận tự do, phân tích từng tiêu chí, so sánh
              đáp án học sinh với đáp án kỳ vọng, liệt kê điểm đúng/sai.

    Bước 2 — DECIDE: Dựa trên reasoning ở bước 1, LLM ra quyết định chính thức
              dưới dạng JSON có cấu trúc.

    Returns:
        {
            "cot_reasoning": str,      # suy luận bước 1
            "score": float,
            "status": str,
            "reasoning": str,          # tóm tắt ngắn gọn bước 2
            "confidence": float,
            "cot_used": True,
            "error": str (nếu thất bại)
        }
    """
    model_name = CFG.get("model_name")
    model_api = CFG.get("model_api")
    api_key = CFG.get("api_key")

    if not model_name or not model_api:
        return {"cot_used": False, "error": "LLM not configured."}

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    n_votes = max(1, CFG.get("cot_self_consistency_n", 1))
    votes = []
    last_error = None
    for _ in range(n_votes):
        result, err = _cot_single_pass(
            model_name=model_name,
            model_api=model_api,
            headers=headers,
            criterion_content=criterion_content,
            expected_output=expected_output,
            student_text=student_text,
            max_score=max_score,
            subject=subject,
            question_context=question_context,
            retries=retries,
            accept_equivalent_solutions=accept_equivalent_solutions,
        )
        if result is not None:
            votes.append(result)
        else:
            last_error = err

    if not votes:
        return {
            "cot_used": True,
            "error": last_error,
            "message": f"CoT LLM failed after {n_votes} self-consistency passes: {last_error}",
            "score": 0,
            "status": "error",
            "confidence": 0.0,
            "cot_reasoning": "",
            "token_usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        }

    # Aggregate token_usage across all votes
    agg_usage: Dict[str, int] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    for v in votes:
        u = v.get("token_usage", {})
        for k in agg_usage:
            agg_usage[k] += u.get(k, 0)

    result = _vote_majority(votes)
    result["token_usage"] = agg_usage
    return result


def _vote_majority(votes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Vote đa số theo 'status' giữa các lần gọi LLM độc lập; trong nhóm đồng
    thuận lấy score trung vị. Dùng chung cho cả CoT và LLM gọi đơn (simple)."""
    status_counts: Dict[str, int] = {}
    for v in votes:
        status_counts[v["status"]] = status_counts.get(v["status"], 0) + 1
    majority_status = max(status_counts.items(), key=lambda kv: kv[1])[0]

    agreeing = sorted(
        (v for v in votes if v["status"] == majority_status), key=lambda v: v["score"]
    )
    chosen = dict(agreeing[len(agreeing) // 2])
    chosen["self_consistency_votes"] = [
        {"score": v["score"], "status": v["status"]} for v in votes
    ]
    return chosen


def _cot_single_pass(
    model_name: str,
    model_api: str,
    headers: Dict[str, str],
    criterion_content: str,
    expected_output: Optional[str],
    student_text: str,
    max_score: float,
    question_context: str,
    retries: int,
    subject: str = "",
    accept_equivalent_solutions: bool = True,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Một lần đầy đủ THINK+DECIDE (có retry nội bộ khi lỗi mạng/parse JSON).
    Trả (result, None) nếu thành công, (None, error_message) nếu thất bại hết retries.

    accept_equivalent_solutions: chỉ hợp lý cho criterion có NHIỀU cách làm
    đúng khác nhau (Logical: nhiều cách viết code cùng đúng logic; Table:
    nhiều ví dụ Input/Output khác nhau vẫn đúng quan hệ toán học). KHÔNG hợp
    lý cho Matching — output chương trình là 1 giá trị CỐ ĐỊNH DUY NHẤT,
    không có khái niệm "cách viết tương đương" cho cùng 1 con số; để nguyên
    câu này trong prompt Matching dễ khiến LLM quá dễ dãi, tự lý giải 1 đáp
    số sai là "tương đương" đáp số đúng. `grade_matching_with_llm` truyền
    `False`; các wrapper còn lại giữ mặc định `True`.
    """
    # ── Bước 1: THINK ──────────────────────────────────────────────────────
    # FIX: siết lại — "tương đương" từng bị LLM diễn giải quá rộng, cho điểm
    # đầy đủ cả code THIẾU/không biên dịch được (VD thiếu tham số hàm, thiếu
    # phần tăng vòng lặp, thiếu dấu đóng ngoặc) chỉ vì "logic hướng đúng",
    # nhầm lẫn với case hợp lệ thật (VD i<=n/2 thay vì i*i<n — khác cách viết
    # nhưng ĐẦY ĐỦ và ĐÚNG). Thêm câu phân định rõ ranh giới này.
    equivalence_note = (
        "\nNGUYÊN TẮC CHẤM: Chấp nhận mọi cách làm tương đương — code/công thức/thuật toán "
        "khác nhau về hình thức nhưng đúng về kết quả và logic đều được điểm đầy đủ. "
        "Không yêu cầu giống hệt đáp án mẫu.\n"
        "LƯU Ý QUAN TRỌNG: nguyên tắc trên CHỈ áp dụng khi code/logic THỰC SỰ ĐÚNG VÀ "
        "ĐẦY ĐỦ, chỉ khác cách viết (VD khác điều kiện vòng lặp nhưng cùng kết quả). "
        "KHÔNG áp dụng cho code THIẾU SÓT hoặc KHÔNG THỂ BIÊN DỊCH ĐƯỢC (thiếu tham số "
        "hàm, thiếu phần tăng của vòng lặp, thiếu dấu đóng ngoặc/dấu ) làm sai cấu trúc, "
        "thiếu chỉ số mảng...) — những trường hợp này PHẢI bị trừ điểm tương ứng mức độ "
        "thiếu sót, không được coi là \"tương đương\" chỉ vì hướng đi đúng.\n"
        if accept_equivalent_solutions
        else ""
    )
    grader_intro = _grader_intro(subject)
    think_prompt = f"""{grader_intro} đang phân tích bài làm.
Hãy SUY LUẬN CHI TIẾT từng bước trước khi đưa ra điểm số.
{equivalence_note}
=== TIÊU CHÍ CHẤM ===
{criterion_content}

=== ĐÁP ÁN KỲ VỌNG ===
{expected_output if expected_output is not None else "(không có đáp án cố định)"}

=== BÀI LÀM HỌC SINH ===
{student_text if student_text else "(trống — học sinh không trả lời)"}

=== ĐIỂM TỐI ĐA ===
{max_score}

{question_context if question_context else ""}

Hãy suy luận tuần tự theo các bước sau (viết rõ từng bước):
1. Đọc và hiểu tiêu chí: tiêu chí này yêu cầu gì?
2. Phân tích đáp án kỳ vọng (nếu có): cần khớp điều gì?
3. Phân tích bài làm học sinh: học sinh đã làm gì, đúng chỗ nào, sai chỗ nào?
4. Kiểm tra tương đương: nếu bài làm khác đáp án mẫu, kiểm tra xem kết quả/logic có tương đương không.
5. So sánh: mức độ khớp giữa bài làm và tiêu chí/đáp án kỳ vọng là bao nhiêu?
6. Kết luận sơ bộ: điểm dự kiến và lý do."""

    # ── Bước 2: DECIDE ─────────────────────────────────────────────────────
    decide_system_prompt = (
        "You are a grading assistant. Based on the reasoning provided, "
        "output ONLY a valid JSON object. No markdown, no explanation outside the JSON."
    )

    last_error = None
    for attempt in range(retries):
        try:
            # --- Bước 1: lấy reasoning ---
            payload_think = {
                "model": model_name,
                "messages": [
                    {
                        "role": "system",
                        "content": f"{grader_intro}. Hãy suy luận chi tiết bằng tiếng Việt.",
                    },
                    {"role": "user", "content": think_prompt},
                ],
                "temperature": 0,
                "max_tokens": CFG.get("cot_max_tokens_think", 600),
            }
            resp_think = requests.post(
                model_api, headers=headers, json=payload_think, timeout=120
            )
            resp_think.raise_for_status()

            resp_think_json = resp_think.json()
            cot_reasoning = (
                resp_think_json.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            ).strip()
            think_usage = resp_think_json.get("usage", {})

            if not cot_reasoning:
                raise ValueError("Empty CoT reasoning from LLM.")

            # --- Bước 2: ra quyết định dựa trên reasoning ---
            decide_prompt = f"""Dựa trên phân tích sau đây:

--- BẮT ĐẦU PHÂN TÍCH ---
{cot_reasoning}
--- KẾT THÚC PHÂN TÍCH ---

Hãy đưa ra quyết định chấm điểm chính thức.
Điểm tối đa: {max_score}

Trả về JSON (và CHỈ JSON):
{{
  "score": <số thực từ 0 đến {max_score}>,
  "status": "<correct|partially_correct|wrong>",
  "reasoning": "<tóm tắt lý do ngắn gọn 1-2 câu>",
  "confidence": <số thực từ 0.0 đến 1.0>,
  "feedback": "<nếu sai hoặc thiếu điểm: liệt kê cụ thể điểm nào sai/thiếu; để chuỗi rỗng nếu đúng hoàn toàn>",
  "suggestion": "<nếu sai hoặc thiếu điểm: hướng dẫn cách sửa cụ thể; để chuỗi rỗng nếu đúng hoàn toàn>"
}}"""

            payload_decide = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": decide_system_prompt},
                    {"role": "user", "content": decide_prompt},
                ],
                "temperature": 0,
                "max_tokens": CFG.get("cot_max_tokens_decide", 300),
            }
            resp_decide = requests.post(
                model_api, headers=headers, json=payload_decide, timeout=60
            )
            resp_decide.raise_for_status()

            resp_decide_json = resp_decide.json()
            decide_text = (
                resp_decide_json.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            ).strip()
            decide_usage = resp_decide_json.get("usage", {})

            parsed = _extract_json_from_text(decide_text)
            if parsed is not None:
                token_usage = {
                    "prompt_tokens": think_usage.get("prompt_tokens", 0)
                    + decide_usage.get("prompt_tokens", 0),
                    "completion_tokens": think_usage.get("completion_tokens", 0)
                    + decide_usage.get("completion_tokens", 0),
                    "total_tokens": think_usage.get("total_tokens", 0)
                    + decide_usage.get("total_tokens", 0),
                }
                return {
                    "cot_reasoning": cot_reasoning,
                    "score": min(float(parsed.get("score", 0)), max_score),
                    "status": parsed.get("status", "wrong"),
                    "reasoning": parsed.get("reasoning", ""),
                    "confidence": float(parsed.get("confidence", 0.7)),
                    "feedback": parsed.get("feedback", ""),
                    "suggestion": parsed.get("suggestion", ""),
                    "cot_used": True,
                    "token_usage": token_usage,
                }, None

            last_error = f"Cannot parse JSON from decide step: {decide_text[:200]}"

        except Exception as e:
            last_error = str(e)
            if attempt < retries - 1:
                continue

    return None, last_error


def call_llm_simple(
    question_context: str,
    criterion_content: str,
    expected_output: Optional[str],
    student_text: str,
    max_score: float,
    subject: str = "",
    retries: int = 3,
    accept_equivalent_solutions: bool = True,
) -> Dict[str, Any]:
    """
    Gọi LLM 1 bước duy nhất (KHÔNG có THINK/DECIDE riêng) — dùng khi
    CFG["use_chain_of_thought"] = False. Rẻ và nhanh hơn call_llm_cot()
    (1 lần gọi/vote thay vì 2), đánh đổi bằng việc LLM không suy luận tường
    minh trước khi chấm — dễ sai hơn với criterion cần lập luận nhiều bước
    (code, essay). Vẫn áp dụng self-consistency vote giống call_llm_cot().

    `accept_equivalent_solutions` nhận vào để giữ chữ ký giống call_llm_cot()
    (`_grade_with_llm_advised_core` gọi `llm_call(...)` qua 1 biến trỏ tới 1
    trong 2 hàm này, cùng bộ kwargs) — nhưng KHÔNG dùng, vì prompt 1-bước
    của hàm này chưa từng có câu "chấp nhận cách làm tương đương" để bật/tắt.
    """
    model_name = CFG.get("model_name")
    model_api = CFG.get("model_api")
    api_key = CFG.get("api_key")
    if not model_name or not model_api:
        return {"cot_used": False, "error": "LLM not configured."}

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    grader_intro = _grader_intro(subject)
    prompt = f"""{grader_intro}. Hãy chấm bài làm sau và trả về JSON.

=== TIÊU CHÍ CHẤM ===
{criterion_content}

=== ĐÁP ÁN KỲ VỌNG ===
{expected_output if expected_output is not None else "(không có đáp án cố định)"}

=== BÀI LÀM HỌC SINH ===
{student_text if student_text else "(trống — học sinh không trả lời)"}

=== ĐIỂM TỐI ĐA ===
{max_score}

{question_context if question_context else ""}

Trả về JSON (và CHỈ JSON):
{{
  "score": <số thực từ 0 đến {max_score}>,
  "status": "<correct|partially_correct|wrong>",
  "reasoning": "<lý do ngắn gọn 1-2 câu>",
  "confidence": <số thực từ 0.0 đến 1.0>,
  "feedback": "<nếu sai hoặc thiếu điểm: liệt kê cụ thể điểm nào sai/thiếu; để chuỗi rỗng nếu đúng hoàn toàn>",
  "suggestion": "<nếu sai hoặc thiếu điểm: hướng dẫn cách sửa cụ thể; để chuỗi rỗng nếu đúng hoàn toàn>"
}}"""

    n_votes = max(1, CFG.get("cot_self_consistency_n", 1))
    votes = []
    last_error = None
    for _ in range(n_votes):
        for attempt in range(retries):
            try:
                payload = {
                    "model": model_name,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a grading assistant. Output ONLY a valid JSON object.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0,
                    "max_tokens": CFG.get("cot_max_tokens_decide", 300),
                }
                resp = requests.post(
                    model_api, headers=headers, json=payload, timeout=60
                )
                resp.raise_for_status()
                text = (
                    resp.json()
                    .get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                ).strip()
                parsed = _extract_json_from_text(text)
                if parsed is not None:
                    votes.append(
                        {
                            "cot_reasoning": "",
                            "score": min(float(parsed.get("score", 0)), max_score),
                            "status": parsed.get("status", "wrong"),
                            "reasoning": parsed.get("reasoning", ""),
                            "confidence": float(parsed.get("confidence", 0.7)),
                            "feedback": parsed.get("feedback", ""),
                            "suggestion": parsed.get("suggestion", ""),
                            "cot_used": False,
                        }
                    )
                    break
                last_error = f"Cannot parse JSON: {text[:200]}"
            except Exception as e:
                last_error = str(e)
                if attempt < retries - 1:
                    continue

    if not votes:
        return {
            "cot_used": False,
            "error": last_error,
            "message": f"Simple LLM call failed after {n_votes} passes: {last_error}",
            "score": 0,
            "status": "error",
            "confidence": 0.0,
            "cot_reasoning": "",
        }

    return _vote_majority(votes)


def call_llm_table_batch(
    table_text: str,
    criteria_specs: List[Dict[str, Any]],
    retries: int = 3,
    question_text: str = "",
    subject: str = "",
) -> Dict[str, Any]:
    """
    Chấm TẤT CẢ criteria cùng 1 bảng trong ĐÚNG 1 lần "vòng" gọi LLM (2 bước
    THINK+DECIDE, giống `_cot_single_pass`) — để LLM thấy toàn bộ nội dung
    bảng (mọi hàng/cột) khi quyết định, thay vì mỗi ô/hàng gọi LLM riêng biệt
    hoàn toàn tách rời nhau (không thể verify quan hệ giữa các ô, VD
    Input↔Output cùng hàng phải khớp logic bài toán).

    Bước 1 — THINK: LLM suy luận tự do qua từng hàng/ô, so sánh với đáp án
              gợi ý VÀ quan hệ giữa các ô liên quan trong cùng hàng.
    Bước 2 — DECIDE: dựa trên reasoning ở bước 1, LLM ra quyết định chính
              thức dưới dạng JSON có cấu trúc, 1 entry / criterion_id.

    criteria_specs: [{"criterion_id", "content", "row_id", "col_id",
                       "expected_value", "max_score"}, ...]

    Không áp dụng self-consistency vote (khác call_llm_cot/call_llm_simple)
    — batch nhiều criterion/lần gọi đã phức tạp hơn, giữ đơn giản 1 vote.

    Return: {"results": {criterion_id: {"score","status","reasoning"}, ...},
             "cot_reasoning": str, "token_usage": {...}}
            hoặc {"error": str} nếu thất bại.
    """
    model_name = CFG.get("model_name")
    model_api = CFG.get("model_api")
    api_key = CFG.get("api_key")
    if not model_name or not model_api:
        return {"error": "LLM not configured."}

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    criteria_text = "\n".join(
        f"- criterion_id=\"{c['criterion_id']}\": {c.get('content','')}\n"
        f"    Vị trí cần kiểm tra: hàng {c.get('row_id')}, cột {c.get('col_id')}\n"
        f"    Đáp án gợi ý (ví dụ tham khảo, KHÔNG bắt buộc khớp y hệt): {c.get('expected_value')!r}\n"
        f"    Điểm tối đa: {c.get('max_score')}"
        for c in criteria_specs
    )
    result_shape = ",\n".join(
        f'    "{c["criterion_id"]}": {{"score": <0..{c.get("max_score")}>, "status": "correct|partially_correct|wrong", "reasoning": "..."}}'
        for c in criteria_specs
    )

    question_text_block = f"\n=== ĐỀ BÀI GỐC ===\n{question_text}\n" if question_text else ""

    # ── Bước 1: THINK ────────────────────────────────────────────────────
    grader_intro = _grader_intro(subject)
    think_prompt = f"""{grader_intro}. Dưới đây là TOÀN BỘ nội dung 1 bảng bài làm học sinh. Hãy SUY LUẬN CHI TIẾT từng bước trước khi đưa ra điểm số — dùng ngữ cảnh CẢ BẢNG (VD quan hệ giữa các ô cùng hàng) để chấm, KHÔNG chỉ so khớp chuỗi cứng với "đáp án gợi ý" (chỉ là 1 ví dụ tham khảo, KHÔNG phải đáp án bắt buộc) — nếu học sinh chọn ví dụ khác nhưng vẫn đúng logic/quan hệ toán học giữa các ô liên quan, vẫn tính đúng.
{question_text_block}
=== TOÀN BỘ NỘI DUNG BẢNG ===
{table_text}

=== DANH SÁCH Ô CẦN CHẤM ===
{criteria_text}

Hãy suy luận tuần tự theo các bước sau, LẦN LƯỢT QUA TỪNG criterion_id (viết rõ từng bước):
1. Đọc vị trí và đáp án gợi ý của ô này (chỉ là ví dụ tham khảo, không bắt buộc khớp y hệt).
2. Đối chiếu với giá trị thật học sinh viết trong bảng ở đúng vị trí đó.
3. Nếu ô này liên quan tới ô khác cùng hàng (VD Input↔Output), kiểm tra quan hệ/logic toán học giữa 2 ô có nhất quán không — dù giá trị có khác đáp án mẫu.
4. Kết luận sơ bộ cho criterion_id này: đúng/sai/1 phần, vì sao."""

    decide_system_prompt = (
        "You are a grading assistant. Based on the reasoning provided, "
        "output ONLY a valid JSON object. No markdown, no explanation outside the JSON."
    )

    last_error = None
    for attempt in range(retries):
        try:
            payload_think = {
                "model": model_name,
                "messages": [
                    {
                        "role": "system",
                        "content": f"{grader_intro}. Hãy suy luận chi tiết bằng tiếng Việt.",
                    },
                    {"role": "user", "content": think_prompt},
                ],
                "temperature": 0,
                "max_tokens": CFG.get("cot_max_tokens_think", 600) * max(1, len(criteria_specs)),
            }
            resp_think = requests.post(model_api, headers=headers, json=payload_think, timeout=120)
            resp_think.raise_for_status()
            resp_think_json = resp_think.json()
            cot_reasoning = (
                resp_think_json.get("choices", [{}])[0].get("message", {}).get("content", "")
            ).strip()
            think_usage = resp_think_json.get("usage", {})

            if not cot_reasoning:
                raise ValueError("Empty CoT reasoning from LLM.")

            # ── Bước 2: DECIDE ──────────────────────────────────────────
            decide_prompt = f"""Dựa trên phân tích sau đây:

--- BẮT ĐẦU PHÂN TÍCH ---
{cot_reasoning}
--- KẾT THÚC PHÂN TÍCH ---

Hãy đưa ra quyết định chấm điểm chính thức cho TỪNG criterion_id.

Trả về JSON (và CHỈ JSON) — đúng 1 entry cho MỖI criterion_id ở trên:
{{
{result_shape}
}}"""

            payload_decide = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": decide_system_prompt},
                    {"role": "user", "content": decide_prompt},
                ],
                "temperature": 0,
                "max_tokens": CFG.get("cot_max_tokens_decide", 300) * max(1, len(criteria_specs)),
            }
            resp_decide = requests.post(model_api, headers=headers, json=payload_decide, timeout=90)
            resp_decide.raise_for_status()
            resp_decide_json = resp_decide.json()
            decide_text = (
                resp_decide_json.get("choices", [{}])[0].get("message", {}).get("content", "")
            ).strip()
            decide_usage = resp_decide_json.get("usage", {})

            parsed = _extract_json_from_text(decide_text)
            if parsed is None:
                last_error = f"Cannot parse JSON from decide step: {decide_text[:200]}"
                continue

            results = {}
            for c in criteria_specs:
                cid = c["criterion_id"]
                entry = parsed.get(cid) or {}
                results[cid] = {
                    "score": clamp_score(float(entry.get("score", 0)), 0, c.get("max_score", 0)),
                    "status": entry.get("status", "wrong"),
                    "reasoning": entry.get("reasoning", ""),
                }

            return {
                "results": results,
                "cot_reasoning": cot_reasoning,
                "token_usage": {
                    "prompt_tokens": think_usage.get("prompt_tokens", 0)
                    + decide_usage.get("prompt_tokens", 0),
                    "completion_tokens": think_usage.get("completion_tokens", 0)
                    + decide_usage.get("completion_tokens", 0),
                    "total_tokens": think_usage.get("total_tokens", 0)
                    + decide_usage.get("total_tokens", 0),
                },
            }
        except Exception as e:
            last_error = str(e)
            continue

    return {"error": last_error}


_VALID_LLM_STATUSES = {"correct", "partially_correct", "wrong"}


def _blend_heuristic_and_llm(
    h_score: float,
    llm_score_raw: float,
    raw_status: str,
    max_score: float,
    question_type: Optional[str] = None,
) -> Tuple[float, str, float, str, bool]:
    """Blend điểm heuristic + LLM theo trọng số CFG['heuristic_weight'] —
    hoặc override theo `question_type` qua CFG['heuristic_weight_by_type']
    nếu có khai (VD Logical/Table = 0.0, vì heuristic 2 loại này không bao
    giờ có điểm thật, chỉ là placeholder — xem comment ở CFG). Validate
    status LLM trả về (suy ra từ score nếu status lạ, không tin mù). Dùng
    chung cho cả `_grade_with_llm_advised_core` (1 criterion/lần gọi LLM) và
    `grade_table_group_with_llm` (nhiều criterion cùng bảng/1 lần gọi LLM) —
    tránh lặp lại công thức blend ở 2 nơi.

    Return: (score, status, llm_score, llm_status, status_corrected)
    """
    llm_score = clamp_score(float(llm_score_raw), 0, max_score)
    if raw_status in _VALID_LLM_STATUSES:
        llm_status = raw_status
        status_corrected = False
    else:
        llm_status = (
            "correct"
            if llm_score == max_score
            else ("partially_correct" if llm_score > 0 else "wrong")
        )
        status_corrected = True

    heuristic_weight = CFG.get("heuristic_weight_by_type", {}).get(
        question_type
    )
    score = clamp_score(
        heuristic_weight * h_score + (1 - heuristic_weight) * llm_score, 0, max_score
    )
    status = (
        "correct" if score == max_score else ("partially_correct" if score > 0 else "wrong")
    )
    return score, status, llm_score, llm_status, status_corrected


# ============================================================================
# SYSTEM 4: LLM + Heuristic Advisory
# Luồng chạy:
#
# ============================================================================


def _grade_with_llm_advised_core(
    sample: Dict[str, Any],
    criterion: Dict[str, Any],
    heuristic_result: Dict[str, Any],
    *,
    extra_prompt_text: str = "",
    extra_result_fields: Optional[Dict[str, Any]] = None,
    expected_outputs_override: Optional[List[str]] = None,
    accept_equivalent_solutions: bool = True,
    show_heuristic_score_status: bool = True,
    heuristic_reason_label: str = "Lý do       ",
) -> Dict[str, Any]:
    """
    SYSTEM 4 (CoT + Heuristic Advisory) — lõi dùng chung cho llm-router
    (`grade_criterion_with_llm`): gọi LLM với Chain-of-Thought reasoning +
    heuristic advisory context, blend điểm, validate status. Phần build
    prompt/giữ field cấu trúc RIÊNG theo từng loại grader (matched/missing,
    row_id, expected_output_tokens/student_tokens...) do các hàm
    `grade_*_with_llm` chuẩn bị và
    truyền vào qua `extra_prompt_text`/`extra_result_fields`/
    `expected_outputs_override` — hàm này không tự biết grader nào gọi tới.

    `accept_equivalent_solutions`: có chèn câu "chấp nhận cách làm tương
    đương" vào prompt CoT hay không (xem docstring `_cot_single_pass`) —
    mặc định `True` (hợp lý cho Logical/Table, nhiều cách làm đúng khác
    nhau); `grade_matching_with_llm` truyền `False` vì Matching chỉ có 1
    đáp số cố định, không có khái niệm "tương đương".
    """
    criterion_id = criterion.get("criterion_id", "unknown")
    part_label = criterion.get("part_label", "main")
    max_score = criterion.get("score", 0)

    evidence = get_student_evidence_for_slot(
        sample, part_label, criterion.get("slot_ids")
    )
    student_text = evidence.get("student_answer", "")

    # FIX: evidence.text rỗng khi câu trả lời là bảng/hình vẽ (table/visual) —
    # get_student_evidence_for_slot() chỉ ghép text từ lines/tokens, không từ
    # tables/visual_answers. Nếu không build fallback, LLM sẽ thấy "trống" dù
    # SV đã trả lời đầy đủ trong bảng (VD câu 15b).
    if not student_text.strip() and evidence.get("tables"):
        student_text = " | ".join(
            f"{cell.get('cell_id', '')}={cell.get('text', '')}"
            for table in evidence["tables"]
            for cell in table.get("cells", [])
            if not cell.get("is_blank", False) and cell.get("text", "")
        )
    if not student_text.strip() and evidence.get("visual_answers"):
        student_text = " | ".join(
            v.get("ocr_text_inside", "") or v.get("note", "")
            for v in evidence["visual_answers"]
        ).strip()

    has_any_evidence = bool(student_text.strip())

    # Blank check — không cần LLM
    if (
        evidence.get("is_blank")
        or evidence.get("type") == "blank"
        or not has_any_evidence
    ):
        return {
            "criterion_id": criterion_id,
            "part_label": part_label,
            "criterion_content": criterion.get("content", ""),
            "score": 0,
            "max_score": max_score,
            "status": "wrong",
            "is_correct": False,
            "llm_used": False,
            "grading_method": "blank_skip",
            "stage": "heuristic",
            "llm_reasoning": "Student left this part blank.",
            "cot_reasoning": "",
            "confidence": 1.0,
            "heuristic_score": heuristic_result.get("score", 0),
            "heuristic_status": heuristic_result.get("status", "wrong"),
            "evidence": evidence,
            "detected_errors": [
                {
                    "error_type": "blank_answer",
                    "message": "Sinh viên không làm phần này.",
                }
            ],
        }

    # Chuẩn bị heuristic advisory
    h_score = heuristic_result.get("score", 0)
    h_status = heuristic_result.get("status", "unknown")
    h_reason = heuristic_result.get("reason", "")

    # expected_outputs: cho phép wrapper theo grader (VD Matching với
    # conditional_outputs) override bằng giá trị đã resolve theo
    # student_index qua expected_outputs_override — nếu không có override,
    # dùng thẳng expected_outputs tĩnh khai báo trong criterion.
    expected_outputs = expected_outputs_override or criterion.get("expected_outputs") or []
    expected_output = " / ".join(expected_outputs) if expected_outputs else None
    grader_note = criterion.get("grader_note", "")
    partial_credit_rule = criterion.get("partial_credit_rule")
    criterion_content = criterion.get("content", "N/A")

    # FIX: expected_value (mô tả logic/công thức kỳ vọng) chưa từng được đưa
    # vào prompt của grade_with_llm_advised — trước đây chỉ criterion (visual,
    # qua _call_vision_llm_for_criterion) mới thấy được. Với tiêu chí "code"
    # (T13/T14...), LLM trước đây chỉ có 1 dòng content ngắn, phải tự đoán
    # logic đúng là gì — dễ hallucinate yêu cầu sai.
    expected_value = criterion.get("expected_value")
    expected_value_text = ""
    if expected_value and isinstance(expected_value, dict):
        lines = []
        for k, v in expected_value.items():
            # sample_solution là code mẫu THAM KHẢO, không phải đáp án bắt
            # buộc khớp y hệt — gắn caveat ngay tại chỗ hiển thị (thay vì chỉ
            # dựa vào equivalence_note chung ở đầu prompt) để LLM không hiểu
            # nhầm đây là 1 tiêu chí "đáp án" như các key khác trong cùng khối.
            if k == "sample_solution":
                lines.append(
                    f"- Đáp án mẫu tham khảo (CHỈ THAM KHẢO để đối chiếu logic, "
                    f"KHÔNG yêu cầu bài học sinh giống hệt): {v}"
                )
            elif isinstance(v, list):
                lines.append(f"- {k}: {', '.join(str(x) for x in v)}")
            elif isinstance(v, dict):
                lines.append(f"- {k}: {json.dumps(v, ensure_ascii=False)}")
            else:
                lines.append(f"- {k}: {v}")
        expected_value_text = "\n".join(lines)
    elif expected_value:
        expected_value_text = str(expected_value)

    # FIX: question_text (đề bài GỐC của cả câu, VD toàn bộ code chương trình
    # cần trace ở câu 1-12) chưa từng được đưa vào prompt — LLM chấm câu
    # "chương trình này in ra gì" mà chưa từng thấy chính chương trình đó,
    # chỉ thấy criterion_content (mô tả ngắn) + đáp án đúng cho sẵn, không
    # có cách nào tự verify độc lập. Gắn từ _attach_question_text() ở
    # load_barem().
    question_text = criterion.get("question_text", "")

    # FIX: grader_note/partial_credit_rule đã được đọc nhưng trước đây không hề
    # đưa vào prompt — đây là nơi giáo viên ghi rõ các trường hợp biên (VD "n<2
    # thì không phải SNT") mà LLM hay hallucinate ra yêu cầu sai vì thiếu thông
    # tin này (đã quan sát ở câu T13A1, T8B, T13C2).
    teacher_rule_text = ""
    if question_text:
        teacher_rule_text += f"\n══ ĐỀ BÀI GỐC ══\n{question_text}"
    if expected_value_text:
        teacher_rule_text += f"\n══ ĐÁP ÁN / LOGIC KỲ VỌNG ══\n{expected_value_text}"
    if grader_note:
        teacher_rule_text += (
            f"\n══ GHI CHÚ CỦA GIÁO VIÊN (BẮT BUỘC TUÂN THỦ) ══\n{grader_note}"
        )
    if partial_credit_rule:
        teacher_rule_text += f"\n══ QUY TẮC ĐIỂM BÁN PHẦN ══\n{json.dumps(partial_credit_rule, ensure_ascii=False)}"

    # Xây dựng question_context với advisory từ heuristic (cho CoT reasoning)
    heuristic_advisory_lines = []
    if show_heuristic_score_status:
        heuristic_advisory_lines.append(f"Score gợi ý : {h_score}/{max_score}")
        heuristic_advisory_lines.append(f"Status gợi ý: {h_status}")
    heuristic_advisory_lines.append(f"{heuristic_reason_label}: {h_reason}{extra_prompt_text}")
    heuristic_advisory_block = "\n".join(heuristic_advisory_lines)

    question_context = f"""══ GỢI Ý TỪ HEURISTIC GRADER ══
{heuristic_advisory_block}
{teacher_rule_text}

══ HƯỚNG DẪN CHAIN-OF-THOUGHT ══
1. Trước hết, suy luận độc lập mà KHÔNG bị ảnh hưởng bởi gợi ý
2. Phân tích chi tiết từng tiêu chí, so sánh bài làm với tiêu chuẩn
3. PHẢI tuân thủ đúng "GHI CHÚ CỦA GIÁO VIÊN" và "QUY TẮC ĐIỂM BÁN PHẦN" nếu có — không tự đặt thêm yêu cầu ngoài tiêu chí đã cho.
4. Sau khi suy luận xong, so sánh kết luận của bạn với gợi ý của Heuristic:
   - Nếu bạn đồng ý → hãy giải thích tại sao
   - Nếu bạn không đồng ý → giải thích tại sao gợi ý có thể không chính xác
5. Đưa ra quyết định cuối cùng dựa trên suy luận của bạn"""

    try:
        # FIX: nối CFG["use_chain_of_thought"] vào logic thật — trước đây flag
        # này tồn tại nhưng không được đọc ở đâu, CoT luôn chạy bất kể giá trị.
        llm_call = (
            call_llm_cot if CFG.get("use_chain_of_thought", True) else call_llm_simple
        )
        cot_result = llm_call(
            question_context=question_context,
            criterion_content=criterion_content,
            expected_output=expected_output,
            student_text=student_text,
            max_score=max_score,
            subject=criterion.get("subject", ""),
            retries=3,
            accept_equivalent_solutions=accept_equivalent_solutions,
        )

        # Kiểm tra lỗi từ LLM (cot_used=False ở nhánh simple là bình thường,
        # không phải lỗi — chỉ "error" key mới biểu thị thất bại thật)
        if "error" in cot_result:
            # CoT fail → fallback heuristic
            fallback = dict(heuristic_result)
            fallback["grading_method"] = "heuristic_llm_failed"
            fallback["stage"] = "llm_failed"
            fallback["llm_used"] = False
            fallback["llm_error"] = cot_result.get("error", "CoT LLM failed")
            fallback["cot_reasoning"] = ""
            if fallback.get("status") in TRANSIENT_REVIEW_STATUSES:
                # Không ai từng ra quyết định thật cho tiêu chí này (heuristic
                # "chưa biết", LLM cũng fail) — không được lặng lẽ tính điểm
                # 0 = "wrong" definitive, phải bắt buộc giáo viên xem lại.
                fallback["status"] = "wrong"
                fallback["teacher_review_required"] = True
            return fallback

        # FIX #7/#8 + blend: xem docstring _blend_heuristic_and_llm — clamp
        # score LLM cả 2 chiều, validate status LLM (suy ra từ score nếu lạ),
        # rồi blend với heuristic theo CFG["heuristic_weight"]/["heuristic_weight_by_type"].
        question_type = criterion.get("question_type")
        score, status, llm_score, llm_status, status_corrected = _blend_heuristic_and_llm(
            h_score, cot_result.get("score", h_score), cot_result.get("status", "wrong"), max_score,
            question_type,
        )
        heuristic_weight = CFG.get("heuristic_weight_by_type", {}).get(
            question_type, CFG.get("heuristic_weight", 0.5)
        )
        raw_status = cot_result.get("status", "wrong")

        reasoning = cot_result.get("reasoning", "")
        cot_reason = cot_result.get("cot_reasoning", "")
        confidence = float(cot_result.get("confidence", 0.8))
        feedback = cot_result.get("feedback", "")
        suggestion = cot_result.get("suggestion", "")
        token_usage = cot_result.get(
            "token_usage",
            {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )

        # Kiểm tra xem LLM (trước khi blend) có đồng ý với heuristic không —
        # so trên llm_score/llm_status GỐC, không phải score đã blend (blend
        # luôn kéo gần heuristic hơn nên so trên score sẽ đánh giá sai lệch).
        agreed_with_heuristic = (
            abs(llm_score - h_score) < 0.01 and llm_status == h_status
        )

        result = {
            "criterion_id": criterion_id,
            "part_label": part_label,
            "criterion_content": criterion.get("content", ""),
            "score": round(score, 4),
            "max_score": max_score,
            "status": status,
            "is_correct": score == max_score,
            "llm_used": True,
            "grading_method": (
                "llm_advised_cot"
                if cot_result.get("cot_used")
                else "llm_advised_simple"
            ),
            "stage": "llm",
            "llm_reasoning": reasoning,
            "cot_reasoning": cot_reason,
            "feedback": feedback,
            "suggestion": suggestion,
            "agreed_with_heuristic": agreed_with_heuristic,
            "confidence": confidence,
            "heuristic_score": h_score,
            "heuristic_status": h_status,
            "heuristic_reason": h_reason,
            "heuristic_weight": heuristic_weight,
            "llm_score": round(llm_score, 4),
            "llm_status": llm_status,
            "token_usage": token_usage,
            "evidence": evidence,
            "status_corrected": status_corrected,
            "detected_errors": (
                [
                    {
                        "error_type": "invalid_llm_status",
                        "message": f"LLM trả về status không hợp lệ: '{raw_status}' — đã tự suy ra status='{status}' từ score.",
                    }
                ]
                if status_corrected
                else []
            ),
        }
        # Field cấu trúc riêng theo grader (matched/missing, row_id,
        # expected_output_tokens/student_tokens...) — do wrapper
        # (grade_*_with_llm) chuẩn bị, giữ
        # lại ở đây thay vì để mất khi LLM chạy thành công (xem doc.md mục 6).
        if extra_result_fields:
            result.update(extra_result_fields)
        return result

    except Exception as e:
        # Exception → fallback heuristic
        fallback = dict(heuristic_result)
        fallback["grading_method"] = "heuristic_exception"
        fallback["stage"] = "llm_failed"
        fallback["llm_used"] = False
        fallback["llm_error"] = str(e)[:100]
        fallback["cot_reasoning"] = ""
        if fallback.get("status") in TRANSIENT_REVIEW_STATUSES:
            fallback["status"] = "wrong"
            fallback["teacher_review_required"] = True
        return fallback


def grade_visual_with_llm(
    sample: Dict[str, Any], criterion: Dict[str, Any], heuristic_result: Dict[str, Any]
) -> Dict[str, Any]:
    """llm-visual: Vision LLM đã chạy bên trong grade_visual_criterion() (ở
    heuristic router) và kết quả đó đã là final — không có text evidence để
    _grade_with_llm_advised_core() re-review. Chỉ chuẩn hóa vài field mặc
    định cho đồng nhất với 3 loại criterion kia."""
    heuristic_result.setdefault("grading_method", "vision_llm")
    heuristic_result.setdefault("stage", "llm")
    heuristic_result.setdefault(
        "token_usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    )
    return heuristic_result


def _format_token_detail(
    expected_output_tokens: Optional[List[str]], student_tokens: Optional[List[Optional[str]]]
) -> str:
    """Build đoạn text 'Chi tiết từng token' cho prompt từ expected_output_tokens/
    student_tokens — is_correct từng token được suy ra trực tiếp (student ==
    expected), không cần lưu riêng field token_evaluations chỉ để trùng lặp
    2 list này."""
    if not expected_output_tokens:
        return ""
    return "\nChi tiet tung token:\n" + "\n".join(
        f"  [{i}] expected='{expected}' student='{student}' > {'[OK]' if student == expected else '[FAIL]'}"
        for i, (expected, student) in enumerate(
            zip(expected_output_tokens, student_tokens or [])
        )
    )


def grade_matching_with_llm(
    sample: Dict[str, Any], criterion: Dict[str, Any], heuristic_result: Dict[str, Any]
) -> Dict[str, Any]:
    """llm-matching: đưa chi tiết từng token (nếu có) vào prompt, override
    expected_output bằng giá trị ĐÃ RESOLVE (`heuristic_result["expected_outputs"]`
    — luôn là bản đã resolve, dù resolve từ conditional_outputs hay chỉ đơn
    giản từ 1 field literal khớp tên trong sample, VD "student_index", xem
    `prepare_output_evidence`), và giữ lại các field cấu trúc riêng của
    Matching trong kết quả cuối.

    FIX: trước đây chỉ override khi criterion là conditional
    (`conditioning.has_conditional`) — criterion KHÔNG conditional nhưng có
    field literal cần resolve (VD `expected_outputs: ["student_index"]`,
    T3_main_s1) thì LLM chưa từng thấy giá trị đã resolve, chỉ thấy nguyên
    văn chuỗi "student_index" (vô nghĩa với LLM) — dẫn tới LLM tự đoán/bịa
    lý do (VD "đã tra cứu danh sách thi xác nhận đúng số X" — không có
    danh sách nào để tra cả) thay vì so khớp với con số thật. Giờ luôn dùng
    `heuristic_result["expected_outputs"]` (đã resolve đủ mọi trường hợp).
    Không chèn câu "chấp nhận cách làm tương đương" vào prompt — output
    chương trình là 1 giá trị cố định duy nhất, không có khái niệm "cách
    viết tương đương" cho cùng 1 con số (xem docstring _cot_single_pass)."""
    extra_prompt_text = _format_token_detail(
        heuristic_result.get("expected_output_tokens"), heuristic_result.get("student_tokens")
    )

    expected_outputs_override = heuristic_result.get("expected_outputs") or None

    extra_result_fields = {
        key: heuristic_result[key]
        for key in (
            "conditioning",
            "expected_output_tokens",
            "student_tokens",
        )
        if key in heuristic_result
    }

    return _grade_with_llm_advised_core(
        sample,
        criterion,
        heuristic_result,
        extra_prompt_text=extra_prompt_text,
        extra_result_fields=extra_result_fields,
        expected_outputs_override=expected_outputs_override,
        accept_equivalent_solutions=False,
    )


def grade_logical_with_llm(
    sample: Dict[str, Any], criterion: Dict[str, Any], heuristic_result: Dict[str, Any]
) -> Dict[str, Any]:
    """llm-logical: đưa matched/missing dạng có cấu trúc vào prompt (thay vì
    chỉ 1 câu reason tóm tắt), và giữ lại matched/missing trong kết quả cuối
    — heuristic Logical không bao giờ có điểm thật nên đây là advisory duy
    nhất LLM có thể dựa vào ngoài nội dung câu hỏi."""
    matched = heuristic_result.get("matched", [])
    missing = heuristic_result.get("missing", [])

    extra_prompt_text = ""
    if matched or missing:
        matched_text = "\n".join(f"  [OK] {m['value']}" for m in matched) or "  (không có)"
        missing_text = "\n".join(f"  [MISS] {m['value']}" for m in missing) or "  (không có)"
        extra_prompt_text = (
            f"\nTừ khóa/ý đã tìm thấy trong bài làm:\n{matched_text}"
            f"\nTừ khóa/ý CHƯA tìm thấy:\n{missing_text}"
        )

    extra_result_fields = {"matched": matched, "missing": missing}

    return _grade_with_llm_advised_core(
        sample,
        criterion,
        heuristic_result,
        extra_prompt_text=extra_prompt_text,
        extra_result_fields=extra_result_fields,
        show_heuristic_score_status=False,
        heuristic_reason_label="Found",
    )


def grade_table_with_llm(
    sample: Dict[str, Any], criterion: Dict[str, Any], heuristic_result: Dict[str, Any]
) -> Dict[str, Any]:
    """llm-table: nhánh 1-ô (row_id+col_id) đưa đúng vị trí ô vào prompt và
    giữ row_id/col_id trong kết quả cuối. `grade_table_criterion`/
    `grade_table_row_criterion` không còn nhánh nào set matched/missing/
    expected_output_tokens/student_tokens (đã bỏ hẳn khỏi Table, xem doc.md
    mục 3/7) — criterion thiếu row_id/col_id (VD "no table"/"incomplete")
    không có gì thêm để đưa vào prompt ngoài row_id/col_id=None."""
    row_id = heuristic_result.get("row_id")
    col_id = heuristic_result.get("col_id")

    extra_prompt_text = ""
    if row_id and col_id:
        student_cell_text = heuristic_result.get("student_cell_text", "")
        extra_prompt_text = (
            f"\nVị trí cần kiểm tra: hàng {row_id}, cột {col_id}. "
            f"Học sinh viết: '{student_cell_text}' (chưa xác định đúng/sai — "
            f"expected_value chỉ là ví dụ gợi ý, cần bạn tự verify logic)."
        )

    extra_result_fields = {
        key: heuristic_result[key]
        for key in ("row_id", "col_id", "student_cell_text")
        if key in heuristic_result
    }

    return _grade_with_llm_advised_core(
        sample,
        criterion,
        heuristic_result,
        extra_prompt_text=extra_prompt_text,
        extra_result_fields=extra_result_fields,
    )


def grade_table_group_with_llm(
    sample: Dict[str, Any], criteria: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """llm-table (BATCH — nhiều criterion cùng 1 bảng): chấm TẤT CẢ criteria
    cùng 1 bảng trong ĐÚNG 1 lần gọi LLM (`call_llm_table_batch`) — để LLM
    thấy toàn bộ nội dung bảng (mọi hàng/cột) khi quyết định, thay vì mỗi ô
    gọi LLM tách biệt hoàn toàn khỏi các ô khác (không thể verify quan hệ
    giữa các ô, VD Input↔Output cùng hàng phải khớp logic bài toán — xem
    thảo luận T15B). Heuristic vẫn chạy riêng từng criterion trước như bình
    thường (advisory), rồi mỗi criterion blend heuristic_score của mình với
    llm_score tương ứng lấy từ response gộp — dùng chung `_blend_heuristic_and_llm`
    với đường đơn-criterion (`_grade_with_llm_advised_core`), không có công
    thức blend riêng cho nhóm."""
    table_cids = [c["criterion_id"] for c in criteria]
    heuristic_results = {
        c["criterion_id"]: grade_table_criterion(sample, c) for c in criteria
    }
    print(
        f"        - {', '.join(table_cids)}: xong heuristic ({len(table_cids)} ô)",
        flush=True,
    )

    # evidence giống nhau cho cả nhóm (cùng 1 bảng) — lấy từ criterion đầu tiên
    evidence = next(iter(heuristic_results.values())).get("evidence") or {}
    tables = evidence.get("tables", [])
    all_cells_blank = not any(
        (cell.get("text") or "").strip()
        for table in tables
        for cell in table.get("cells", [])
    )

    if not tables or all_cells_blank:
        print(
            f"        - {', '.join(table_cids)}: bảng trống, bỏ qua LLM (blank_skip)",
            flush=True,
        )
        return [
            {
                "criterion_id": c.get("criterion_id"),
                "part_label": c.get("part_label"),
                "criterion_content": c.get("content", ""),
                "score": 0,
                "max_score": c.get("score", 0),
                "status": "wrong",
                "llm_used": False,
                "grading_method": "blank_skip",
                "stage": "heuristic",
                "row_id": heuristic_results[c["criterion_id"]].get("row_id"),
                "col_id": heuristic_results[c["criterion_id"]].get("col_id"),
                "evidence": evidence,
                "detected_errors": [
                    {"error_type": "blank_answer", "message": "Sinh viên không làm phần này."}
                ],
            }
            for c in criteria
        ]

    # table_slot (từ barem — question.parts[].tables[].table_slot) là cấu
    # trúc ĐẦY ĐỦ của bảng, gồm cả ô in sẵn/header — evidence.tables (OCR bài
    # học sinh) chỉ có ô học sinh thực sự viết, thiếu hẳn ô in sẵn. Dùng
    # table_slot làm khung, điền giá trị: ô "printed" lấy nguyên text khai
    # trong barem; ô "student_text" tra theo cell_id trong evidence.tables.
    table_slot = criteria[0].get("table_slot") if criteria else None
    if table_slot:
        student_cells_by_id = {
            cell.get("cell_id"): cell
            for table in tables
            for cell in table.get("cells", [])
        }
        table_text = "\n".join(
            f"{slot.get('cell_id')}: "
            + (
                slot.get("text", "")
                if slot.get("source") == "printed"
                else (student_cells_by_id.get(slot.get("cell_id"), {}).get("text", "") or "(trống)")
            )
            for slot in table_slot
        )
    else:
        table_text = "\n".join(
            f"{cell.get('cell_id')}: {cell.get('text', '') or '(trống)'}"
            for table in tables
            for cell in table.get("cells", [])
        )

    criteria_specs = [
        {
            "criterion_id": c["criterion_id"],
            "content": c.get("content", ""),
            "row_id": heuristic_results[c["criterion_id"]].get("row_id"),
            "col_id": heuristic_results[c["criterion_id"]].get("col_id"),
            "expected_value": c.get("expected_value"),
            # Không default về 0 — criterion Table 1-ô (VD T15B1..T15B5) không
            # có field "score" riêng (chỉ "weight", điểm thật cấp ở nhóm
            # all_or_nothing cha). Hiện "None" trong prompt cho LLM thấy rõ
            # ràng "không có điểm tối đa riêng cho ô này", tránh nhầm với 1
            # giáo viên thật sự khai max_score=0. Đây CHỈ là giá trị hiển thị
            # trong prompt — max_score dùng để tính điểm thật vẫn tách riêng
            # (xem `max_score = c.get("score", 0)` ở vòng lặp blend bên dưới,
            # không đổi — vẫn là known open issue, xem CLAUDE.md).
            "max_score": c.get("score"),
        }
        for c in criteria
    ]

    print(
        f"        - {', '.join(table_cids)}: đang gọi LLM batch...",
        flush=True,
    )
    batch_result = call_llm_table_batch(
        table_text,
        criteria_specs,
        question_text=criteria[0].get("question_text", ""),
        subject=criteria[0].get("subject", ""),
    )
    print(
        f"        - {', '.join(table_cids)}: xong LLM batch",
        flush=True,
    )

    if "error" in batch_result:
        # Cả nhóm fail cùng lúc (1 lần gọi LLM chung) → fallback TỪNG
        # criterion về heuristic riêng, giống hệt cách _grade_with_llm_advised_core
        # xử lý lỗi LLM ở đường đơn-criterion.
        results = []
        for c in criteria:
            fallback = dict(heuristic_results[c["criterion_id"]])
            fallback["grading_method"] = "heuristic_llm_failed"
            fallback["stage"] = "llm_failed"
            fallback["llm_used"] = False
            fallback["llm_error"] = batch_result.get("error", "Table batch LLM failed")
            fallback["cot_reasoning"] = ""
            if fallback.get("status") in TRANSIENT_REVIEW_STATUSES:
                fallback["status"] = "wrong"
                fallback["teacher_review_required"] = True
            results.append(fallback)
        return results

    llm_results = batch_result.get("results", {})
    token_usage = batch_result.get(
        "token_usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    )
    # 1 lần gọi LLM cho cả nhóm — chia đều token_usage cho từng criterion để
    # tổng token_usage cấp sample không bị nhân N lần.
    n = max(1, len(criteria))
    shared_token_usage = {k: v / n for k, v in token_usage.items()}

    results = []
    for c in criteria:
        cid = c["criterion_id"]
        h = heuristic_results[cid]
        max_score = c.get("score", 0)
        h_score = h.get("score", 0)
        entry = llm_results.get(cid) or {"score": h_score, "status": "wrong", "reasoning": ""}

        score, status, llm_score, llm_status, status_corrected = _blend_heuristic_and_llm(
            h_score, entry.get("score", h_score), entry.get("status", "wrong"), max_score,
            c.get("question_type", "table"),
        )

        results.append(
            {
                "criterion_id": cid,
                "part_label": c.get("part_label"),
                "criterion_content": c.get("content", ""),
                "score": round(score, 4),
                "max_score": max_score,
                "status": status,
                "llm_used": True,
                "grading_method": "llm_table_batch_cot",
                "stage": "llm",
                "llm_reasoning": entry.get("reasoning", ""),
                "cot_reasoning": batch_result.get("cot_reasoning", ""),
                "row_id": h.get("row_id"),
                "col_id": h.get("col_id"),
                "heuristic_score": h_score,
                "heuristic_status": h.get("status", "unknown"),
                "heuristic_weight": CFG.get("heuristic_weight_by_type", {}).get(
                    c.get("question_type", "table"), CFG.get("heuristic_weight", 0.5)
                ),
                "llm_score": round(llm_score, 4),
                "llm_status": llm_status,
                "evidence": evidence,
                "token_usage": shared_token_usage,
                "status_corrected": status_corrected,
                "detected_errors": (
                    [
                        {
                            "error_type": "invalid_llm_status",
                            "message": (
                                f"LLM trả về status không hợp lệ cho '{cid}': "
                                f"'{entry.get('status')}' — đã tự suy ra status='{status}' từ score."
                            ),
                        }
                    ]
                    if status_corrected
                    else []
                ),
            }
        )
    return results


def grade_criterion_with_llm(
    sample: Dict[str, Any], criterion: Dict[str, Any], heuristic_result: Dict[str, Any]
) -> Dict[str, Any]:
    """llm-router: dispatch heuristic_result tới hàm LLM advisory phù hợp với
    question_type của criterion (đối xứng với grade_criterion() — heuristic
    router). Mỗi loại tự quyết advisory text nào đưa vào prompt và field cấu
    trúc nào giữ lại trong kết quả cuối, thay vì dùng chung 1 luồng generic
    cho mọi grader."""
    mode = infer_criterion_grading_mode(criterion)
    if mode == "visual":
        return grade_visual_with_llm(sample, criterion, heuristic_result)
    if mode == "expected_output":
        return grade_matching_with_llm(sample, criterion, heuristic_result)
    if mode == "expected_value":
        return grade_logical_with_llm(sample, criterion, heuristic_result)
    if mode == "table":
        return grade_table_with_llm(sample, criterion, heuristic_result)
    # question_type ngoài 4 loại đã biết (không nên xảy ra sau validate_barem) —
    # vẫn cho qua LLM core, không có advisory/field cấu trúc riêng nào thêm.
    return _grade_with_llm_advised_core(sample, criterion, heuristic_result)


def grade_criterion_advised(
    sample: Dict[str, Any], criterion: Dict[str, Any]
) -> Dict[str, Any]:
    """
    System 4: Luôn chạy heuristic trước (grade_criterion — heuristic router)
    → dùng kết quả làm advisory cho LLM (grade_criterion_with_llm — llm
    router), rồi dispatch tới hàm LLM advisory riêng theo question_type. LLM
    là người ra quyết định cuối cho MỌI criterion, kể cả khi heuristic đã
    chắc chắn (VD khớp chuỗi thô tuyệt đối, status="correct") — heuristic
    result CHỈ đóng vai trò gợi ý (advisory context) cho LLM, không còn tự quyết
    thay LLM nữa (đã bỏ cơ chế bypass "FIX #4" trước đây). Ngoại lệ DUY NHẤT
    (visual): xem grade_visual_with_llm().
    """
    cid = criterion.get("criterion_id", "?")
    heuristic_result = grade_criterion(sample, criterion)
    print(f"        - {cid}: xong heuristic, đang gọi LLM...", flush=True)
    result = grade_criterion_with_llm(sample, criterion, heuristic_result)
    print(f"        - {cid}: xong LLM", flush=True)
    return result


def aggregate_with_group_rules(
    criterion_results: List[Dict[str, Any]],
) -> Tuple[float, List[Dict[str, Any]]]:
    """
    Áp dụng all_or_nothing ở cấp group (sub_question, VD T15A) khi tính tổng điểm.
    Các criterion thuộc nhóm all_or_nothing chỉ được tính 1 lần cho cả nhóm:
    đủ điểm nhóm nếu TẤT CẢ thành viên đúng, ngược lại 0 — không cộng riêng từng thành viên.
    """
    total = 0.0
    groups: Dict[str, List[Dict[str, Any]]] = {}

    for r in criterion_results:
        gid = r.get("group_id")
        if gid and r.get("group_all_or_nothing"):
            groups.setdefault(gid, []).append(r)
        else:
            total += r.get("score", 0)

    group_overrides = []
    for gid, members in groups.items():
        # Dùng status thay vì is_correct — heuristic result (và fallback khi
        # LLM lỗi, dict(heuristic_result)) không còn field is_correct riêng
        # nữa (suy ra 100% từ status, xem grade_expected_value_criterion).
        all_correct = all(m.get("status") == "correct" for m in members)
        group_max = members[0].get("group_max_score", 0)
        group_score = group_max if all_correct else 0.0
        total += group_score
        group_overrides.append(
            {
                "group_id": gid,
                "members": [m.get("criterion_id") for m in members],
                "all_correct": all_correct,
                "group_score": group_score,
                "group_max_score": group_max,
            }
        )

    return round(total, 4), group_overrides


def _attach_group_metadata(criterion: Dict[str, Any], result: Dict[str, Any]) -> None:
    """Mang theo group metadata (all_or_nothing) từ criterion sang result để
    aggregate_with_group_rules() áp dụng đúng lúc tính tổng điểm. Dùng chung
    cho mọi criterion đi qua run_part(), bất kể chấm qua đường đơn-criterion
    hay đường batch-table."""
    if criterion.get("group_all_or_nothing"):
        result["group_id"] = criterion.get("group_id")
        result["group_all_or_nothing"] = True
        result["group_max_score"] = criterion.get("group_max_score", 0)


def run_part(
    routed_sample: Dict[str, Any], part_criteria: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """run_part: chấm toàn bộ criteria thuộc 1 part (part_label) của 1 câu.
    Criteria nào là table (question_type='table') được gom chấm chung ĐÚNG 1
    lần gọi LLM (grade_table_group_with_llm) — để LLM thấy toàn bộ bảng khi
    quyết định (VD verify quan hệ Input↔Output cùng hàng, xem thảo luận
    T15B) — thay vì mỗi ô/hàng gọi LLM tách biệt hoàn toàn khỏi nhau. Các
    criteria không phải table trong CÙNG part (nếu có) vẫn chấm riêng từng
    cái như bình thường."""
    table_criteria = [
        c for c in part_criteria if infer_criterion_grading_mode(c) == "table"
    ]
    other_criteria = [c for c in part_criteria if c not in table_criteria]

    results = []
    for criterion in other_criteria:
        crit_t0 = time.time()
        result = grade_criterion_advised(routed_sample, criterion)
        result["latency_ms"] = round((time.time() - crit_t0) * 1000)
        _attach_group_metadata(criterion, result)
        results.append(result)

    if table_criteria:
        group_t0 = time.time()
        group_results = grade_table_group_with_llm(routed_sample, table_criteria)
        group_latency_ms = round((time.time() - group_t0) * 1000)
        for criterion, result in zip(table_criteria, group_results):
            result["latency_ms"] = group_latency_ms
            _attach_group_metadata(criterion, result)
            results.append(result)

    return results


def grade_sample_advised(
    sample: Dict[str, Any], barem_dict: Dict[int, List[Dict]]
) -> Dict[str, Any]:
    """
    Hàm chạy chấm sample chính sử dụng cơ chế:
        Heuritic review -> LLM advisory -> Aggregate score

    Chấm theo từng part (run_part) — mỗi part của câu này tự quyết định
    chấm qua đường đơn-criterion hay đường batch-table.
    """

    routed_sample = apply_question_routing(sample, barem_dict)

    validation_after = validate_sample_schema(
        routed_sample, after_routing=True, barem_dict=barem_dict
    )

    q_num = sample.get("question_number")
    if q_num is None:
        m = re.match(r"cau_(\d+)", sample.get("sample_id", ""))
        if m:
            q_num = int(m.group(1))

    criteria_list = (
        barem_dict.get(q_num, [])
        if barem_dict and q_num and barem_dict.get(q_num)
        else routed_sample.get("teacher_barem", [])
    )

    parts: Dict[Any, List[Dict[str, Any]]] = {}
    for criterion in criteria_list:
        parts.setdefault(criterion.get("part_label"), []).append(criterion)

    criterion_results = []
    sample_t0 = time.time()
    for part_criteria in parts.values():
        criterion_results.extend(run_part(routed_sample, part_criteria))

    # Giữ lại đúng thứ tự criteria_list gốc trong report (run_part xử lý
    # riêng từng part nên các part có thể lệch thứ tự sau khi gộp lại).
    _order = {c.get("criterion_id"): i for i, c in enumerate(criteria_list)}
    criterion_results.sort(key=lambda r: _order.get(r.get("criterion_id"), len(_order)))

    agreed_count = 0
    overridden_count = 0
    detected_errors = []
    for result in criterion_results:
        # Track agreement stats
        if result.get("agreed_with_heuristic") is True:
            agreed_count += 1
        elif result.get("agreed_with_heuristic") is False:
            overridden_count += 1

        for err in result.get("detected_errors", []):
            detected_errors.append(
                {
                    "criterion_id": result.get("criterion_id"),
                    "part_label": result.get("part_label"),
                    **err,
                }
            )

    total_score, group_overrides = aggregate_with_group_rules(criterion_results)
    max_score = routed_sample.get("max_score", 0)
    latency_ms = round((time.time() - sample_t0) * 1000)

    # Aggregate token usage across all criteria
    total_tokens: Dict[str, int] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    for r in criterion_results:
        u = r.get("token_usage", {})
        for k in total_tokens:
            total_tokens[k] += u.get(k, 0)

    # Collect non-empty LLM feedbacks/suggestions per criterion
    llm_feedbacks = [
        {
            "criterion_id": r.get("criterion_id"),
            "part_label": r.get("part_label"),
            "score": r.get("score", 0),
            "max_score": r.get("max_score", 0),
            "feedback": r.get("feedback", ""),
            "suggestion": r.get("suggestion", ""),
        }
        for r in criterion_results
        if r.get("feedback") or r.get("suggestion")
    ]

    teacher_review_required = (
        any(r.get("status") == "error" for r in criterion_results)
        or any(r.get("status") in TRANSIENT_REVIEW_STATUSES for r in criterion_results)
        or any(r.get("teacher_review_required") for r in criterion_results)
        or not validation_after["valid"]
        or routed_sample.get("routing", {}).get("confidence", 1.0) < 0.6
    )

    if not validation_after["valid"]:
        status = "ungraded"
        feedback = f"Validation failed: {', '.join(validation_after.get('errors', []))}"
    elif total_score == max_score:
        status = "correct"
        feedback = "Bài làm đạt đầy đủ tiêu chí (LLM + Heuristic Advisory)."
    elif total_score > 0:
        status = "partially_correct"
        feedback = "Bài làm đúng một phần (LLM + Heuristic Advisory)."
    elif total_score == 0 and not teacher_review_required:
        status = "wrong"
        feedback = "Bài làm chưa đạt tiêu chí (LLM + Heuristic Advisory)."
    else:
        status = "ungraded"
        feedback = "Cần review thêm."

    return {
        "sample_id": routed_sample.get("sample_id"),
        "ma_de": routed_sample.get("ma_de"),
        "question_number": q_num,
        "question_type": routed_sample.get("question_type"),
        "routing": routed_sample.get("routing"),
        "score": total_score,
        "max_score": max_score,
        "status": status,
        "grading_method": "llm_advised",
        "latency_ms": latency_ms,
        "token_usage": total_tokens,
        "llm_feedbacks": llm_feedbacks,
        "validation_after_routing": validation_after,
        "criterion_results": criterion_results,
        "group_overrides": group_overrides,
        "detected_errors": detected_errors,
        "feedback": feedback,
        "teacher_review_required": teacher_review_required,
        "advisory_stats": {
            "total_criteria": len(criteria_list),
            "agreed_count": agreed_count,
            "overridden_count": overridden_count,
            "blank_skipped": sum(
                1 for r in criterion_results if r.get("grading_method") == "blank_skip"
            ),
        },
    }


# ============================================================================
# RESULTS FORMAT CONVERTER
# ============================================================================


def convert_results_to_samples(
    data: Dict, barem_dict: Dict[int, List[Dict]]
) -> List[Dict[str, Any]]:
    """
    Chuyển Results_Ma_de_1.json format sang pipeline sample list.

    Nguyên tắc mapping:
      - Mỗi HS_N  → student_index = N
      - Cau_XX    → question_number = XX, lines map tuần tự theo part_labels từ barem
      - Cau_XX_N  → sub-slot N của câu XX (vd Cau_08_1, Cau_08_2)
      - Cau_XXa   → sub-part "a" của câu XX (vd Cau_13a, Cau_14b)
      - Mỗi line  → 1 slot: lấy đúng N lines đầu theo số slot parem định nghĩa,
                    thiếu → rỗng, thừa → bỏ
    """
    samples = []

    try:
        ma_de = str(data.get("ma_de"))
    except (ValueError, TypeError):
        print("[ERROR] Invalid 'ma_de' value in input data")
        return samples

    for hs_key, questions in data.items():
        if not hs_key.startswith("HS_") or not isinstance(questions, dict):
            continue
        try:
            student_index = int(hs_key.split("_")[-1])
        except ValueError:
            student_index = -1  # Invalid student index

        # Gom các Cau entries theo question_number
        q_data: Dict[int, Dict[str, Any]] = {}

        for cau_key, cau_val in questions.items():
            if not isinstance(cau_val, dict):
                continue
            ocr_status = cau_val.get("status", "")
            table_extracted: List[Dict] = []
            if ocr_status in ("failed_at_cropping", "skipped"):
                lines: List[str] = []
            else:
                content = cau_val.get("content") or {}
                lines = [l for l in (content.get("lines") or []) if isinstance(l, str)]
                # Format bảng chuẩn: table_extracted thay vì lines
                raw_table = content.get("table_extracted")
                if isinstance(raw_table, list):
                    table_extracted = [r for r in raw_table if isinstance(r, dict)]

            # Parse: Cau_XX | Cau_XX_N | Cau_XXa | Cau_XXa_N
            m = re.match(r"Cau_(\d+)([a-z]?)(?:_(\d+))?$", cau_key, re.IGNORECASE)
            if not m:
                continue
            q_num = int(m.group(1))
            sub = m.group(2).lower() if m.group(2) else None
            slot_n = int(m.group(3)) if m.group(3) else None

            if q_num not in q_data:
                q_data[q_num] = {}

            image_path = cau_val.get("image_path", "")
            cau_type = cau_val.get("type", "")
            is_visual = cau_type == "diagram" and bool(image_path)

            if sub and slot_n is not None:
                q_data[q_num][f"sub_{sub}_slot_{slot_n}"] = lines
                if table_extracted:
                    q_data[q_num][f"sub_{sub}_slot_{slot_n}_table"] = table_extracted
                if is_visual:
                    q_data[q_num][f"sub_{sub}_slot_{slot_n}_visual"] = image_path
            elif sub:
                q_data[q_num][f"sub_{sub}"] = lines
                if table_extracted:
                    q_data[q_num][f"sub_{sub}_table"] = table_extracted
                if is_visual:
                    q_data[q_num][f"sub_{sub}_visual"] = image_path
            elif slot_n is not None:
                q_data[q_num][f"slot_{slot_n}"] = lines
            else:
                q_data[q_num]["main"] = lines
                if table_extracted:
                    q_data[q_num]["main_table"] = table_extracted
                if is_visual:
                    q_data[q_num]["main_visual"] = image_path

        # Xây dựng sample cho từng câu
        for q_num in sorted(q_data.keys()):
            q_entries = q_data[q_num]
            criteria = barem_dict.get(q_num, [])

            # Lấy danh sách part_labels theo thứ tự từ barem
            part_labels: List[str] = []
            for c in criteria:
                pl = c.get("part_label")
                if pl and pl not in part_labels:
                    part_labels.append(pl)

            # Map part_label → text (part chỉ 1 slot)
            part_text: Dict[str, str] = {}
            # Map part_label → {slot_n: text} (part có NHIỀU slot con, VD Cau_13a_1/13a_2)
            part_multi_slot_text: Dict[str, Dict[int, str]] = {}

            if "main" in q_entries:
                # Cau_XX đơn: line[i] → part_labels[i]
                all_lines = q_entries["main"]
                for i, pl in enumerate(part_labels):
                    part_text[pl] = all_lines[i] if i < len(all_lines) else ""

            elif any(k.startswith("slot_") for k in q_entries):
                # FIX: Cau_XX_1, Cau_XX_2 — mỗi slot đã LÀ 1 part_label riêng
                # (không phải mỗi LINE trong content.lines). Trước đây
                # flatten_lines gộp lines của TẤT CẢ slot lại thành 1 danh
                # sách rồi chia lại theo vị trí cho part_labels — sai khi 1
                # slot có nhiều dòng (VD Cau_08_2 = ['0x50528c','8','0','8']
                # ở HS_3 thật): dòng thừa của slot này bị gán nhầm sang
                # part_label của slot khác, dòng cuối bị mất hẳn. Giờ map
                # ĐÚNG 1 slot → 1 part_label, nối các dòng CÙNG slot bằng
                # "\n" (nhất quán với get_student_evidence_for_slot).
                slot_keys = sorted(
                    (k for k in q_entries if k.startswith("slot_")),
                    key=lambda k: int(k.split("_")[1]),
                )
                for i, pl in enumerate(part_labels):
                    lns = q_entries[slot_keys[i]] if i < len(slot_keys) else []
                    part_text[pl] = "\n".join(lns) if lns else ""

            elif any(k.startswith("sub_") for k in q_entries):
                # Cau_13a/b/c: sub letter = part_label, join tất cả lines.
                # FIX: Cau_13a_1/13a_2 — part "a" có NHIỀU slot con, giữ
                # riêng vào part_multi_slot_text (không gộp vào part_text)
                # để sau này sinh nhiều slot_id, mỗi slot 1 cái — thay vì 1
                # slot_id chung cho cả part như trước (sẽ làm mất phân biệt
                # giữa 2 slot). Nhân tiện loại trừ luôn "_visual" ở đây —
                # trước đây thiếu điều kiện này khiến image_path (1 chuỗi,
                # không phải list) bị "\n".join() theo từng KÝ TỰ một.
                for k, lns in q_entries.items():
                    if k.endswith("_table") or k.endswith("_visual"):
                        continue
                    m2 = re.match(r"sub_([a-z])_slot_(\d+)$", k)
                    if m2:
                        letter, n = m2.group(1), int(m2.group(2))
                        part_multi_slot_text.setdefault(letter, {})[n] = (
                            "\n".join(lns) if lns else ""
                        )
                    elif k.startswith("sub_"):
                        sub_letter = k[4:]
                        part_text[sub_letter] = "\n".join(lns) if lns else ""

            # Build ans_tables từ table_extracted (format chuẩn)
            ans_tables: List[Dict] = []
            for k, rows in q_entries.items():
                if not k.endswith("_table") or not isinstance(rows, list):
                    continue
                # Xác định part_label từ key: "main_table" → part_labels[0], "sub_b_table" → "b"
                if k == "main_table":
                    pl = part_labels[0] if part_labels else "main"
                elif k.startswith("sub_") and k.endswith("_table"):
                    pl = k[4:-6]  # "sub_b_table" → "b"
                else:
                    continue
                cells = []
                for i, row in enumerate(rows):
                    if not isinstance(row, dict):
                        continue
                    col_keys = sorted(ck for ck in row if ck.startswith("col_"))
                    for j, col_key in enumerate(col_keys):
                        text = str(row.get(col_key, ""))
                        cells.append(
                            {
                                "cell_id": f"R{i+1}C{j+1}",
                                "row_id": f"R{i+1}",
                                "col_id": f"C{j+1}",
                                "text": text,
                                "part_label": pl,
                                "slot_id": f"cau_{q_num}_001_{pl}",
                                "is_blank": not bool(text),
                            }
                        )
                if cells:
                    ans_tables.append({"part_label": pl, "cells": cells})

            # Build ans_visuals từ diagram entries
            ans_visuals: List[Dict] = []
            for k, img_path in q_entries.items():
                if not k.endswith("_visual") or not isinstance(img_path, str):
                    continue
                if k == "main_visual":
                    pl = part_labels[0] if part_labels else "main"
                elif k.startswith("sub_") and k.endswith("_visual"):
                    pl = k[4:-7]  # "sub_c_visual" → "c"
                else:
                    continue
                ans_visuals.append(
                    {
                        "image_path": img_path,
                        "part_label": pl,
                        "slot_id": f"cau_{q_num}_001_{pl}",
                        "type": "diagram",
                        "is_blank": not bool(img_path),
                    }
                )

            # Build student_answer
            ans_lines: List[Dict] = []
            ans_tokens: List[Dict] = []
            full_parts: List[str] = []
            line_idx = 1

            effective_pls = (
                part_labels
                if part_labels
                else (list(part_text.keys()) + list(part_multi_slot_text.keys()))
            )

            def _emit_slot_lines(pl: str, slot_id: str, text: str) -> None:
                """Sinh ans_lines cho 1 slot cụ thể — dùng chung cho cả part
                1-slot (slot_id không hậu tố) và part nhiều-slot (slot_id có
                hậu tố _S{n}). `ans_tokens` (`student_answer.tokens`) không
                được sinh ở đây nữa — không có grader nào đọc field này (mọi
                so khớp đều dựa trên `evidence["student_answer"]`, chuỗi text
                thô, không phải token đã tách sẵn); trước đây gọi
                `tokenize_answer()`, một hàm chưa từng được định nghĩa trong
                file này — crash NameError ngay khi có dòng trả lời không
                trống, trên MỌI lần chạy `convert_results_to_samples()` thật."""
                nonlocal line_idx
                if not text:
                    ans_lines.append(
                        {
                            "line_id": f"L{line_idx}",
                            "part_label": pl,
                            "slot_id": slot_id,
                            "text": "",
                            "bbox": [0, 0, 0, 0],
                            "confidence": 0.0,
                            "is_blank": True,
                        }
                    )
                    line_idx += 1
                    return

                # Tách multi-line text (code) thành từng dòng riêng.
                # Chỉ rstrip() (bỏ ký tự trắng/CR thừa ở cuối dòng do OCR) —
                # KHÔNG strip() đầu dòng, vì sẽ xóa mất thụt lề (indentation)
                # của code nhiều dòng. Dòng trống thật sự vẫn được giữ lại
                # (không continue-skip) để không làm lệch cấu trúc dòng gốc
                # mà học sinh đã viết.
                for tl in text.split("\n"):
                    stripped = tl.rstrip()
                    if not stripped.strip():
                        full_parts.append("")
                        ans_lines.append(
                            {
                                "line_id": f"L{line_idx}",
                                "part_label": pl,
                                "slot_id": slot_id,
                                "text": "",
                                "bbox": [0, 0, 0, 0],
                                "confidence": 1.0,
                            }
                        )
                        line_idx += 1
                        continue
                    full_parts.append(stripped)
                    ans_lines.append(
                        {
                            "line_id": f"L{line_idx}",
                            "part_label": pl,
                            "slot_id": slot_id,
                            "text": stripped,
                            "bbox": [0, 0, 0, 0],
                            "confidence": 1.0,
                        }
                    )
                    line_idx += 1

            for pl in effective_pls:
                if pl in part_multi_slot_text:
                    # FIX: part có NHIỀU slot con (VD Cau_13a_1/13a_2) — sinh
                    # 1 slot_id RIÊNG cho mỗi slot con (hậu tố _S{n}, đúng
                    # quy ước đã dùng trong barem/structure_parem.txt), thay
                    # vì 1 slot_id chung cho cả part (sẽ làm 2 slot con lẫn
                    # vào nhau, không thể phân biệt khi chấm).
                    for n in sorted(part_multi_slot_text[pl].keys()):
                        slot_id = f"cau_{q_num}_001_{pl}_S{n}"
                        _emit_slot_lines(pl, slot_id, part_multi_slot_text[pl][n])
                    continue

                text = part_text.get(pl, "")
                slot_id = f"cau_{q_num}_001_{pl}"
                _emit_slot_lines(pl, slot_id, text)

            seen_groups: set = set()
            max_score = 0.0
            for c in criteria:
                if c.get("group_all_or_nothing"):
                    gid = c.get("group_id")
                    if gid not in seen_groups:
                        seen_groups.add(gid)
                        max_score += c.get("group_max_score", 0)
                else:
                    max_score += c.get("score", 0)
            q_type = next(
                (c.get("question_type") for c in criteria if c.get("question_type")),
                None,
            )

            samples.append(
                {
                    "sample_id": f"cau_{q_num}_001__{hs_key}",
                    "student_index": student_index,
                    "ma_de": ma_de,
                    "question_type": q_type,
                    "question": {"text": f"Câu {q_num}.", "parts": []},
                    "student_answer": {
                        "full_text": "\n".join(full_parts),
                        "lines": ans_lines,
                        "tokens": ans_tokens,
                        "tables": ans_tables,
                        "visual_answers": ans_visuals,
                    },
                    "max_score": max_score,
                    "question_number": q_num,
                }
            )

    return samples


# ============================================================================
# Loading input & barem
# ============================================================================

def load_input(
    test_input_path: str, barem_dict: Dict[int, List[Dict]] = None
) -> List[Dict[str, Any]]:
    """
    Load test_input.json → list of samples. Pipeline chỉ chấp nhận input
    Results format gốc (dict {"HS_N": {...}})
    """
    with open(test_input_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    # Kiểm tra định dạng có phải dict hay không
    if not isinstance(raw_data, dict):
        raise ValueError(
            f"[ERROR] Input file {test_input_path} Wrong Results format (must be dict)"
        )

    # Kiểm tra có key "HS_N" hay không (ít nhất 1 học sinh)
    if "HS_N" not in raw_data and not any(k.startswith("HS_") for k in raw_data):
        raise ValueError(
            f"[ERROR] Input file {test_input_path} Wrong Results format (must have key 'HS_N' or keys starting with 'HS_')"
        )

    print("[INFO] Correcting format — converting to pipeline format...")

    # Chuyển Results format sang pipeline sample list (mỗi sample = 1 câu của 1 học sinh)
    samples = convert_results_to_samples(raw_data, barem_dict or {})
    print(f"[INFO] Converted {len(samples)} samples from Results format")


    # Save converted samples for inspection for debugging (optional)
    converted_path = Path(test_input_path).with_suffix(".converted.json")
    with open(converted_path, "w", encoding="utf-8") as f:
        json.dump(samples, f, ensure_ascii=False, indent=2)
    print(f"[INFO] Converted input saved to: {converted_path}")

    print(f"[OK] Loaded input: {len(samples)} samples")

    validation = validate_input(samples, barem_dict)

    if validation["warnings"]:
        print(f"  [WARN] validate_input: {len(validation['warnings'])} cảnh báo")
        for w in validation["warnings"]:
            print(f"    - {w}")
    if not validation["valid"]:
        print(
            f"  [ERROR] validate_input: {len(validation['errors'])} lỗi cấu trúc input"
        )
        for e in validation["errors"]:
            print(f"    - {e}")

    return samples


def _attach_table_slots(entry: Dict[str, Any], flat_criteria: List[Dict[str, Any]]) -> None:
    """Gắn `table_slot` (cấu trúc ĐẦY ĐỦ của bảng — gồm cả ô in sẵn/header,
    KHÔNG chỉ ô học sinh viết) từ `question.parts[].tables[].table_slot` vào
    từng criterion cùng `part_label`. `evidence.tables` (từ OCR bài học sinh)
    chỉ có các ô học sinh thực sự viết — thiếu hẳn ô header/in sẵn — nên
    `grade_table_group_with_llm` cần `table_slot` này để build `table_text`
    đầy đủ ngữ cảnh cho LLM (biết cột nào là gì, ô nào bị ép giá trị cố
    định...), không chỉ dựa vào evidence.tables."""
    parts = (entry.get("question") or {}).get("parts") or []
    table_slot_by_part: Dict[str, List[Dict[str, Any]]] = {}
    for part in parts:
        part_label = part.get("part_label")
        slots: List[Dict[str, Any]] = []
        for table in part.get("tables") or []:
            slots.extend(table.get("table_slot") or [])
        if slots:
            table_slot_by_part[part_label] = slots

    for criterion in flat_criteria:
        slot = table_slot_by_part.get(criterion.get("part_label"))
        if slot:
            criterion["table_slot"] = slot


def _attach_question_text(entry: Dict[str, Any], flat_criteria: List[Dict[str, Any]]) -> None:
    """Gắn `question["text"]` (đề bài GỐC của cả câu — VD toàn bộ code chương
    trình cần trace ở câu 1-12, hay đề bài toán ở câu 15) vào từng criterion
    dưới key `question_text`. Trước đây field này chỉ nằm ở cấp `question`
    (cha), KHÔNG hề được đưa vào bất kỳ prompt LLM nào — LLM chấm câu "chương
    trình này in ra gì" mà chưa từng thấy chính chương trình đó, chỉ thấy
    `criterion_content` (mô tả ngắn của giáo viên) + đáp án đúng cho sẵn,
    không có cách nào tự verify độc lập.

    Với câu có nhiều part (a/b/c...), còn nối thêm text RIÊNG của đúng part
    đó (`question["parts"][].text`, VD "Hãy tìm 3 ví dụ cho bài toán trên"
    cho phần b câu 15) — khớp theo `part_label`, không chỉ dùng mỗi text
    chung của cả câu (thiếu yêu cầu cụ thể của từng phần)."""
    question = entry.get("question") or {}
    question_text = question.get("text") or ""
    part_text_by_label = {
        part.get("part_label"): part.get("text")
        for part in question.get("parts") or []
        if part.get("text")
    }
    if not question_text and not part_text_by_label:
        return

    for criterion in flat_criteria:
        part_text = part_text_by_label.get(criterion.get("part_label"))
        if question_text and part_text:
            criterion["question_text"] = (
                f"{question_text}\n\n[Yêu cầu riêng phần {criterion.get('part_label')}] {part_text}"
            )
        elif part_text:
            criterion["question_text"] = part_text
        elif question_text:
            criterion["question_text"] = question_text


def load_barem(barem_path: str) -> Dict[int, List[Dict[str, Any]]]:
    """
    Load barem cho câu hỏi từ file JSON, flatten các criteria theo question_number → trả về dict {question_number: [criteria]}
    """
    barem_dict: Dict[int, List[Dict[str, Any]]] = {}
    path = Path(barem_path)


    if not path.exists():
        print(f"⚠ Không tìm thấy file barem: {barem_path}")
        return barem_dict

    with open(path, "r", encoding="utf-8") as f:
        barem_data = json.load(f)

    # Kiểm tra mã đề trong barem
    if barem_data.get("ma_de") is None:
        raise ValueError(f"[ERROR] Barem file {barem_path} missing 'ma_de' field")

    for entry in barem_data.get("teacher_barem", []):
        q_num = entry.get("question_number")
        if q_num is None:
            continue
        if q_num not in barem_dict:
            barem_dict[q_num] = []
        flat = flatten_criteria(entry)
        _attach_table_slots(entry, flat)
        _attach_question_text(entry, flat)
        subject = barem_data.get("subject", "")
        for c in flat:
            c["subject"] = subject
        barem_dict[q_num].extend(flat)

    print(f"[OK] Loaded barem: {len(barem_dict)} question groups")
    print(f"  Questions: {sorted(barem_dict.keys())}")
    for q, clist in sorted(barem_dict.items()):
        ids = [c.get("criterion_id", "?") for c in clist]
        print(f"  Q{q}: {ids}")

    validation = validate_barem(
        barem_dict, declared_total=barem_data.get("total_score")
    )
    if validation["warnings"]:
        print(f"  [WARN] validate_barem: {len(validation['warnings'])}")
        for w in validation["warnings"]:
            print(f"    - {w}")
    if not validation["valid"]:
        print(
            f"  [ERROR] validate_barem: {len(validation['errors'])} barem format errors"
        )
        for e in validation["errors"]:
            print(f"    - {e}")

    return barem_dict


#===========================================================================
# BATCH RUNNER
#===========================================================================

def run_student(
    student_samples: List[Dict[str, Any]], barem_dict: Dict[int, List[Dict]]
) -> List[Dict[str, Any]]:
    """
    Hàm chạy chấm tất cả samples của 1 học sinh (student_index) theo thứ tự
    """
    results = []
    ordered_samples = sorted(student_samples, key=lambda s: s.get("question_number") or 0)
    total = len(ordered_samples)
    for idx, sample in enumerate(ordered_samples, start=1):
        sid = sample.get("sample_id", "?")
        # In NGAY TRƯỚC khi chấm (không đợi grade_sample_advised xong mới in)
        # — để thấy tiến độ thật khi đang gọi LLM (có thể mất vài giây/câu do
        # self-consistency vote), tránh nhìn như bị treo khi chạy batch lớn.
        print(f"    [{idx}/{total}] Đang chấm {sid} (câu {sample.get('question_number')})...", flush=True)
        try:
            res = grade_sample_advised(sample, barem_dict)
        except Exception as e:
            res = {
                "sample_id": sid,
                "question_number": sample.get("question_number"),
                "score": 0,
                "max_score": sample.get("max_score", 0),
                "status": "error",
                "error": str(e),
            }
        results.append(res)
    return results


def run_batch(
    test_input_path: str, barem_path: str, output_path: str = None
) -> List[Dict[str, Any]]:
    """
    Hàm chạy chấm chính quy mô batch
    """

    barem_dict = load_barem(barem_path)
    samples = load_input(test_input_path, barem_dict)

    print(f"\n{'='*80}")
    print(f"System 4 (LLM+Advisory) — {len(samples)} samples")
    print(f"{'='*80}")

    # Gom samples theo student_index để chấm theo từng học sinh, tra theo student_index (HS_N) để in báo cáo theo thứ tự HS_1, HS_2, ...
    def _student_key(sample: Dict[str, Any]) -> str:
        student_index = sample.get("student_index")
        try:
            return f"HS_{int(student_index)}"
        except Exception as e:
            print(f"[Error] Cannot get student_index from sample {sample.get('sample_id')}: {e}")
            return "HS_UNKNOWN"


    def _hs_sort_key(hs_key: str) -> int:
        m = re.search(r"\d+", hs_key)
        return int(m.group()) if m else 0

    students: Dict[str, List[Dict[str, Any]]] = {}
    for sample in samples:
        students.setdefault(_student_key(sample), []).append(sample)

    results = []
    i = 0
    student_keys = sorted(students.keys(), key=_hs_sort_key)
    for hs_idx, hs_key in enumerate(student_keys, start=1):
        print(
            f"\n  === Học sinh {hs_key} ({hs_idx}/{len(student_keys)}, {len(students[hs_key])} câu) ===",
            flush=True,
        )
        for res in run_student(students[hs_key], barem_dict):
            i += 1
            sc, mx = res.get("score", 0), res.get("max_score", 0)
            pct = sc / mx * 100 if mx else 0
            print(
                f"  [{i:2d}/{len(samples)}] {res.get('sample_id','?'):14s} {sc:.2f}/{mx:.2f} ({pct:.0f}%) — {res.get('status')}",
                flush=True,
            )
            results.append(res)

    # Summary
    total_sc = sum(r.get("score", 0) for r in results)
    total_mx = sum(r.get("max_score", 0) for r in results)
    print(f"\n  TOTAL: {total_sc:.2f}/{total_mx:.2f} ({total_sc/total_mx*100:.1f}%)")

    summary = summarize_by_student(results)
    print_student_summary(summary)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"  Saved to: {output_path}")

        summary_path = str(Path(output_path).with_name("student_summary.json"))
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(f"  Saved to: {summary_path}")

    return results






def summarize_by_student(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Gom kết quả chấm (mỗi phần tử = 1 câu của 1 học sinh, theo sample_id
    dạng 'cau_{N}_{variant}__HS_{X}') thành báo cáo tổng quan theo từng học sinh:
    tổng điểm + danh sách câu/phần bị trừ điểm (VD '1a', '13c').
    """
    by_hs: Dict[str, Dict[str, Any]] = {}

    for r in results:
        m = re.search(r"(HS_\d+)$", r.get("sample_id", ""))
        hs_key = m.group(1) if m else r.get("sample_id", "?")
        entry = by_hs.setdefault(
            hs_key, {"hs": hs_key, "score": 0.0, "max_score": 0.0, "wrong": []}
        )
        entry["score"] += r.get("score", 0) or 0
        entry["max_score"] += r.get("max_score", 0) or 0

        q_num = r.get("question_number")
        criterion_results = r.get("criterion_results") or []
        if criterion_results:
            for cr in criterion_results:
                sc = cr.get("score", 0) or 0
                mx = cr.get("max_score", 0) or 0
                if sc < mx:
                    label = re.sub(r"_S\d+$", "", cr.get("part_label", "") or "")
                    tag = f"{q_num}" if label in ("", "main") else f"{q_num}{label}"
                    entry["wrong"].append(tag)
        elif (r.get("score", 0) or 0) < (r.get("max_score", 0) or 0):
            entry["wrong"].append(f"{q_num}")

    def _sort_key(tag: str):
        num_match = re.match(r"\d+", tag)
        return (int(num_match.group()) if num_match else 0, tag)

    summary = []
    for hs_key, e in by_hs.items():
        wrong_sorted = sorted(dict.fromkeys(e["wrong"]), key=_sort_key)
        summary.append(
            {
                "hs": hs_key,
                "score": round(e["score"], 2),
                "max_score": round(e["max_score"], 2),
                "wrong": wrong_sorted,
            }
        )
    summary.sort(key=lambda x: int(x["hs"].split("_")[-1]))
    return summary


def print_student_summary(summary: List[Dict[str, Any]]) -> None:
    print(f"\n{'='*80}")
    print("TỔNG QUAN THEO HỌC SINH")
    print(f"{'='*80}")
    for e in summary:
        wrong_str = ", ".join(e["wrong"]) if e["wrong"] else "-"
        print(
            f"  {e['hs']}: {e['score']:.2f}/{e['max_score']:.2f}đ, sai câu {wrong_str}"
        )


# ============================================================================
# QUICK SMOKE TEST
# ============================================================================


def smoke_test():
    """Kiểm tra nhanh các fix quan trọng không cần file thật."""
    print("=" * 60)
    print("SMOKE TEST — Kiểm tra các fix quan trọng")
    print("=" * 60)

    # FIX #1: validate không còn require teacher_barem
    sample_no_barem = {
        "sample_id": "cau_1_001",
        "question": {"text": "Câu 1", "parts": []},
        "student_answer": {
            "full_text": "3529",
            "lines": [],
            "tokens": [],
            "tables": [],
            "visual_answers": [],
        },
        "max_score": 0.5,
        "question_number": 1,
        "question_type": None,
    }
    v = validate_sample_schema(sample_no_barem, after_routing=False)
    assert v["valid"], f"FIX #1 FAIL: {v['errors']}"
    print("✅ FIX #1: validate_sample_schema không require teacher_barem")

    # FIX #2: get_student_evidence_for_slot đọc từ lines
    sample_with_lines = {
        "student_answer": {
            "full_text": "3529",
            "lines": [
                {
                    "line_id": "L1",
                    "part_label": "main",
                    "slot_id": "cau_1_001_main",
                    "text": "3529",
                    "bbox": [0, 0, 0, 0],
                    "confidence": 0.99,
                }
            ],
            "tokens": [
                {
                    "token_id": "W1",
                    "line_id": "L1",
                    "part_label": "main",
                    "slot_id": "cau_1_001_main",
                    "order": 1,
                    "text": "3529",
                    "bbox": [0, 0, 0, 0],
                    "confidence": 0.99,
                }
            ],
            "tables": [],
            "visual_answers": [],
        }
    }
    ev = get_student_evidence_for_slot(sample_with_lines, "main", ["cau_1_001_main"])
    assert ev["student_answer"] == "3529", f"FIX #2 FAIL: got '{ev['student_answer']}'"
    print("✅ FIX #2: get_student_evidence_for_slot đọc từ lines")

    # FIX #3: flatten_criteria
    entry_with_sub = {
        "sample_id": "cau_13",
        "question_number": 13,
        "score": 2.0,
        "sub_questions": [
            {
                "sub_label": "a",
                "criterion_id": "T13A",
                "score": 1.0,
                "question_type": "code",
                "sub_criteria": [
                    {"criterion_id": "T13A1", "score": 0.5, "content": "KiemtraSNT"},
                    {"criterion_id": "T13A2", "score": 0.5, "content": "TongSNT"},
                ],
            },
            {
                "sub_label": "b",
                "criterion_id": "T13B",
                "score": 0.5,
                "question_type": "code",
                "content": "TimMax",
            },
        ],
    }
    flat = flatten_criteria(entry_with_sub)
    assert len(flat) == 3, f"FIX #3 FAIL: expected 3, got {len(flat)}"
    assert flat[0]["criterion_id"] == "T13A1"
    assert flat[1]["criterion_id"] == "T13A2"
    assert flat[2]["criterion_id"] == "T13B"
    print("✅ FIX #3: flatten_criteria xử lý sub_questions/sub_criteria đúng")

    # FIX #4: prepare_conditional_output với restricted eval
    sample_idx7 = {**sample_no_barem, "student_index": 7}
    criterion_cond = {
        "criterion_id": "T3",
        "condition_source": {"type": "sample_field", "field": "student_index"},
        "conditional_outputs": [
            {
                "condition": "value % 4 == 3",
                "expected_outputs": ["57918"],
                "expected_output_tokens": ["5", "7", "9", "18"],
            },
            {"condition": "value % 4 == 0", "expected_outputs": ["24615"]},
        ],
    }
    resolved = prepare_conditional_output(sample_idx7, criterion_cond)
    assert resolved["matched"] is True, "FIX #4 FAIL: should match"
    assert resolved["expected_outputs"] == [
        "57918"
    ], f"FIX #4 FAIL: {resolved['expected_outputs']}"
    print(
        "✅ FIX #4: prepare_conditional_output với condition expression (student_index=7)"
    )

    # condition_source="self_reported": value đọc từ slot học sinh TỰ GHI
    # (khác FIX #4 dùng sample_field đọc thẳng student_index ground truth)
    sample_self_reported = {
        **sample_no_barem,
        "student_answer": {
            "full_text": "7",
            "lines": [
                {
                    "line_id": "L1",
                    "part_label": "main",
                    "slot_id": "cau_3_001_main_S1",
                    "text": "7",
                    "bbox": [0, 0, 0, 0],
                    "confidence": 0.99,
                }
            ],
            "tokens": [],
            "tables": [],
            "visual_answers": [],
        },
    }
    criterion_self_reported = {
        "criterion_id": "T3_main_s2",
        "condition_source": {
            "type": "self_reported",
            "slot_ids": ["cau_3_001_main_S1"],
        },
        "conditional_outputs": [
            {"condition": "value % 4 == 3", "expected_outputs": ["57918"]},
            {"condition": "value % 4 == 0", "expected_outputs": ["24615"]},
        ],
    }
    resolved_sr = prepare_conditional_output(
        sample_self_reported, criterion_self_reported
    )
    assert resolved_sr["matched"] is True, "FIX self_reported FAIL: should match"
    assert resolved_sr["expected_outputs"] == [
        "57918"
    ], f"FIX self_reported FAIL: {resolved_sr['expected_outputs']}"
    print("✅ FIX self_reported: condition_source đọc value từ slot học sinh tự ghi")

    # force_wrong: self_reported slot bị bỏ trống → chấm thẳng "wrong",
    # KHÔNG đẩy qua LLM/teacher review (matched=False vẫn cần phân biệt
    # với case "không match" thông thường)
    sample_blank_self_reported = {
        **sample_no_barem,
        "student_answer": {
            "full_text": "",
            "lines": [],
            "tokens": [],
            "tables": [],
            "visual_answers": [],
        },
    }
    resolved_blank = prepare_conditional_output(
        sample_blank_self_reported, criterion_self_reported
    )
    assert resolved_blank["matched"] is False, "FIX force_wrong FAIL: should not match"
    assert (
        resolved_blank["force_wrong"] is True
    ), "FIX force_wrong FAIL: force_wrong phải là True"
    print(
        "✅ FIX force_wrong: self_reported slot bỏ trống → force_wrong=True, không qua LLM"
    )

    # FIX #7: partial_credit_rule không downgrade full score
    sample_full = {
        **sample_with_lines,
        "question_number": 5,
        "student_index": 7,
        "question_type": "matching",
        "student_answer": {
            "full_text": "10 5 5",
            "lines": [
                {
                    "line_id": "L1",
                    "part_label": "main",
                    "slot_id": "cau_5_001_main",
                    "text": "10 5 5",
                    "bbox": [0, 0, 0, 0],
                    "confidence": 0.99,
                }
            ],
            "tokens": [
                {
                    "token_id": "W1",
                    "line_id": "L1",
                    "part_label": "main",
                    "slot_id": "cau_5_001_main",
                    "order": 1,
                    "text": "10",
                    "bbox": [0, 0, 0, 0],
                    "confidence": 0.99,
                },
                {
                    "token_id": "W2",
                    "line_id": "L1",
                    "part_label": "main",
                    "slot_id": "cau_5_001_main",
                    "order": 2,
                    "text": "5",
                    "bbox": [0, 0, 0, 0],
                    "confidence": 0.99,
                },
                {
                    "token_id": "W3",
                    "line_id": "L1",
                    "part_label": "main",
                    "slot_id": "cau_5_001_main",
                    "order": 3,
                    "text": "5",
                    "bbox": [0, 0, 0, 0],
                    "confidence": 0.99,
                },
            ],
            "tables": [],
            "visual_answers": [],
        },
    }
    criterion_q5 = {
        "criterion_id": "T5",
        "part_label": "main",
        "slot_ids": ["cau_5_001_main"],
        "score": 0.5,
        "expected_outputs": ["10 5 5"],
        "expected_output_tokens": ["10", "5", "5"],
        "partial_credit_rule": {
            "type": "count_correct_tokens",
            "partial_score": 0.25,
            "condition": "correct_token_count == 2",
        },
    }
    r = grade_expected_output_criterion(sample_full, criterion_q5)
    assert (
        r["score"] == 0.5
    ), f"FIX #7 FAIL: full answer should get 0.5, got {r['score']}"
    assert r["status"] == "correct"
    print("✅ FIX #7: partial_credit_rule không downgrade khi đúng 3/3 tokens")

    # partial_credit_rule dạng List[Dict] (nhiều tier) — chọn tier điểm cao
    # nhất trong số các tier có condition khớp
    sample_partial = {
        **sample_full,
        "student_answer": {
            **sample_full["student_answer"],
            "full_text": "10 5 9",
            "tokens": [
                {
                    "token_id": "W1",
                    "line_id": "L1",
                    "part_label": "main",
                    "slot_id": "cau_5_001_main",
                    "order": 1,
                    "text": "10",
                    "bbox": [0, 0, 0, 0],
                    "confidence": 0.99,
                },
                {
                    "token_id": "W2",
                    "line_id": "L1",
                    "part_label": "main",
                    "slot_id": "cau_5_001_main",
                    "order": 2,
                    "text": "5",
                    "bbox": [0, 0, 0, 0],
                    "confidence": 0.99,
                },
                {
                    "token_id": "W3",
                    "line_id": "L1",
                    "part_label": "main",
                    "slot_id": "cau_5_001_main",
                    "order": 3,
                    "text": "9",
                    "bbox": [0, 0, 0, 0],
                    "confidence": 0.99,
                },
            ],
            "lines": [
                {
                    "line_id": "L1",
                    "part_label": "main",
                    "slot_id": "cau_5_001_main",
                    "text": "10 5 9",
                    "bbox": [0, 0, 0, 0],
                    "confidence": 0.99,
                }
            ],
        },
    }
    criterion_q5_multitier = {
        **criterion_q5,
        "partial_credit_rule": [
            {
                "type": "count_correct_tokens",
                "partial_score": 0.15,
                "condition": "correct_token_count == 1",
            },
            {
                "type": "count_correct_tokens",
                "partial_score": 0.35,
                "condition": "correct_token_count == 2",
            },
        ],
    }
    r_multitier = grade_expected_output_criterion(
        sample_partial, criterion_q5_multitier
    )
    assert (
        r_multitier["score"] == 0.35
    ), f"FIX multitier FAIL: expected 0.35, got {r_multitier['score']}"
    print(
        "✅ FIX partial_credit_rule List[Dict]: chọn tier điểm cao nhất khớp condition"
    )

    # partial_credit_rule type="custom_condition" — dùng correct_token_count/
    # wrong_token_count qua safe_eval_condition
    criterion_q5_custom = {
        **criterion_q5,
        "partial_credit_rule": {
            "type": "custom_condition",
            "partial_score": 0.2,
            "condition": "correct_token_count >= 2 and wrong_token_count <= 1",
        },
    }
    r_custom = grade_expected_output_criterion(sample_partial, criterion_q5_custom)
    assert (
        r_custom["score"] == 0.2
    ), f"FIX custom_condition FAIL: expected 0.2, got {r_custom['score']}"
    print("✅ FIX partial_credit_rule custom_condition: eval correct/wrong_token_count")

    # safe_eval_condition: whitelist đúng 1 method .isdigit(), chặn method khác
    assert safe_eval_condition("value.isdigit()", {"value": "12a"}) is False
    assert (
        safe_eval_condition("value.isdigit() or value == 'blank'", {"value": "blank"})
        is True
    )
    try:
        safe_eval_condition("value.upper() == 'AB'", {"value": "ab"})
        raise AssertionError("FIX safe_eval_condition FAIL: phải chặn .upper()")
    except ValueError:
        pass
    print("✅ FIX safe_eval_condition: whitelist .isdigit(), chặn method khác")

    # grade_self_reported_index_criterion: đúng STT nhưng SAI định dạng
    # (VD "a=23") vẫn phải chấm sai — chỉ đúng khi ghi ĐÚNG NGUYÊN VĂN
    sample_stt_correct = {
        **sample_no_barem,
        "student_index": 23,
        "student_answer": {
            "full_text": "23",
            "lines": [
                {
                    "line_id": "L1",
                    "part_label": "stt",
                    "slot_id": "cau_x_stt",
                    "text": "23",
                    "bbox": [0, 0, 0, 0],
                    "confidence": 0.99,
                }
            ],
            "tokens": [],
            "tables": [],
            "visual_answers": [],
        },
    }
    criterion_stt = {
        "criterion_id": "T_stt",
        "part_label": "stt",
        "slot_ids": ["cau_x_stt"],
        "score": 0.5,
        "expected_value": {"rule": "match_student_index"},
    }
    r_stt_ok = grade_self_reported_index_criterion(sample_stt_correct, criterion_stt)
    assert (
        r_stt_ok["is_correct"] is True and r_stt_ok["score"] == 0.5
    ), f"FIX grade_self_reported_index FAIL (đúng): {r_stt_ok}"

    sample_stt_wrong_format = {
        **sample_stt_correct,
        "student_answer": {
            **sample_stt_correct["student_answer"],
            "lines": [
                {**sample_stt_correct["student_answer"]["lines"][0], "text": "a=23"}
            ],
        },
    }
    r_stt_fmt = grade_self_reported_index_criterion(
        sample_stt_wrong_format, criterion_stt
    )
    assert (
        r_stt_fmt["is_correct"] is False and r_stt_fmt["score"] == 0
    ), f"FIX grade_self_reported_index FAIL (sai định dạng): {r_stt_fmt}"
    print(
        "✅ FIX grade_self_reported_index_criterion: đúng số nhưng sai định dạng vẫn tính sai"
    )

    # FIX #9: JSON extraction
    test_responses = [
        '{"score": 0.5, "status": "correct"}',
        '```json\n{"score": 0.5, "status": "correct"}\n```',
        'Here is the result: {"score": 0.5, "status": "correct"} done.',
    ]
    for resp in test_responses:
        parsed = _extract_json_from_text(resp)
        assert (
            parsed is not None and parsed["score"] == 0.5
        ), f"FIX #9 FAIL on: {resp[:50]}"
    print("✅ FIX #9: _extract_json_from_text xử lý các dạng LLM response")

    print()
    print("✅ Tất cả smoke tests PASS")
    print("=" * 60)


# ============== Main entry point ==============

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Grading Pipeline",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Vi du:
  python pipeline.py --test
  python pipeline.py --input testing/input/test_1_HS.json --barem sample_parem.json
        """,
    )
    parser.add_argument("--input", "-i", default="testing/input/test_1_HS.json")
    parser.add_argument("--barem", "-b", default="sample_parem.json")
    parser.add_argument("--output-dir", "-o", default="testing/output")
    parser.add_argument("--test", action="store_true")

    args = parser.parse_args()

    if args.test:
        smoke_test()
        sys.exit(0)

    missing = []
    if not Path(args.input).exists():
        missing.append(f"  test_input: '{args.input}'")
    if not Path(args.barem).exists():
        missing.append(f"  barem: '{args.barem}'")
    if missing:
        print("Khong tim thay file:")
        print("\n".join(missing))
        sys.exit(1)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    out = str(output_dir / "grading_results.json")
    print(f"\n{'='*60}")
    print("  System 4 (LLM_Advisory)")
    print(f"  Input : {args.input}")
    print(f"  Barem : {args.barem}")
    print(f"  Output: {out}")
    print(f"{'='*60}")
    run_batch(
        test_input_path=args.input,
        barem_path=args.barem,
        output_path=out,
    )
    print(f"\n==> Saved: {out}")
