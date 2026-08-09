"""
Bảng điểm grading với Groundtruth + MAE (System 4 — LLM + Heuristic Advisory)
Dùng: python report.py [grading_results.json] [sample_parem.json] [test_input.json] [system_name]
"""

import json
import sys
import math
from pathlib import Path
from pipeline import load_barem, resolve_conditional_output

# ── Màu terminal ──────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

def color_status(status: str) -> str:
    if status in ("correct",):
        return f"{GREEN}{status}{RESET}"
    if status in ("partially_correct",):
        return f"{YELLOW}{status}{RESET}"
    if status in ("wrong", "wrong_or_ungraded"):
        return f"{RED}{status}{RESET}"
    return f"{DIM}{status}{RESET}"

def color_pct(pct: float) -> str:
    if pct >= 90:   return f"{GREEN}{pct:.1f}%{RESET}"
    if pct >= 50:   return f"{YELLOW}{pct:.1f}%{RESET}"
    return f"{RED}{pct:.1f}%{RESET}"

def color_mae(mae: float) -> str:
    if mae == 0:     return f"{GREEN}{mae:.4f}{RESET}"
    if mae <= 0.1:   return f"{YELLOW}{mae:.4f}{RESET}"
    return f"{RED}{mae:.4f}{RESET}"


# ── Lấy groundtruth từ parem ──────────────────────────────────────────────────
def get_groundtruth(sample: dict, barem_dict: dict) -> dict:
    """
    Trả về groundtruth score (max_score) và expected answer cho câu đó.
    groundtruth_score = max_score (SV trả lời hoàn toàn đúng sẽ được điểm này).
    expected_answer = đáp án đúng, tính theo student_index nếu conditional.
    """
    q_num = sample.get("question_number")
    student_index = sample.get("student_index")
    criteria = barem_dict.get(q_num, [])

    gt_score = sample.get("max_score", 0)   # groundtruth luôn là max_score
    expected_answers = []

    for criterion in criteria:
        # Resolve conditional output nếu có
        if criterion.get("conditional_outputs"):
            resolved = resolve_conditional_output(sample, criterion)
            if resolved.get("matched") and resolved.get("expected_output"):
                expected_answers.append(str(resolved["expected_output"]))
                continue

        # Fixed expected_output
        if criterion.get("expected_output") is not None:
            expected_answers.append(str(criterion["expected_output"]))
        elif criterion.get("expected_output_lines"):
            expected_answers.append(" | ".join(criterion["expected_output_lines"][:2]) + "...")
        elif criterion.get("expected_value"):
            ev = criterion["expected_value"]
            if isinstance(ev, dict) and "function" in ev:
                expected_answers.append(f"[code: {ev['function']}()]")
            elif isinstance(ev, dict):
                pairs = [f"{k}={v}" for k, v in list(ev.items())[:3]]
                expected_answers.append(", ".join(pairs))
        else:
            expected_answers.append("[see rubric]")

    gt_answer = " | ".join(expected_answers) if expected_answers else "—"
    return {"gt_score": gt_score, "gt_answer": gt_answer}


# ── Distance metrics ─────────────────────────────────────────────────────────
def compute_distance(predicted: float, groundtruth: float) -> dict:
    """
    Tính các độ đo distance giữa predicted score và groundtruth score.
    """
    ae  = abs(predicted - groundtruth)           # Absolute Error
    se  = (predicted - groundtruth) ** 2         # Squared Error
    ape = ae / groundtruth * 100 if groundtruth > 0 else 0.0  # Absolute Percentage Error
    return {"AE": ae, "SE": se, "APE": ape}


# ── In bảng ───────────────────────────────────────────────────────────────────
def print_report(
    grading_path: str,
    barem_path: str,
    test_input_path: str,
    system_name: str = "System"
):
    # Load data
    barem_dict = load_barem(barem_path)

    with open(grading_path, encoding="utf-8") as f:
        results = json.load(f)

    with open(test_input_path, encoding="utf-8") as f:
        samples = json.load(f)

    # Index samples theo question_number
    sample_by_qnum = {s.get("question_number"): s for s in samples}

    # ── Header ────────────────────────────────────────────────────────────────
    title = f"  BẢNG ĐIỂM — {system_name.upper()} (All {len(results)} Questions)  "
    border = "=" * (len(title) + 4)
    print(f"\n{BOLD}{CYAN}{border}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{border}{RESET}\n")

    # ── Column widths ─────────────────────────────────────────────────────────
    W = {
        "cau":    4,   "id":     14,  "pred":   6,  "gt":     5,
        "pct":    8,   "ae":     8,   "status": 22,
        "student":18,  "answer": 22,
    }

    hdr = (
        f"{'Câu':>{W['cau']}}  "
        f"{'Sample ID':<{W['id']}}  "
        f"{'Score':>{W['pred']}}  "
        f"{'GT':>{W['gt']}}  "
        f"{'Pct':>{W['pct']}}  "
        f"{'AE':>{W['ae']}}  "
        f"{'Status':<{W['status']}}  "
        f"{'SV trả lời':<{W['student']}}  "
        f"{'Đáp án đúng':<{W['answer']}}"
    )
    sep = "-" * len(hdr)

    print(f"{BOLD}{hdr}{RESET}")
    print(sep)

    # ── Rows ──────────────────────────────────────────────────────────────────
    all_ae, all_se, all_ape = [], [], []

    for r in results:
        q_num     = r.get("question_number")
        sample_id = r.get("sample_id", "?")
        pred      = r.get("score", 0)
        max_score = r.get("max_score", 0)
        status    = r.get("status", "?")
        pct       = pred / max_score * 100 if max_score else 0

        # Groundtruth
        sample = sample_by_qnum.get(q_num, {})
        gt     = get_groundtruth(sample, barem_dict)
        gt_score  = gt["gt_score"]
        gt_answer = gt["gt_answer"]

        # Distance
        dist = compute_distance(pred, gt_score)
        all_ae.append(dist["AE"])
        all_se.append(dist["SE"])
        all_ape.append(dist["APE"])

        # Student answer (gộp từ criterion_results)
        student_texts = []
        for cr in r.get("criterion_results", []):
            t = cr.get("student_answer_text", "") or ""
            if t and t not in student_texts:
                student_texts.append(t[:30])
        student_ans = " | ".join(student_texts)[:W["student"]]

        # Truncate
        gt_disp  = gt_answer[:W["answer"]]
        sv_disp  = student_ans[:W["student"]]

        row = (
            f"{q_num:>{W['cau']}}  "
            f"{sample_id:<{W['id']}}  "
            f"{pred:>{W['pred']}.2f}  "
            f"{gt_score:>{W['gt']}.2f}  "
            f"{color_pct(pct):>{W['pct'] + 14}}  "  # +14 cho color codes
            f"{color_mae(dist['AE']):>{W['ae'] + 14}}  "
            f"{color_status(status):<{W['status'] + 14}}  "
            f"{sv_disp:<{W['student']}}  "
            f"{gt_disp:<{W['answer']}}"
        )
        print(row)

    print(sep)

    # ── Summary metrics ───────────────────────────────────────────────────────
    n = len(all_ae)
    mae   = sum(all_ae) / n
    mse   = sum(all_se) / n
    rmse  = math.sqrt(mse)
    mape  = sum(all_ape) / n

    total_pred = sum(r.get("score", 0) for r in results)
    total_gt   = sum(r.get("max_score", 0) for r in results)
    total_pct  = total_pred / total_gt * 100 if total_gt else 0

    correct   = sum(1 for r in results if r.get("status") == "correct")
    partial   = sum(1 for r in results if r.get("status") == "partially_correct")
    wrong     = sum(1 for r in results if r.get("status") in ("wrong", "wrong_or_ungraded"))
    ungraded  = sum(1 for r in results if r.get("status") == "ungraded")

    print(f"\n{BOLD}  TỔNG ĐIỂM:{RESET}")
    print(f"    Predicted : {total_pred:.2f} / {total_gt:.2f}  ({color_pct(total_pct)})")
    print(f"    Correct   : {GREEN}{correct}{RESET}  |  Partial: {YELLOW}{partial}{RESET}  |  Wrong: {RED}{wrong}{RESET}  |  Ungraded: {DIM}{ungraded}{RESET}")

    print(f"\n{BOLD}  DISTANCE METRICS (predicted vs groundtruth score):{RESET}")
    print(f"    MAE   (Mean Absolute Error)     : {color_mae(mae)}")
    print(f"    RMSE  (Root Mean Squared Error) : {color_mae(rmse)}")
    print(f"    MAPE  (Mean Abs Pct Error)      : {YELLOW}{mape:.2f}%{RESET}")
    print(f"\n    {DIM}MAE=0 nghĩa là grader cho điểm chính xác hoàn toàn so với max_score.{RESET}")
    print(f"    {DIM}Lưu ý: GT ở đây là max_score (điểm tối đa), không phải điểm human-labeled.{RESET}")
    print(f"    {DIM}Để tính MAE thật, cần file human_labels.json với điểm giáo viên chấm tay.{RESET}")

    print(f"\n{BOLD}{CYAN}{border}{RESET}\n")

    return {
        "total_predicted": total_pred,
        "total_groundtruth": total_gt,
        "total_pct": total_pct,
        "MAE": mae,
        "MSE": mse,
        "RMSE": rmse,
        "MAPE": mape,
        "correct": correct,
        "partial": partial,
        "wrong": wrong,
        "ungraded": ungraded,
    }


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Defaults — chỉ còn System 4 (LLM + Heuristic Advisory)
    grading_path = sys.argv[1] if len(sys.argv) > 1 else "grading_results.json"
    barem_path   = sys.argv[2] if len(sys.argv) > 2 else "sample_parem.json"
    test_input   = sys.argv[3] if len(sys.argv) > 3 else "test_input.json"
    system_name  = sys.argv[4] if len(sys.argv) > 4 else "System 4 (LLM + Heuristic Advisory)"

    print_report(grading_path, barem_path, test_input, system_name)
