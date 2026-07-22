"""
Multi-format Rubric-based Grading Pipeline
==========================================
Fixed version — addresses 11 issues from code review.
"""

import re
import json
import os
import sys
import time
import requests
import argparse

from dotenv import load_dotenv
load_dotenv()

from pathlib import Path
from difflib import SequenceMatcher
from typing import Dict, List, Any, Optional, Tuple

import pandas as pd

pd.set_option("display.max_colwidth", 200)

# ============================================================================
# FIX #10: API key từ env var, không hardcode
# ============================================================================
CFG = {
    "use_llm": True,
    "model_name": os.environ.get("LLM_MODEL_NAME", "qwen2.5vlinstruct"),
    "base_url": os.environ.get("LLM_BASE_URL", ""),
    "model_api": os.environ.get("LLM_MODEL_API", ""),
    "api_key": os.environ.get("LLM_API_KEY", ""),
    "use_finetuned_model": False,
    "teacher_review_threshold": 0.65,
    "enable_static_analysis": True,
    "enable_rubric_mapping": True,
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
        ├─ sub_criteria[]  → yield từng criterion con với kế thừa part_label/question_type
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
                    criterion["part_label"] = item.get("part_label") or item.get("sub_label")
                if "question_type" not in criterion:
                    criterion["question_type"] = item.get(
                        "question_type", entry.get("question_type")
                    )
                if group_all_or_nothing:
                    criterion["group_id"] = item.get("criterion_id")
                    criterion["group_all_or_nothing"] = True
                    criterion["group_max_score"] = item.get("score", 0)
                flat.append(criterion)
        else:
            criterion = dict(item)
            if "part_label" not in criterion:
                criterion["part_label"] = item.get("sub_label") or item.get("part_label")
            flat.append(criterion)

    return flat


def load_barem(barem_path: str) -> Dict[int, List[Dict[str, Any]]]:
    """
    Load sample_parem_fixed.json → dict[question_number → flat criteria list].
    FIX #3: dùng flatten_criteria() để xử lý cấu trúc sub_questions.
    """
    barem_dict: Dict[int, List[Dict[str, Any]]] = {}
    path = Path(barem_path)

    if not path.exists():
        print(f"⚠ Không tìm thấy file barem: {barem_path}")
        return barem_dict

    with open(path, "r", encoding="utf-8") as f:
        barem_data = json.load(f)

    for entry in barem_data.get("teacher_barem", []):
        q_num = entry.get("question_number")
        if q_num is None:
            continue
        if q_num not in barem_dict:
            barem_dict[q_num] = []
        barem_dict[q_num].extend(flatten_criteria(entry))

    print(f"[OK] Loaded barem: {len(barem_dict)} question groups")
    print(f"  Questions: {sorted(barem_dict.keys())}")
    for q, clist in sorted(barem_dict.items()):
        ids = [c.get("criterion_id", "?") for c in clist]
        print(f"  Q{q}: {ids}")

    return barem_dict


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def normalize_text(text: Any) -> str:
    if  text is None:
        return ""
    text = str(text).lower().strip()
    text = re.sub(r"\s+", " ", text)
    text = text.replace("（", "(").replace("）", ")")
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\uff0c", ",").replace("\uff1a", ":").replace("\uff1b", ";")
    return text


def tokenize_answer(text: Any) -> List[str]:
    if text is None:
        return []
    text = str(text).strip()
    if not text:
        return []
    if re.search(r"\s+", text):
        return [t for t in re.split(r"\s+", text) if t]
    return [text]


def normalize_output_text(text: Any) -> str:
    if text is None:
        return ""
    text = str(text).strip()
    text = re.sub(r"\s+", "", text)
    return text


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_text(a), normalize_text(b)).ratio()


def safe_json_dumps(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)


def clamp_score(
    score: float, min_score: float = 0, max_score: Optional[float] = None
) -> float:
    if max_score is not None:
        return max(min_score, min(score, max_score))
    return max(min_score, score)


# ============================================================================
# FIX #2: get_student_evidence_for_part — đọc từ lines/tokens thay vì part_answers
# ============================================================================


def get_student_evidence_for_part(
    sample: Dict[str, Any], part_label: str = None, slot_ids: List[str] = None
) -> Dict[str, Any]:
    """
    Trích xuất câu trả lời của SV cho một part cụ thể.

    Lookup ưu tiên:
      1. slot_ids (primary): lọc lines/tokens có line["slot_id"] in slot_ids
      2. part_label (fallback): lọc theo part_label khi không có slot_id trên lines

    Returns:
        {
            "text": str,
            "lines": [...],
            "tokens": [...],
            "tables": [...],
            "visual_answers": [...],
            "part_label": str,
            "type": "full" | "partial" | "blank" | "fallback",
            "found": bool
        }
    """
    student_answer = sample.get("student_answer", {}) or {}
    all_lines = student_answer.get("lines", []) or []
    all_tokens = student_answer.get("tokens", []) or []
    all_tables = student_answer.get("tables", []) or []
    all_visuals = student_answer.get("visual_answers", []) or []

    if not part_label and not slot_ids:
        # Không lọc — trả về toàn bộ
        return {
            "text": student_answer.get("full_text", "") or "",
            "lines": all_lines,
            "tokens": all_tokens,
            "tables": all_tables,
            "visual_answers": all_visuals,
            "part_label": None,
            "type": "full",
            "found": bool(student_answer.get("full_text", "")),
        }

    # Primary: slot_id matching (khi lines có slot_id và slot_ids được cung cấp)
    use_slot_lookup = bool(slot_ids) and any(l.get("slot_id") for l in all_lines)
    if use_slot_lookup:
        slot_id_set = set(slot_ids)
        part_lines = [
            l for l in all_lines
            if l.get("slot_id") in slot_id_set and not l.get("is_blank", False)
        ]
        part_tokens = [t for t in all_tokens if t.get("slot_id") in slot_id_set]
        part_tables = [tb for tb in all_tables if tb.get("slot_id") in slot_id_set]
        part_visuals = [
            v for v in all_visuals
            if v.get("slot_id") in slot_id_set and not v.get("is_blank", False)
        ]
    else:
        # Fallback: lọc theo part_label
        part_lines = [
            l for l in all_lines
            if l.get("part_label") == part_label and not l.get("is_blank", False)
        ]
        part_tokens = [t for t in all_tokens if t.get("part_label") == part_label]
        part_tables = [tb for tb in all_tables if tb.get("part_label") == part_label]
        part_visuals = [
            v for v in all_visuals
            if v.get("part_label") == part_label and not v.get("is_blank", False)
        ]

    if part_lines or part_tokens or part_tables or part_visuals:
        # Ghép text từ lines
        text = " ".join(
            l.get("text", "") for l in part_lines if l.get("text", "")
        ).strip()
        if not text and part_tokens:
            text = " ".join(
                t.get("text", "") for t in part_tokens if t.get("text", "")
            ).strip()
        return {
            "text": text,
            "lines": part_lines,
            "tokens": part_tokens,
            "tables": part_tables,
            "visual_answers": part_visuals,
            "part_label": part_label,
            "type": "partial",
            "found": True,
        }

    # FIX: Kiểm tra part có dòng blank có chủ ý không
    if use_slot_lookup:
        slot_id_set = set(slot_ids)
        explicit_blank = any(
            l.get("slot_id") in slot_id_set and l.get("is_blank", False)
            for l in all_lines
        ) or any(
            v.get("slot_id") in slot_id_set and v.get("is_blank", False)
            for v in all_visuals
        )
    else:
        explicit_blank = any(
            l.get("part_label") == part_label and l.get("is_blank", False)
            for l in all_lines
        ) or any(
            v.get("part_label") == part_label and v.get("is_blank", False)
            for v in all_visuals
        )

    if explicit_blank:
        # Bỏ trống có chủ ý — KHÔNG fallback full_text
        return {
            "text": "",
            "lines": [],
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
        "text": full_text,
        "lines": all_lines,
        "tokens": all_tokens,
        "tables": all_tables,
        "visual_answers": all_visuals,
        "part_label": part_label,
        "type": "fallback",
        "found": False,
    }


def build_student_sample_index(
    samples: List[Dict[str, Any]],
) -> Dict[int, Dict[str, Any]]:
    """Index samples theo question_number."""
    index = {}
    for sample in samples:
        q_num = sample.get("question_number")
        if q_num is not None:
            index[q_num] = sample
    return index


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


def call_llm_json(
    prompt: str, schema_name: str = "generic", retries: int = 3
) -> Dict[str, Any]:
    """
    Gọi LLM API và trả về JSON.
    FIX #9: dùng _extract_json_from_text() thay vì greedy regex.
    FIX #10: api_key đọc từ CFG (env-sourced), không hardcode.
    """
    if not CFG["use_llm"]:
        return {
            "llm_used": False,
            "schema_name": schema_name,
            "message": "LLM is disabled. Using heuristic grader instead.",
        }

    model_name = CFG.get("model_name")
    model_api = CFG.get("model_api")
    api_key = CFG.get("api_key")

    if not model_name:
        raise ValueError("Chưa cấu hình CFG['model_name'].")
    if not model_api:
        raise ValueError("Chưa cấu hình CFG['model_api'].")

    last_error = None
    for attempt in range(retries):
        try:
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            payload = {
                "model": model_name,
                "messages": [
                    {
                        "role": "system",
                        "content": "Return only valid JSON. No markdown, no explanation.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0,
            }

            response = requests.post(
                model_api, headers=headers, json=payload, timeout=120
            )
            response.raise_for_status()

            resp_json = response.json()
            resp_text = (
                resp_json.get("choices", [{}])[0].get("message", {}).get("content", "")
            )
            if not resp_text:
                resp_text = resp_json.get("output_text", "")

            parsed = _extract_json_from_text(resp_text)
            if parsed is not None:
                return parsed

            # Không parse được → retry
            last_error = f"Cannot parse JSON from: {resp_text[:200]}"

        except Exception as e:
            last_error = str(e)
            if attempt < retries - 1:
                continue

    return {
        "llm_used": True,
        "schema_name": schema_name,
        "error": last_error,
        "message": f"LLM API failed after {retries} retries: {last_error}",
    }


# ============================================================================
# VALIDATION — FIX #1: bỏ teacher_barem khỏi required_fields
# FIX #11: sau routing, lấy question_type từ parem thay vì chỉ dùng heuristic
# ============================================================================


def validate_sample_schema(
    sample: Dict[str, Any],
    after_routing: bool = False,
    barem_dict: Dict[int, List[Dict]] = None,
) -> Dict[str, Any]:
    """
    FIX #1: 'teacher_barem' KHÔNG còn là required field.
    FIX #11: Sau routing, accept question_type từ parem lookup.
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
        # FIX #11: question_type có thể vẫn null nếu parem lookup chưa set
        # Không raise error — chỉ warn, vì routing có thể chưa chạy
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


# ============================================================================
# ROUTING — FIX #11: ưu tiên lấy question_type từ parem
# ============================================================================


def compute_routing_confidence(sample: Dict[str, Any]) -> Dict[str, Any]:
    """Heuristic weighted-sum routing."""
    question = sample.get("question", {})
    question_text_raw = question.get("text", "") or ""
    question_text = normalize_text(question_text_raw)
    parts = question.get("parts", []) or []
    student_answer = sample.get("student_answer", {}) or {}
    teacher_barem = sample.get("teacher_barem", []) or []

    visuals = student_answer.get("visual_answers", []) or []
    has_visual = bool(visuals)
    visual_types = [v.get("type", "") for v in visuals]
    has_question_tables = any(len(p.get("tables", [])) > 0 for p in parts)
    has_student_tables = bool(student_answer.get("tables"))
    has_expected_output = any(
        c.get("expected_output") is not None for c in teacher_barem
    )
    has_expected_value = any(bool(c.get("expected_value")) for c in teacher_barem)
    has_multiple_parts = len(parts) > 1
    full_text = student_answer.get("full_text", "") or ""

    q_has_code = bool(
        re.search(
            r"#include|\bcout\b|\bprintf\b|\bprint\(|;", question_text_raw, flags=re.I
        )
    )
    a_has_code = bool(re.search(r"\bprint\(|;|\{|\}", full_text))

    WEIGHTS = {
        "visual": 0.9,
        "chart": 0.8,
        "table": 0.7,
        "expected_output": 0.85,
        "expected_value": 0.55,
        "q_code": 0.6,
        "a_code": 0.6,
        "blank": 0.5,
        "essay": 0.45,
        "multi": 0.35,
    }

    candidates: Dict[str, float] = {}

    if has_visual:
        if any(vt in ["flowchart", "diagram"] for vt in visual_types):
            candidates["visual_flowchart"] = (
                candidates.get("visual_flowchart", 0) + WEIGHTS["visual"]
            )
        if any(
            vt in ["chart", "bar_chart", "line_chart", "pie_chart"]
            for vt in visual_types
        ):
            candidates["chart_drawing"] = (
                candidates.get("chart_drawing", 0) + WEIGHTS["chart"]
            )

    if has_question_tables or has_student_tables:
        candidates["table_completion"] = (
            candidates.get("table_completion", 0) + WEIGHTS["table"]
        )

    if (
        has_expected_output
        or q_has_code
        or re.search(r"kết quả in ra|output", question_text)
    ):
        key = "program_trace_output"
        candidates[key] = candidates.get(key, 0) + (
            WEIGHTS["expected_output"] if has_expected_output else WEIGHTS["q_code"]
        )

    if "____" in question_text_raw or re.search(r"\bđiền|chỗ trống", question_text_raw):
        candidates["fill_in_the_blank"] = (
            candidates.get("fill_in_the_blank", 0) + WEIGHTS["blank"]
        )

    if re.search(r"giải thích|trình bày|nêu|vì sao", question_text):
        candidates["short_answer_or_essay"] = (
            candidates.get("short_answer_or_essay", 0) + WEIGHTS["essay"]
        )

    if has_multiple_parts:
        candidates["mixed_multi_part"] = (
            candidates.get("mixed_multi_part", 0) + WEIGHTS["multi"]
        )

    if has_expected_value:
        candidates["rubric_expected_value"] = (
            candidates.get("rubric_expected_value", 0) + WEIGHTS["expected_value"]
        )

    heuristic_candidates = [
        {"type": t, "score": min(1.0, s), "evidence": "heuristic"}
        for t, s in candidates.items()
    ]
    heuristic_candidates.sort(key=lambda x: x["score"], reverse=True)
    top = (
        heuristic_candidates[0]
        if heuristic_candidates
        else {"type": "unknown", "score": 0.0}
    )

    return {
        "candidates": heuristic_candidates,
        "top_type": top.get("type"),
        "top_score": round(top.get("score", 0.0), 3),
    }


def apply_question_routing(
    sample: Dict[str, Any], barem_dict: Dict[int, List[Dict]] = None
) -> Dict[str, Any]:
    """
    FIX #11: Ưu tiên question_type từ parem lookup.
    Nếu parem có question_type → dùng ngay, không cần heuristic.
    """
    routed = dict(sample)

    # Lấy question_type từ parem nếu có
    q_num = sample.get("question_number")
    parem_qtype = None
    if barem_dict and q_num and barem_dict.get(q_num):
        # Tìm entry gốc trong barem để lấy question_type
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

    # Fallback: heuristic routing
    result = compute_routing_confidence(routed)
    routed["question_type"] = result["top_type"]
    routed["routing"] = {
        "question_type": result["top_type"],
        "confidence": result["top_score"],
        "reason": f"Heuristic: {result['top_type']} (conf={result['top_score']:.3f})",
        "candidates": result["candidates"],
        "uses_llm": False,
        "method": "heuristic",
    }
    return routed


# ============================================================================
# CONDITIONAL OUTPUT RESOLVER — FIX #4: safe eval + nhất quán tên biến
# ============================================================================


def resolve_conditional_output(
    sample: Dict[str, Any], criterion: Dict[str, Any]
) -> Dict[str, Any]:
    """
    FIX #4: eval với restricted scope để tránh injection.
    Tên biến nhất quán: luôn dùng 'student_index'.
    """
    conditional_outputs = criterion.get("conditional_outputs", [])

    if not conditional_outputs:
        return {
            "expected_output": criterion.get("expected_output"),
            "expected_output_tokens": criterion.get("expected_output_tokens", []),
            "partial_credit_rule": criterion.get("partial_credit_rule"),
            "matched": False,
            "reason": "No conditional_outputs in criterion",
        }

    # FIX #8: đọc trực tiếp từ sample, không cần parse sample_id
    student_index = sample.get("student_index")

    # Case 1: match by student_indices list
    for cond in conditional_outputs:
        if "student_indices" in cond and student_index is not None:
            if student_index in cond.get("student_indices", []):
                return {
                    "expected_output": cond.get("expected_output"),
                    "expected_output_tokens": cond.get("expected_output_tokens", []),
                    "partial_credit_rule": criterion.get("partial_credit_rule"),
                    "matched": True,
                    "reason": f"Matched student_indices: student_index={student_index}",
                }

    # Case 2: match by condition expression
    # FIX #4: restricted eval scope, không dùng locals()
    for cond in conditional_outputs:
        if "condition" in cond and student_index is not None:
            condition_expr = cond.get("condition", "")
            try:
                result = eval(
                    condition_expr,
                    {"__builtins__": {}},  # no builtins
                    {"student_index": student_index},  # chỉ cho phép biến này
                )
                if result:
                    return {
                        "expected_output": cond.get("expected_output"),
                        "expected_output_tokens": cond.get(
                            "expected_output_tokens", []
                        ),
                        "partial_credit_rule": criterion.get("partial_credit_rule"),
                        "matched": True,
                        "reason": f"Matched condition: '{condition_expr}' with student_index={student_index}",
                    }
            except Exception as e:
                print(f"⚠ Condition eval failed: '{condition_expr}' — {e}")

    return {
        "expected_output": criterion.get("expected_output"),
        "expected_output_tokens": criterion.get("expected_output_tokens", []),
        "partial_credit_rule": criterion.get("partial_credit_rule"),
        "matched": False,
        "reason": "No matching conditional output found",
    }


# ============================================================================
# GRADERS — FIX #5: define v2 TRƯỚC grade_criterion
# FIX #7: partial_credit_rule chỉ apply khi ratio < 1
# ============================================================================


def grade_expected_output_criterion_v2(
    sample: Dict[str, Any], criterion: Dict[str, Any]
) -> Dict[str, Any]:
    """
    System 1 v2: xử lý cả fixed output và conditional output.
    FIX #7: partial_credit_rule chỉ apply khi ratio < 1 (tránh downgrade full score).
    """
    part_label = criterion.get("part_label")
    max_score = criterion.get("score", 0)

    resolved = resolve_conditional_output(sample, criterion)
    expected_output = resolved.get("expected_output")
    expected_output_tokens = resolved.get("expected_output_tokens", [])
    partial_credit_rule = resolved.get("partial_credit_rule")

    evidence = get_student_evidence_for_part(sample, part_label, criterion.get("slot_ids", []))
    student_text = evidence.get("text", "")
    detected_errors = []

    # ── Case 0: expected_output_lines (T8A — địa chỉ bộ nhớ) ────────────
    expected_output_lines = criterion.get("expected_output_lines", [])
    if expected_output_lines:
        student_lines = [
            l.get("text", "").strip()
            for l in evidence.get("lines", [])
            if l.get("text", "").strip()
        ]
        correct_count = sum(
            1 for line in expected_output_lines
            if line in student_lines or any(line in sl for sl in student_lines)
        )
        rule = partial_credit_rule or {}
        rule_type = rule.get("type", "")

        if rule_type == "min_correct_lines":
            threshold = rule.get("threshold", 0)
            score = (
                rule.get("score_if_above_threshold", max_score)
                if correct_count >= threshold
                else rule.get("score_if_below_threshold", 0)
            )
        else:
            score = max_score * (correct_count / max(1, len(expected_output_lines)))

        status = (
            "correct"
            if correct_count == len(expected_output_lines)
            else ("partially_correct" if score > 0 else "wrong")
        )
        return {
            "criterion_id": criterion.get("criterion_id"),
            "part_label": part_label,
            "criterion_content": criterion.get("content", ""),
            "score": round(score, 4),
            "max_score": max_score,
            "status": status,
            "is_correct": correct_count == len(expected_output_lines),
            "expected_output_lines": expected_output_lines,
            "student_lines": student_lines,
            "correct_lines_count": correct_count,
            "evidence": evidence,
            "reason": f"{correct_count}/{len(expected_output_lines)} address lines correct.",
            "detected_errors": [],
        }

    # ── Pre-check: accepted_outputs match trước token-by-token ───────────
    # Xử lý:
    # 1) SV ghi gộp ('3529') trong khi expected_tokens là ['3','5','2','9']
    # 2) SV ghi '10/1/2026' trong khi expected_tokens là ['10','1','2026']
    # 3) SV ghi nhiều dòng (dòng đầu là giá trị nhập, dòng cuối là đáp án)
    accepted_outputs_pre = list(criterion.get("accepted_outputs", []))
    if expected_output is not None and expected_output not in accepted_outputs_pre:
        accepted_outputs_pre = [expected_output] + accepted_outputs_pre

    accepted_norm_raw_pre = [normalize_text(x) for x in accepted_outputs_pre]
    accepted_norm_ns_pre = [normalize_output_text(x) for x in accepted_outputs_pre]

    # Tập candidate texts: full text + từng dòng riêng (xử lý câu có line 'a=7' + line '57918')
    part_lines = evidence.get("lines", [])
    candidate_texts = [student_text]
    if len(part_lines) > 1:
        candidate_texts += [
            l.get("text", "") for l in part_lines if l.get("text", "").strip()
        ]

    for cand in candidate_texts:
        if (
            normalize_text(cand) in accepted_norm_raw_pre
            or normalize_output_text(cand) in accepted_norm_ns_pre
        ):
            return {
                "criterion_id": criterion.get("criterion_id"),
                "part_label": part_label,
                "criterion_content": criterion.get("content", ""),
                "score": max_score,
                "max_score": max_score,
                "status": "correct",
                "is_correct": True,
                "expected_output": expected_output,
                "student_answer_text": student_text,
                "evidence": evidence,
                "reason": "Student answer matches accepted output (pre-check).",
                "detected_errors": [],
                "conditional_resolved": resolved.get("matched", False),
                "conditional_reason": resolved.get("reason"),
            }

    # ── Case 1: token matching ────────────────────────────────────────────
    if expected_output_tokens:
        student_tokens = tokenize_answer(student_text)
        token_evals = []
        correct_count = 0

        for i, expected_token in enumerate(expected_output_tokens):
            student_token = student_tokens[i] if i < len(student_tokens) else None
            is_correct = normalize_text(student_token) == normalize_text(expected_token)
            if is_correct:
                correct_count += 1
            token_evals.append(
                {
                    "index": i,
                    "expected": expected_token,
                    "student": student_token,
                    "is_correct": is_correct,
                }
            )
            if not is_correct:
                detected_errors.append(
                    {
                        "error_type": "wrong_output_token",
                        "token_index": i,
                        "expected": expected_token,
                        "student": student_token,
                        "message": f"Token {i}: expected='{expected_token}', student='{student_token}'",
                    }
                )

        ratio = correct_count / max(1, len(expected_output_tokens))
        score = max_score * ratio  # default: proportional

        # FIX #7: chỉ apply partial_credit_rule khi chưa full score
        if partial_credit_rule and ratio < 1.0:
            rule_type = partial_credit_rule.get("type", "")
            wrong_count = len(expected_output_tokens) - correct_count

            try:
                if rule_type == "count_wrong_tokens":
                    wrong_token_count = wrong_count  # noqa: used in eval
                    cond = partial_credit_rule.get("condition", "")
                    if cond and eval(
                        cond, {"__builtins__": {}}, {"wrong_token_count": wrong_count}
                    ):
                        score = partial_credit_rule.get("partial_score", 0)

                elif rule_type == "count_correct_tokens":
                    cond = partial_credit_rule.get("condition", "")
                    if cond and eval(
                        cond,
                        {"__builtins__": {}},
                        {"correct_token_count": correct_count},
                    ):
                        score = partial_credit_rule.get("partial_score", 0)

                elif rule_type in ("min_correct_tokens", "min_correct_lines"):
                    threshold = partial_credit_rule.get("threshold", 0)
                    score = (
                        partial_credit_rule.get("score_if_above_threshold", max_score)
                        if correct_count >= threshold
                        else partial_credit_rule.get("score_if_below_threshold", 0)
                    )

                elif rule_type == "date_partial_match":
                    # câu 12: tháng và năm đúng → 0.25
                    cond = partial_credit_rule.get("condition", "")
                    tokens_dict = {t["expected"]: t["is_correct"] for t in token_evals}
                    # kiểm tra month=1 và year=2026
                    if "1" in [
                        t["expected"] for t in token_evals if t["is_correct"]
                    ] and "2026" in [
                        t["expected"] for t in token_evals if t["is_correct"]
                    ]:
                        score = partial_credit_rule.get("partial_score", 0)

                elif rule_type == "position_tolerance":
                    # câu 10: sai ở <=2 vị trí đầu hoặc <=2 cuối → 0.25
                    wrong_positions = [
                        i for i, t in enumerate(token_evals) if not t["is_correct"]
                    ]
                    n = len(expected_output_tokens)
                    if wrong_positions and all(
                        p < 2 or p >= n - 2 for p in wrong_positions
                    ):
                        score = partial_credit_rule.get("partial_score", 0)

            except Exception as e:
                print(f"⚠ partial_credit_rule eval failed: {e}")

        if ratio == 1.0:
            status = "correct"
            reason = "All output tokens correct."
        elif score > 0:
            status = "partially_correct"
            reason = f"{correct_count}/{len(expected_output_tokens)} tokens correct (partial credit applied)."
        else:
            status = "wrong"
            reason = "No output token correct."

        return {
            "criterion_id": criterion.get("criterion_id"),
            "part_label": part_label,
            "criterion_content": criterion.get("content", ""),
            "score": round(score, 4),
            "max_score": max_score,
            "status": status,
            "is_correct": ratio == 1.0,
            "expected_output": expected_output,
            "expected_output_tokens": expected_output_tokens,
            "student_answer_text": student_text,
            "student_tokens": student_tokens,
            "token_evaluations": token_evals,
            "evidence": evidence,
            "reason": reason,
            "detected_errors": detected_errors,
            "conditional_resolved": resolved.get("matched", False),
            "conditional_reason": resolved.get("reason"),
        }

    # ── Case 2: raw / fuzzy match ─────────────────────────────────────────
    accepted_outputs = list(criterion.get("accepted_outputs", []))
    if expected_output is not None:
        accepted_outputs = [expected_output] + accepted_outputs

    student_norm_raw = normalize_text(student_text)
    student_norm_no_space = normalize_output_text(student_text)
    accepted_norm_raw = [normalize_text(x) for x in accepted_outputs]
    accepted_norm_no_space = [normalize_output_text(x) for x in accepted_outputs]

    if (
        student_norm_raw in accepted_norm_raw
        or student_norm_no_space in accepted_norm_no_space
    ):
        score = max_score
        status = "correct"
        reason = "Student answer matches accepted output."
    else:
        best_sim, best_answer = 0.0, None
        for ans in accepted_outputs:
            sim = max(
                similarity(student_text, ans),
                SequenceMatcher(
                    None, student_norm_no_space, normalize_output_text(ans)
                ).ratio(),
            )
            if sim > best_sim:
                best_sim, best_answer = sim, ans

        if best_sim >= 0.85:
            score = max_score
            status = "correct_by_fuzzy_match"
            reason = f"Very similar to expected output: '{best_answer}'"
        elif best_sim >= 0.65:
            score = max_score * 0.5
            status = "partially_correct"
            reason = f"Partially similar to expected output: '{best_answer}'"
        else:
            score = 0
            status = "wrong"
            reason = "Does not match expected output."
            detected_errors.append(
                {
                    "error_type": "wrong_expected_output",
                    "expected_output": expected_output,
                    "student_answer": student_text,
                    "message": "Đáp án không khớp expected_output.",
                }
            )

    return {
        "criterion_id": criterion.get("criterion_id"),
        "part_label": part_label,
        "criterion_content": criterion.get("content", ""),
        "score": round(score, 4),
        "max_score": max_score,
        "status": status,
        "is_correct": score == max_score,
        "expected_output": expected_output,
        "accepted_outputs": accepted_outputs,
        "student_answer_text": student_text,
        "evidence": evidence,
        "reason": reason,
        "detected_errors": detected_errors,
        "conditional_resolved": resolved.get("matched", False),
        "conditional_reason": resolved.get("reason"),
    }


def grade_expected_value_criterion(
    sample: Dict[str, Any], criterion: Dict[str, Any]
) -> Dict[str, Any]:
    part_label = criterion.get("part_label")
    max_score = criterion.get("score", 0)
    expected_value = criterion.get("expected_value", {})

    evidence = get_student_evidence_for_part(sample, part_label, criterion.get("slot_ids", []))
    student_text = evidence.get("text", "")
    student_norm = normalize_text(student_text)

    if not expected_value:
        return {
            "criterion_id": criterion.get("criterion_id"),
            "part_label": part_label,
            "criterion_content": criterion.get("content", ""),
            "score": 0,
            "max_score": max_score,
            "status": "needs_llm_or_teacher_review",
            "is_correct": False,
            "reason": "No expected_value provided.",
            "teacher_review_required": True,
            "detected_errors": [],
        }

    matched, missing = [], []
    for key, value in expected_value.items():
        value_norm = normalize_text(str(value))
        if value_norm and value_norm in student_norm:
            matched.append({"key": key, "value": value})
        else:
            missing.append({"key": key, "value": value})

    ratio = len(matched) / max(1, len(expected_value))
    score = round(max_score * ratio, 4)

    status = (
        "correct" if ratio == 1 else ("partially_correct" if ratio > 0 else "wrong")
    )
    reason = (
        "All expected values found."
        if ratio == 1
        else f"{len(matched)}/{len(expected_value)} expected values found."
    )

    return {
        "criterion_id": criterion.get("criterion_id"),
        "part_label": part_label,
        "criterion_content": criterion.get("content", ""),
        "score": score,
        "max_score": max_score,
        "status": status,
        "is_correct": ratio == 1,
        "matched": matched,
        "missing": missing,
        "evidence": evidence,
        "reason": reason,
        "detected_errors": [
            {
                "error_type": "missing_expected_value",
                "key": m["key"],
                "expected": m["value"],
                "message": f"Không tìm thấy {m['key']}={m['value']} trong đáp án.",
            }
            for m in missing
        ],
    }


def grade_table_criterion(
    sample: Dict[str, Any], criterion: Dict[str, Any]
) -> Dict[str, Any]:
    part_label = criterion.get("part_label")
    max_score = criterion.get("score", 0)
    evidence = get_student_evidence_for_part(sample, part_label, criterion.get("slot_ids", []))
    tables = evidence.get("tables", [])

    if not tables:
        return {
            "criterion_id": criterion.get("criterion_id"),
            "part_label": part_label,
            "criterion_content": criterion.get("content", ""),
            "score": 0,
            "max_score": max_score,
            "status": "wrong",
            "is_correct": False,
            "reason": "No table answer found.",
            "detected_errors": [
                {
                    "error_type": "missing_table_answer",
                    "message": "Không tìm thấy đáp án dạng bảng.",
                }
            ],
        }

    row_id = criterion.get("row_id")
    column_map = criterion.get("column_map")
    expected_value = criterion.get("expected_value")

    if row_id and column_map and expected_value:
        return grade_table_row_criterion(
            criterion, tables, row_id, column_map, expected_value, evidence,
            part_label, max_score,
        )

    all_cell_texts = [
        cell.get("text", "")
        for table in tables
        for cell in table.get("cells", [])
        if not cell.get("is_blank", False)
    ]

    fake_sample = dict(sample)
    fake_sample["student_answer"] = dict(sample["student_answer"])
    fake_sample["student_answer"]["full_text"] = " ".join(all_cell_texts)

    if criterion.get("expected_output") is not None or criterion.get(
        "expected_output_tokens"
    ):
        result = grade_expected_output_criterion_v2(fake_sample, criterion)
    else:
        result = grade_expected_value_criterion(fake_sample, criterion)

    result["student_table_text"] = fake_sample["student_answer"]["full_text"]
    result["evidence"] = evidence
    return result


def grade_table_row_criterion(
    criterion: Dict[str, Any],
    tables: List[Dict[str, Any]],
    row_id: str,
    column_map: Dict[str, str],
    expected_value: Dict[str, Any],
    evidence: Dict[str, Any],
    part_label: Optional[str],
    max_score: float,
) -> Dict[str, Any]:
    """
    Chấm criterion table theo đúng vị trí (row_id + col_id), không gộp text.
    column_map: {key trong expected_value: col_id}, VD {"input": "C1", "output": "C2"}.
    """
    cells_by_id = {
        cell.get("cell_id"): cell
        for table in tables
        for cell in table.get("cells", [])
    }

    matched, missing = [], []
    for key, expected in expected_value.items():
        col_id = column_map.get(key)
        cell = cells_by_id.get(f"{row_id}{col_id}") if col_id else None
        cell_text = cell.get("text", "") if cell else ""
        is_blank = cell.get("is_blank", False) if cell else True
        if (
            cell
            and not is_blank
            and normalize_text(str(expected)) in normalize_text(cell_text)
        ):
            matched.append({"key": key, "value": expected})
        else:
            missing.append({"key": key, "value": expected, "col_id": col_id})

    ratio = len(matched) / max(1, len(expected_value))
    score = round(max_score * ratio, 4)
    status = "correct" if ratio == 1 else ("partially_correct" if ratio > 0 else "wrong")

    return {
        "criterion_id": criterion.get("criterion_id"),
        "part_label": part_label,
        "criterion_content": criterion.get("content", ""),
        "score": score,
        "max_score": max_score,
        "status": status,
        "is_correct": ratio == 1,
        "matched": matched,
        "missing": missing,
        "row_id": row_id,
        "evidence": evidence,
        "reason": (
            f"All expected values found at row {row_id}."
            if ratio == 1
            else f"{len(matched)}/{len(expected_value)} expected values found at row {row_id}."
        ),
        "detected_errors": [
            {
                "error_type": "wrong_table_position",
                "key": m["key"],
                "expected": m["value"],
                "row_id": row_id,
                "col_id": m["col_id"],
                "message": f"Không tìm thấy {m['key']}={m['value']} đúng vị trí (row={row_id}, col={m['col_id']}).",
            }
            for m in missing
        ],
    }


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
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif"}.get(ext, "image/jpeg")
    with open(image_path, "rb") as f:
        b64_image = base64.b64encode(f.read()).decode("utf-8")

    max_score = criterion.get("score", 0)
    criterion_content = criterion.get("content", "")
    rubric_items = criterion.get("rubric", [])
    rubric_text = "\n".join(f"- {r}" for r in rubric_items) if rubric_items else ""
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

    sections = [
        f"=== TIÊU CHÍ ===\n{criterion_content}",
    ]
    if expected_val_text:
        sections.append(f"=== ĐÁP ÁN / CÔNG THỨC KỲ VỌNG ===\n{expected_val_text}")
    if rubric_text:
        sections.append(f"=== RUBRIC ===\n{rubric_text}")
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
    think_prompt = (
        f"Bạn là giáo viên chấm thi. {equivalence_note}\n\n"
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
                    "messages": [{
                        "role": "user",
                        "content": [image_content, {"type": "text", "text": think_prompt}],
                    }],
                    "temperature": 0,
                    "max_tokens": CFG.get("cot_max_tokens_think", 600),
                },
                timeout=180,
            )
            resp_think.raise_for_status()
            resp_think_json = resp_think.json()
            cot_reasoning = (
                resp_think_json.get("choices", [{}])[0].get("message", {}).get("content", "")
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
                resp_decide_json.get("choices", [{}])[0].get("message", {}).get("content", "")
            ).strip()
            decide_usage = resp_decide_json.get("usage", {})

            parsed = _extract_json_from_text(decide_text)
            if parsed is not None:
                token_usage = {
                    "prompt_tokens": think_usage.get("prompt_tokens", 0) + decide_usage.get("prompt_tokens", 0),
                    "completion_tokens": think_usage.get("completion_tokens", 0) + decide_usage.get("completion_tokens", 0),
                    "total_tokens": think_usage.get("total_tokens", 0) + decide_usage.get("total_tokens", 0),
                }
                parsed.setdefault("score", 0)
                parsed.setdefault("status", "wrong")
                parsed.setdefault("reasoning", "")
                parsed.setdefault("confidence", 0.5)
                parsed["score"] = max(0.0, min(float(parsed["score"]), float(max_score)))
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
    evidence = get_student_evidence_for_part(sample, part_label, criterion.get("slot_ids", []))
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
            "reason": "Không tìm thấy hình vẽ/biểu đồ/lưu đồ.",
            "teacher_review_required": True,
            "detected_errors": [
                {
                    "error_type": "missing_visual_answer",
                    "message": "Không tìm thấy hình vẽ/biểu đồ/lưu đồ.",
                }
            ],
        }

    # Dùng visual đầu tiên tìm được (mỗi slot_id chỉ có 1 ảnh)
    visual = visuals[0]
    image_path = visual.get("image_path", "")

    if not CFG.get("use_llm") or not image_path:
        return {
            "criterion_id": criterion_id,
            "part_label": part_label,
            "criterion_content": criterion_content,
            "score": 0,
            "max_score": max_score,
            "status": "needs_vision_llm_or_teacher_review",
            "is_correct": False,
            "reason": "LLM disabled hoặc không có đường dẫn ảnh.",
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
            "status": "needs_vision_llm_or_teacher_review",
            "is_correct": False,
            "reason": f"Vision LLM lỗi: {llm_result['error']}",
            "visual_answers": visuals,
            "teacher_review_required": True,
            "detected_errors": [{"error_type": "vision_llm_error", "message": llm_result["error"]}],
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


def infer_criterion_grading_mode(
    sample: Dict[str, Any], criterion: Dict[str, Any]
) -> str:
    """Quyết định mode chấm cho từng criterion."""
    qtype = sample.get("question_type", "unknown")
    part_label = criterion.get("part_label")
    evidence = get_student_evidence_for_part(sample, part_label)

    if evidence.get("visual_answers"):
        return "visual"

    if evidence.get("tables") or qtype == "table_completion":
        return "table"

    if (
        criterion.get("expected_output") is not None
        or criterion.get("expected_output_tokens")
        or criterion.get("expected_output_lines")
        or criterion.get("conditional_outputs")
    ):
        return "expected_output"

    if criterion.get("expected_value"):
        return "expected_value"

    if qtype in ("program_trace_output", "fill_in_the_blank", "mixed_multi_part"):
        if (
            criterion.get("expected_output") is not None
            or criterion.get("expected_output_tokens")
            or criterion.get("expected_output_lines")
            or criterion.get("conditional_outputs")
        ):
            return "expected_output"
        if criterion.get("expected_value"):
            return "expected_value"

    if qtype == "short_answer_or_essay":
        return "llm_rubric"

    return "llm_or_teacher_review"


# FIX #5: grade_criterion định nghĩa SAU tất cả v2 functions
def grade_criterion(
    sample: Dict[str, Any], criterion: Dict[str, Any]
) -> Dict[str, Any]:
    """Orchestrator: chọn hàm grading phù hợp."""
    mode = infer_criterion_grading_mode(sample, criterion)

    if mode == "expected_output":
        return grade_expected_output_criterion_v2(sample, criterion)
    if mode == "expected_value":
        return grade_expected_value_criterion(sample, criterion)
    if mode == "table":
        return grade_table_criterion(sample, criterion)
    if mode == "visual":
        return grade_visual_criterion(sample, criterion)

    # Needs LLM or teacher review
    return {
        "criterion_id": criterion.get("criterion_id"),
        "part_label": criterion.get("part_label"),
        "criterion_content": criterion.get("content", ""),
        "score": 0,
        "max_score": criterion.get("score", 0),
        "status": "needs_llm_or_teacher_review",
        "is_correct": False,
        "reason": f"No heuristic grader for this criterion (mode={mode}).",
        "teacher_review_required": True,
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
    rubric_text: str = "",
    retries: int = 3,
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
    if not CFG["use_llm"]:
        return {
            "cot_used": False,
            "error": "LLM is disabled.",
            "message": "LLM is disabled. Using heuristic grader instead.",
        }

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
            rubric_text=rubric_text,
            student_text=student_text,
            max_score=max_score,
            question_context=question_context,
            retries=retries,
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
            "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

    # Aggregate token_usage across all votes
    agg_usage: Dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
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
    rubric_text: str,
    student_text: str,
    max_score: float,
    question_context: str,
    retries: int,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Một lần đầy đủ THINK+DECIDE (có retry nội bộ khi lỗi mạng/parse JSON).
    Trả (result, None) nếu thành công, (None, error_message) nếu thất bại hết retries.
    """
    # ── Bước 1: THINK ──────────────────────────────────────────────────────
    think_prompt = f"""Bạn là một giáo viên chấm thi lập trình đang phân tích bài làm.
Hãy SUY LUẬN CHI TIẾT từng bước trước khi đưa ra điểm số.

NGUYÊN TẮC CHẤM: Chấp nhận mọi cách làm tương đương — code/công thức/thuật toán khác nhau về hình thức nhưng đúng về kết quả và logic đều được điểm đầy đủ. Không yêu cầu giống hệt đáp án mẫu.

=== TIÊU CHÍ CHẤM ===
{criterion_content}

=== ĐÁP ÁN KỲ VỌNG ===
{expected_output if expected_output is not None else "(không có đáp án cố định — dùng rubric)"}

=== RUBRIC ===
{rubric_text if rubric_text else "(không có rubric bổ sung)"}

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
                        "content": "Bạn là giáo viên chấm thi. Hãy suy luận chi tiết bằng tiếng Việt.",
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
                resp_think_json
                .get("choices", [{}])[0]
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
                resp_decide_json
                .get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            ).strip()
            decide_usage = resp_decide_json.get("usage", {})

            parsed = _extract_json_from_text(decide_text)
            if parsed is not None:
                token_usage = {
                    "prompt_tokens": think_usage.get("prompt_tokens", 0) + decide_usage.get("prompt_tokens", 0),
                    "completion_tokens": think_usage.get("completion_tokens", 0) + decide_usage.get("completion_tokens", 0),
                    "total_tokens": think_usage.get("total_tokens", 0) + decide_usage.get("total_tokens", 0),
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
    rubric_text: str = "",
    retries: int = 3,
) -> Dict[str, Any]:
    """
    Gọi LLM 1 bước duy nhất (KHÔNG có THINK/DECIDE riêng) — dùng khi
    CFG["use_chain_of_thought"] = False. Rẻ và nhanh hơn call_llm_cot()
    (1 lần gọi/vote thay vì 2), đánh đổi bằng việc LLM không suy luận tường
    minh trước khi chấm — dễ sai hơn với criterion cần lập luận nhiều bước
    (code, essay). Vẫn áp dụng self-consistency vote giống call_llm_cot().
    """
    if not CFG["use_llm"]:
        return {"cot_used": False, "error": "LLM is disabled."}

    model_name = CFG.get("model_name")
    model_api = CFG.get("model_api")
    api_key = CFG.get("api_key")
    if not model_name or not model_api:
        return {"cot_used": False, "error": "LLM not configured."}

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    prompt = f"""Bạn là một giáo viên chấm thi lập trình. Hãy chấm bài làm sau và trả về JSON.

=== TIÊU CHÍ CHẤM ===
{criterion_content}

=== ĐÁP ÁN KỲ VỌNG ===
{expected_output if expected_output is not None else "(không có đáp án cố định — dùng rubric)"}

=== RUBRIC ===
{rubric_text if rubric_text else "(không có rubric bổ sung)"}

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


# ============================================================================
# SYSTEM 4: LLM + Heuristic Advisory
# Heuristic chạy trước → kết quả làm "góp ý" trong prompt LLM
# LLM ra quyết định cuối cùng, có thể đồng ý hoặc override heuristic
# ============================================================================


def grade_with_llm_advised(
    sample: Dict[str, Any], criterion: Dict[str, Any], heuristic_result: Dict[str, Any]
) -> Dict[str, Any]:
    """
    SYSTEM 4 (CoT + Heuristic Advisory):
    Gọi LLM với Chain-of-Thought reasoning + heuristic advisory context.
    LLM suy luận chi tiết, có tham khảo gợi ý từ heuristic, rồi ra quyết định.
    """
    criterion_id = criterion.get("criterion_id", "unknown")
    part_label = criterion.get("part_label", "main")
    max_score = criterion.get("score", 0)

    evidence = get_student_evidence_for_part(sample, part_label)
    student_text = evidence.get("text", "")

    # FIX: evidence.text rỗng khi câu trả lời là bảng/hình vẽ (table/visual) —
    # get_student_evidence_for_part() chỉ ghép text từ lines/tokens, không từ
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
            "llm_reasoning": "Student left this part blank.",
            "cot_reasoning": "",
            "confidence": 1.0,
            "heuristic_score": heuristic_result.get("score", 0),
            "heuristic_status": heuristic_result.get("status", "wrong"),
            "student_answer_text": "",
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
    h_mode = heuristic_result.get("grading_method", "heuristic")

    # Token evaluation detail nếu có
    token_detail = ""
    if heuristic_result.get("token_evaluations"):
        evals = heuristic_result["token_evaluations"]
        token_detail = "\nChi tiet tung token:\n" + "\n".join(
            f"  [{i}] expected='{e['expected']}' student='{e['student']}' > {'[OK]' if e['is_correct'] else '[FAIL]'}"
            for i, e in enumerate(evals)
        )

    rubric = criterion.get("rubric", {})
    rubric_text = "\n".join(f"- {k}: {v}" for k, v in rubric.items()) if rubric else ""

    # FIX: câu có conditional_outputs (VD T3, T8B, T9) có expected_output=null ở
    # barem gốc — giá trị thật chỉ được resolve trong heuristic_result theo
    # student_index. Phải dùng giá trị đã resolve đó khi đưa cho LLM, nếu không
    # LLM sẽ không biết đáp án đúng là gì và phải đoán mò.
    expected_output = criterion.get("expected_output")
    if expected_output is None and heuristic_result.get("conditional_resolved"):
        expected_output = heuristic_result.get("expected_output")
    grader_note = criterion.get("grader_note", "")
    partial_credit_rule = criterion.get("partial_credit_rule")
    criterion_content = criterion.get("content", "N/A")

    # FIX: grader_note/partial_credit_rule đã được đọc nhưng trước đây không hề
    # đưa vào prompt — đây là nơi giáo viên ghi rõ các trường hợp biên (VD "n<2
    # thì không phải SNT") mà LLM hay hallucinate ra yêu cầu sai vì thiếu thông
    # tin này (đã quan sát ở câu T13A1, T8B, T13C2).
    teacher_rule_text = ""
    if grader_note:
        teacher_rule_text += f"\n══ GHI CHÚ CỦA GIÁO VIÊN (BẮT BUỘC TUÂN THỦ) ══\n{grader_note}"
    if partial_credit_rule:
        teacher_rule_text += f"\n══ QUY TẮC ĐIỂM BÁN PHẦN ══\n{json.dumps(partial_credit_rule, ensure_ascii=False)}"

    # Xây dựng question_context với advisory từ heuristic (cho CoT reasoning)
    question_context = f"""══ GỢI Ý TỪ HEURISTIC GRADER ══
Score gợi ý : {h_score}/{max_score}
Status gợi ý: {h_status}
Lý do       : {h_reason}{token_detail}
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
        llm_call = call_llm_cot if CFG.get("use_chain_of_thought", True) else call_llm_simple
        cot_result = llm_call(
            question_context=question_context,
            criterion_content=criterion_content,
            expected_output=expected_output,
            student_text=student_text,
            max_score=max_score,
            rubric_text=rubric_text,
            retries=3,
        )

        # Kiểm tra lỗi từ LLM (cot_used=False ở nhánh simple là bình thường,
        # không phải lỗi — chỉ "error" key mới biểu thị thất bại thật)
        if "error" in cot_result:
            # CoT fail → fallback heuristic
            fallback = dict(heuristic_result)
            fallback["grading_method"] = "heuristic_llm_failed"
            fallback["llm_used"] = False
            fallback["llm_error"] = cot_result.get("error", "CoT LLM failed")
            fallback["cot_reasoning"] = ""
            return fallback

        score = min(float(cot_result.get("score", h_score)), max_score)
        status = cot_result.get("status", "wrong")
        reasoning = cot_result.get("reasoning", "")
        cot_reason = cot_result.get("cot_reasoning", "")
        confidence = float(cot_result.get("confidence", 0.8))
        feedback = cot_result.get("feedback", "")
        suggestion = cot_result.get("suggestion", "")
        token_usage = cot_result.get("token_usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})

        # Kiểm tra xem LLM có đồng ý với heuristic không
        agreed_with_heuristic = abs(score - h_score) < 0.01 and status == h_status

        return {
            "criterion_id": criterion_id,
            "part_label": part_label,
            "criterion_content": criterion.get("content", ""),
            "score": round(score, 4),
            "max_score": max_score,
            "status": status,
            "is_correct": score == max_score,
            "llm_used": True,
            "grading_method": "llm_advised_cot" if cot_result.get("cot_used") else "llm_advised_simple",
            "llm_reasoning": reasoning,
            "cot_reasoning": cot_reason,
            "feedback": feedback,
            "suggestion": suggestion,
            "agreed_with_heuristic": agreed_with_heuristic,
            "confidence": confidence,
            "heuristic_score": h_score,
            "heuristic_status": h_status,
            "heuristic_reason": h_reason,
            "student_answer_text": student_text,
            "token_usage": token_usage,
            "evidence": evidence,
            "detected_errors": [],
        }

    except Exception as e:
        # Exception → fallback heuristic
        fallback = dict(heuristic_result)
        fallback["grading_method"] = "heuristic_exception"
        fallback["llm_used"] = False
        fallback["llm_error"] = str(e)[:100]
        fallback["cot_reasoning"] = ""
        return fallback


def grade_criterion_advised(
    sample: Dict[str, Any], criterion: Dict[str, Any]
) -> Dict[str, Any]:
    """
    System 4: Luôn chạy heuristic trước → dùng kết quả làm advisory cho LLM.
    LLM luôn là người ra quyết định cuối.

    Ngoại lệ: visual criterion — grade_criterion() đã gọi Vision LLM bên trong
    grade_visual_criterion(). Không qua grade_with_llm_advised() vì không có
    text evidence → blank_skip sẽ xóa kết quả Vision LLM.
    """
    # Bước 1: Heuristic (với visual: đã gọi Vision LLM bên trong)
    heuristic_result = grade_criterion(sample, criterion)

    # Visual criterion: kết quả đã hoàn chỉnh từ Vision LLM, không cần LLM text
    if infer_criterion_grading_mode(sample, criterion) == "visual":
        heuristic_result.setdefault("grading_method", "vision_llm")
        heuristic_result.setdefault("token_usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
        return heuristic_result

    # Bước 2: LLM với heuristic advisory
    if CFG.get("use_llm"):
        return grade_with_llm_advised(sample, criterion, heuristic_result)

    # LLM disabled → dùng heuristic
    heuristic_result["grading_method"] = "heuristic_only"
    return heuristic_result


def aggregate_with_group_rules(
    criterion_results: List[Dict[str, Any]]
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
        all_correct = all(m.get("is_correct") for m in members)
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


def grade_sample_advised(
    sample: Dict[str, Any], barem_dict: Dict[int, List[Dict]] = None
) -> Dict[str, Any]:
    """
    System 4 (LLM + Heuristic Advisory): chấm toàn bộ.
    Mỗi criterion: heuristic → LLM quyết định với heuristic làm gợi ý.
    """
    barem_dict = barem_dict or {}

    validation_before = validate_sample_schema(
        sample, after_routing=False, barem_dict=barem_dict
    )
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

    criterion_results = []
    detected_errors = []
    agreed_count = 0
    overridden_count = 0
    sample_t0 = time.time()

    for criterion in criteria_list:
        crit_t0 = time.time()
        result = grade_criterion_advised(routed_sample, criterion)
        result["latency_ms"] = round((time.time() - crit_t0) * 1000)
        # Mang theo group metadata (all_or_nothing) từ criterion sang result
        # để aggregate_with_group_rules() áp dụng đúng lúc tính tổng điểm.
        if criterion.get("group_all_or_nothing"):
            result["group_id"] = criterion.get("group_id")
            result["group_all_or_nothing"] = True
            result["group_max_score"] = criterion.get("group_max_score", 0)
        criterion_results.append(result)

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
    total_tokens: Dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
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
        "validation_before_routing": validation_before,
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


def detect_results_format(data: Any) -> bool:
    """Kiểm tra xem input có phải format Results_Ma_de_1 (dict HS_N -> questions) không."""
    if not isinstance(data, dict):
        return False
    return any(k.startswith("HS_") for k in data)


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

    for hs_key, questions in data.items():
        if not hs_key.startswith("HS_") or not isinstance(questions, dict):
            continue
        try:
            student_index = int(hs_key.split("_")[-1])
        except ValueError:
            student_index = 0

        # Gom các Cau entries theo question_number
        q_data: Dict[int, Dict[str, Any]] = {}

        for cau_key, cau_val in questions.items():
            if not isinstance(cau_val, dict):
                continue
            status = cau_val.get("status", "")
            table_extracted: List[Dict] = []
            if status in ("failed_at_cropping", "skipped"):
                lines: List[str] = []
            else:
                content = cau_val.get("content") or {}
                lines = [l for l in (content.get("lines") or []) if isinstance(l, str)]
                # Format bảng chuẩn: table_extracted thay vì lines
                raw_table = content.get("table_extracted")
                if isinstance(raw_table, list):
                    table_extracted = [r for r in raw_table if isinstance(r, dict)]

            # Parse: Cau_XX | Cau_XX_N | Cau_XXa
            m = re.match(r"Cau_(\d+)(?:_(\d+))?([a-z]?)$", cau_key, re.IGNORECASE)
            if not m:
                continue
            q_num = int(m.group(1))
            slot_n = int(m.group(2)) if m.group(2) else None
            sub = m.group(3).lower() if m.group(3) else None

            if q_num not in q_data:
                q_data[q_num] = {}

            image_path = cau_val.get("image_path", "")
            cau_type = cau_val.get("type", "")
            is_visual = cau_type == "diagram" and bool(image_path)

            if sub:
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

            # Map part_label → text
            part_text: Dict[str, str] = {}

            if "main" in q_entries:
                # Cau_XX đơn: line[i] → part_labels[i]
                all_lines = q_entries["main"]
                for i, pl in enumerate(part_labels):
                    part_text[pl] = all_lines[i] if i < len(all_lines) else ""

            elif any(k.startswith("slot_") for k in q_entries):
                # Cau_XX_1, Cau_XX_2: nối tất cả slot lines lại rồi map tuần tự
                slot_keys = sorted(k for k in q_entries if k.startswith("slot_"))
                flat_lines: List[str] = []
                for sk in slot_keys:
                    flat_lines.extend(q_entries[sk])
                for i, pl in enumerate(part_labels):
                    part_text[pl] = flat_lines[i] if i < len(flat_lines) else ""

            elif any(k.startswith("sub_") for k in q_entries):
                # Cau_13a/b/c: sub letter = part_label, join tất cả lines
                for k, lns in q_entries.items():
                    if k.startswith("sub_") and not k.endswith("_table"):
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
                        text = str(row.get(col_key, "")).strip()
                        cells.append({
                            "cell_id": f"R{i+1}C{j+1}",
                            "row_id": f"R{i+1}",
                            "col_id": f"C{j+1}",
                            "text": text,
                            "part_label": pl,
                            "slot_id": f"cau_{q_num}_001_{pl}",
                            "is_blank": not bool(text),
                        })
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
                ans_visuals.append({
                    "image_path": img_path,
                    "part_label": pl,
                    "slot_id": f"cau_{q_num}_001_{pl}",
                    "type": "diagram",
                    "is_blank": not bool(img_path),
                })

            # Build student_answer
            ans_lines: List[Dict] = []
            ans_tokens: List[Dict] = []
            full_parts: List[str] = []
            line_idx = 1
            token_idx = 1

            effective_pls = part_labels if part_labels else list(part_text.keys())

            for pl in effective_pls:
                text = part_text.get(pl, "")
                slot_id = f"cau_{q_num}_001_{pl}"
                if not text:
                    ans_lines.append({
                        "line_id": f"L{line_idx}",
                        "part_label": pl,
                        "slot_id": slot_id,
                        "text": "",
                        "bbox": [0, 0, 0, 0],
                        "confidence": 0.0,
                        "is_blank": True,
                    })
                    line_idx += 1
                    continue

                # Tách multi-line text (code) thành từng dòng riêng
                text_lines = text.split("\n")
                for tl in text_lines:
                    stripped = tl.strip()
                    if not stripped:
                        continue
                    full_parts.append(stripped)
                    ans_lines.append({
                        "line_id": f"L{line_idx}",
                        "part_label": pl,
                        "slot_id": slot_id,
                        "text": stripped,
                        "bbox": [0, 0, 0, 0],
                        "confidence": 1.0,
                    })
                    for tok in tokenize_answer(stripped):
                        ans_tokens.append({
                            "token_id": f"W{token_idx}",
                            "line_id": f"L{line_idx}",
                            "part_label": pl,
                            "slot_id": slot_id,
                            "order": token_idx,
                            "text": tok,
                            "bbox": [0, 0, 0, 0],
                            "confidence": 1.0,
                        })
                        token_idx += 1
                    line_idx += 1

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

            samples.append({
                "sample_id": f"cau_{q_num}_001__{hs_key}",
                "student_index": student_index,
                "ma_de": "1",
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
            })

    return samples


# ============================================================================
# BATCH RUNNER
# ============================================================================


def run_batch(
    test_input_path: str, barem_path: str, output_path: str = None
) -> List[Dict[str, Any]]:
    """
    Chạy grading toàn bộ test samples bằng System 4 (LLM + Heuristic Advisory).
    """
    barem_dict = load_barem(barem_path)

    with open(test_input_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    if detect_results_format(raw_data):
        print("[INFO] Detected Results format — converting to pipeline format...")
        samples = convert_results_to_samples(raw_data, barem_dict)
        print(f"[INFO] Converted {len(samples)} samples from Results format")
        # Save converted samples for inspection
        converted_path = Path(test_input_path).with_suffix(".converted.json")
        with open(converted_path, "w", encoding="utf-8") as f:
            json.dump(samples, f, ensure_ascii=False, indent=2)
        print(f"[INFO] Converted input saved to: {converted_path}")
    else:
        samples = raw_data

    print(f"\n{'='*80}")
    print(f"System 4 (LLM+Advisory) — {len(samples)} samples")
    print(f"{'='*80}")

    results = []
    for i, sample in enumerate(samples):
        sid = sample.get("sample_id", f"sample_{i}")
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
        sc, mx = res.get("score", 0), res.get("max_score", 0)
        pct = sc / mx * 100 if mx else 0
        print(
            f"  [{i+1:2d}/{len(samples)}] {sid:14s} {sc:.2f}/{mx:.2f} ({pct:.0f}%) — {res.get('status')}"
        )

    # Summary
    total_sc = sum(r.get("score", 0) for r in results)
    total_mx = sum(r.get("max_score", 0) for r in results)
    print(f"\n  TOTAL: {total_sc:.2f}/{total_mx:.2f} ({total_sc/total_mx*100:.1f}%)")

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"  Saved to: {output_path}")

    return results


# ============================================================================
# QUICK SMOKE TEST
# ============================================================================


def smoke_test():
    """Kiểm tra nhanh các fix quan trọng không cần file thật."""
    print("=" * 60)
    print("SMOKE TEST — Kiểm tra 11 fixes")
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

    # FIX #2: get_student_evidence_for_part đọc từ lines
    sample_with_lines = {
        "student_answer": {
            "full_text": "3529",
            "lines": [
                {
                    "line_id": "L1",
                    "part_label": "main",
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
    ev = get_student_evidence_for_part(sample_with_lines, "main")
    assert ev["text"] == "3529", f"FIX #2 FAIL: got '{ev['text']}'"
    print("✅ FIX #2: get_student_evidence_for_part đọc từ lines")

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

    # FIX #4: resolve_conditional_output với restricted eval
    sample_idx7 = {**sample_no_barem, "student_index": 7}
    criterion_cond = {
        "criterion_id": "T3",
        "conditional_outputs": [
            {
                "condition": "student_index % 4 == 3",
                "expected_output": "57918",
                "expected_output_tokens": ["5", "7", "9", "18"],
            },
            {"condition": "student_index % 4 == 0", "expected_output": "24615"},
        ],
    }
    resolved = resolve_conditional_output(sample_idx7, criterion_cond)
    assert resolved["matched"] is True, "FIX #4 FAIL: should match"
    assert (
        resolved["expected_output"] == "57918"
    ), f"FIX #4 FAIL: {resolved['expected_output']}"
    print(
        "✅ FIX #4: resolve_conditional_output với condition expression (student_index=7)"
    )

    # FIX #7: partial_credit_rule không downgrade full score
    sample_full = {
        **sample_with_lines,
        "question_number": 5,
        "student_index": 7,
        "question_type": "fill_in_the_blank",
        "student_answer": {
            "full_text": "10 5 5",
            "lines": [
                {
                    "line_id": "L1",
                    "part_label": "main",
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
                    "order": 1,
                    "text": "10",
                    "bbox": [0, 0, 0, 0],
                    "confidence": 0.99,
                },
                {
                    "token_id": "W2",
                    "line_id": "L1",
                    "part_label": "main",
                    "order": 2,
                    "text": "5",
                    "bbox": [0, 0, 0, 0],
                    "confidence": 0.99,
                },
                {
                    "token_id": "W3",
                    "line_id": "L1",
                    "part_label": "main",
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
        "score": 0.5,
        "expected_output": "10 5 5",
        "expected_output_tokens": ["10", "5", "5"],
        "partial_credit_rule": {
            "type": "count_correct_tokens",
            "partial_score": 0.25,
            "condition": "correct_token_count == 2",
        },
    }
    r = grade_expected_output_criterion_v2(sample_full, criterion_q5)
    assert (
        r["score"] == 0.5
    ), f"FIX #7 FAIL: full answer should get 0.5, got {r['score']}"
    assert r["status"] == "correct"
    print("✅ FIX #7: partial_credit_rule không downgrade khi đúng 3/3 tokens")

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
  python pipeline.py --input test_input.json --barem sample_parem.json
        """,
    )
    parser.add_argument("--input", "-i", default="input/test_input_perfect.json")
    parser.add_argument("--barem", "-b", default="sample_parem.json")
    parser.add_argument("--output-dir", "-o", default="output")
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
    print(f"  System 4 (LLM_Advisory)")
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
