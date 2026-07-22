"""
Chuyển Results_Ma_de_1.json (raw OCR output, dict HS_x -> Cau_xx -> content)
sang format list-of-samples mà pipeline.run_batch() / grade_sample_advised() yêu cầu
(giống cấu trúc test_input.json / test_input_perfect.json).

Usage:
    python scripts/convert_results_to_samples.py \
        --results Results_Ma_de_1.json \
        --parem sample_parem.json \
        --output real_input_ma_de_1.json
"""
import argparse
import json
import re
from pathlib import Path

# question_number -> list of (part_label, cau_key)
PART_TO_CAU = {
    1: [("main", "Cau_01")],
    2: [("main", "Cau_02")],
    3: [("main", "Cau_03")],
    4: [("main", "Cau_04")],
    5: [("main", "Cau_05")],
    6: [("main", "Cau_06")],
    7: [("main", "Cau_07")],
    8: [("a", "Cau_08_1"), ("b", "Cau_08_2")],
    9: [("main", "Cau_09")],
    10: [("main", "Cau_10")],
    11: [("main", "Cau_11")],
    12: [("main", "Cau_12")],
    13: [("a", "Cau_13a"), ("b", "Cau_13b"), ("c", "Cau_13c")],
    14: [("a", "Cau_14a"), ("b", "Cau_14b"), ("c", "Cau_14c")],
    15: [("a", "Cau_15a"), ("b", "Cau_15b"), ("c", "Cau_15c")],
}


def diagram_to_lines(content):
    lines = []
    for node in content.get("nodes", []):
        lines.append(f"[{node.get('shape', 'box')} {node.get('id')}] {node.get('text', '')}")
    for edge in content.get("edges", []):
        label = edge.get("label") or edge.get("text") or ""
        lines.append(f"{edge.get('from')} -> {edge.get('to')}: {label}".rstrip(": "))
    return lines


def build_part_lines(cau_entry, part_label, line_id_start, confidence_default=1.0):
    """Tra ve (lines, tokens, tables, is_blank) cho 1 part, tu 1 Cau_xx entry."""
    if cau_entry is None:
        return [], [], [], True

    status = cau_entry.get("status", "")
    ctype = cau_entry.get("type", "text")
    confidence = cau_entry.get("confidence", confidence_default)
    content = cau_entry.get("content", {}) or {}

    if status not in ("completed", "low_confidence_completed"):
        return [], [], [], True

    if ctype == "table":
        rows = content.get("table_extracted", [])
        if not rows:
            return [], [], [], True
        cells = []
        for r_idx, row in enumerate(rows, start=1):
            row_id = f"R{r_idx}"
            for c_idx, (_, val) in enumerate(sorted(row.items()), start=1):
                col_id = f"C{c_idx}"
                cells.append(
                    {
                        "cell_id": f"{row_id}{col_id}",
                        "col_id": col_id,
                        "text": str(val) if val is not None else "",
                        "tokens": [],
                    }
                )
        table = {"table_id": "TB1", "part_label": part_label, "cells": cells}
        return [], [], [table], False

    if ctype == "diagram":
        text_lines = diagram_to_lines(content)
    else:
        text_lines = content.get("lines", []) or []

    if not text_lines:
        return [], [], [], True

    lines, tokens = [], []
    line_id = line_id_start
    for raw_line in text_lines:
        lid = f"L{line_id}"
        lines.append(
            {
                "line_id": lid,
                "part_label": part_label,
                "text": raw_line,
                "bbox": [0, 0, 0, 0],
                "confidence": confidence,
            }
        )
        for order, tok in enumerate(raw_line.split(), start=1):
            tokens.append(
                {
                    "token_id": f"{lid}T{order}",
                    "line_id": lid,
                    "part_label": part_label,
                    "order": order,
                    "text": tok,
                    "bbox": [0, 0, 0, 0],
                    "confidence": confidence,
                }
            )
        line_id += 1
    return lines, tokens, [], False


def build_samples(results, templates_by_q):
    samples = []
    for hs_id, cau_map in results.items():
        m = re.search(r"(\d+)", hs_id)
        student_index = int(m.group(1)) if m else None

        for q_num, parts in PART_TO_CAU.items():
            template = templates_by_q.get(q_num)
            if template is None:
                continue

            all_lines, all_tokens, all_tables = [], [], []
            line_id = 1
            for part_label, cau_key in parts:
                cau_entry = cau_map.get(cau_key)
                lines, tokens, tables, _ = build_part_lines(cau_entry, part_label, line_id)
                line_id += len(lines)
                all_lines.extend(lines)
                all_tokens.extend(tokens)
                all_tables.extend(tables)

            full_text = "\n".join(l["text"] for l in all_lines)

            sample = {
                "sample_id": f"{template['sample_id']}__{hs_id}",
                "student_index": student_index,
                "ma_de": "1",
                "question_type": template.get("question_type"),
                "image_path": cau_map.get(parts[0][1], {}).get("image_path", ""),
                "question": template["question"],
                "question_number": q_num,
                "max_score": template.get("score", 0),
                "student_answer": {
                    "full_text": full_text,
                    "lines": all_lines,
                    "tokens": all_tokens,
                    "tables": all_tables,
                    "visual_answers": [],
                },
            }
            samples.append(sample)
    return samples


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default="Results_Ma_de_1.json")
    parser.add_argument("--parem", default="sample_parem.json")
    parser.add_argument("--output", default="real_input_ma_de_1.json")
    args = parser.parse_args()

    results = json.loads(Path(args.results).read_text(encoding="utf-8"))
    parem = json.loads(Path(args.parem).read_text(encoding="utf-8"))
    templates_by_q = {e["question_number"]: e for e in parem["teacher_barem"]}

    samples = build_samples(results, templates_by_q)

    Path(args.output).write_text(
        json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Built {len(samples)} samples -> {args.output}")


if __name__ == "__main__":
    main()
