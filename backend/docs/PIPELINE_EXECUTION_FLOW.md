# Pipeline Execution Flow - Multi-format Rubric-based Grading System

## 📋 Tổng quan
Hệ thống chấm bài chạy theo luồng từ dưới lên (bottom-up), bắt đầu từ batch runner entry point, sau đó gọi grade_sample cho từng sample, rồi phân tách thành các criterion grader chuyên biệt.

---

## 🚀 Entry Point & Main Flow

### Cell 37: Batch Runner (Main Entry)
```python
# File: pipeline (2).ipynb, Cell 37
# Input: pipeline_input_cau_1_5_ma_de_1.json
# Output: grading_results_batch.json

for sample in samples:
    res = grade_sample(sample)  # ← Gọi Cell 17
    results.append(res)

json.dump(results, output_file)
```

**Chức năng:** Đọc danh sách samples từ JSON, chấm từng cái, lưu kết quả ra file.

---

## 📊 Level 1: Sample-Level Grading

### Cell 17: grade_sample() - Main Orchestrator
```python
# File: pipeline (2).ipynb, Cell 17

def grade_sample(sample):
    # Step 1: Validate trước routing
    validation_before = validate_sample_schema(sample, after_routing=False)

    # Step 2: Route question type
    routed_sample = apply_question_routing(sample)  # ← Gọi Cell 9

    # Step 3: Validate sau routing
    validation_after = validate_sample_schema(routed_sample, after_routing=True)

    # Step 4: Chấm từng criterion
    criterion_results = []
    for criterion in routed_sample.get("teacher_barem", []):
        result = grade_criterion(routed_sample, criterion)  # ← Gọi Cell 16
        criterion_results.append(result)

    # Step 5: Tổng hợp điểm
    total_score = sum(r.get("score", 0) for r in criterion_results)

    # Step 6: Sinh feedback
    if total_score == max_score:
        status = "correct"
    elif total_score > 0:
        status = "partially_correct"
    else:
        status = "wrong_or_ungraded"

    return {
        "sample_id": ...,
        "question_type": routed_sample.get("question_type"),
        "score": total_score,
        "max_score": ...,
        "status": status,
        "criterion_results": criterion_results,
        "feedback": feedback,
        "teacher_review_required": ...
    }
```

**Flow chi tiết:**
1. Kiểm tra schema trước routing
2. Gọi `apply_question_routing()` để xác định dạng câu hỏi
3. Kiểm tra schema sau routing
4. Lặp qua từng criterion → gọi `grade_criterion()` cho mỗi cái
5. Tính tổng điểm + xác định status
6. Trả về kết quả sample level

---

## 🔄 Level 2: Routing (Câu hỏi là dạng gì?)

### Cell 9: route_question() - Question Type Detection
```python
# File: pipeline (2).ipynb, Cell 9

def route_question(sample):
    """
    Xác định loại câu hỏi dựa trên:
    - Nội dung question
    - Thông tin barem
    - Thông tin student_answer

    Return: {"question_type": "...", "confidence": 0.x, "reason": "..."}
    """

    question_text = sample["question"]["text"]
    student_answer = sample["student_answer"]
    teacher_barem = sample["teacher_barem"]

    # Phán đoán theo thứ tự ưu tiên:

    # 1. Visual (hình vẽ, flowchart, chart)
    if has_visual_answers:
        if visual_type in ["flowchart", "diagram"]:
            return {"question_type": "visual_flowchart", "confidence": 0.9}
        if visual_type in ["chart", "bar_chart", "pie_chart"]:
            return {"question_type": "chart_drawing", "confidence": 0.9}
        return {"question_type": "visual_answer", "confidence": 0.75}

    # 2. Table (bảng)
    if has_tables:
        return {"question_type": "table_completion", "confidence": 0.85}

    # 3. Program trace / output prediction (C++, Java trace)
    if has_expected_output or "kết quả in ra màn hình" in question_text or "#include" in question_text:
        return {"question_type": "program_trace_output", "confidence": 0.9}

    # 4. Fill in the blank (điền chỗ trống)
    if "____" in question_text or "điền" in question_text:
        return {"question_type": "fill_in_the_blank", "confidence": 0.8}

    # 5. Short answer / essay (tự luận)
    if "giải thích" in question_text or "so sánh" in question_text:
        return {"question_type": "short_answer_or_essay", "confidence": 0.8}

    # 6. Mixed multi-part (nhiều phần)
    if has_multiple_parts:
        return {"question_type": "mixed_multi_part", "confidence": 0.7}

    # 7. Expected value fallback
    if has_expected_value:
        return {"question_type": "rubric_expected_value", "confidence": 0.65}

    # Fallback
    return {"question_type": "unknown", "confidence": 0.3}
```

### Cell 9: apply_question_routing() - Gắn routing vào sample
```python
def apply_question_routing(sample):
    routed_sample = dict(sample)
    routing = route_question(routed_sample)
    routed_sample["question_type"] = routing["question_type"]
    routed_sample["routing"] = routing
    return routed_sample
```

**Kết quả:** Sample được gắn thêm `question_type` và `routing` info.

---

## ⚙️ Level 3: Criterion-Level Grading

### Cell 16: grade_criterion() - Criterion Dispatcher
```python
# File: pipeline (2).ipynb, Cell 16

def infer_criterion_grading_mode(sample, criterion):
    """
    Xác định mode chấm cho từng criterion.
    Phụ thuộc vào:
    - question_type của sample
    - Trường có sẵn trong criterion (expected_output, expected_value, ...)
    - Evidence trong student_answer
    """

    # Ưu tiên:
    if evidence.get("visual_answers"):
        return "visual"

    if evidence.get("tables") or qtype == "table_completion":
        return "table"

    if criterion.get("expected_output") or criterion.get("expected_output_tokens"):
        return "expected_output"

    if criterion.get("expected_value"):
        return "expected_value"

    if qtype in ["program_trace_output", "fill_in_the_blank"]:
        if criterion.get("expected_output"):
            return "expected_output"
        if criterion.get("expected_value"):
            return "expected_value"
        return "llm_or_teacher_review"

    if qtype == "short_answer_or_essay":
        return "llm_rubric"

    return "llm_or_teacher_review"


def grade_criterion(sample, criterion):
    mode = infer_criterion_grading_mode(sample, criterion)

    # Dispatch đến grader phù hợp:
    if mode == "expected_output":
        return grade_expected_output_criterion(sample, criterion)  # ← Cell 12

    if mode == "expected_value":
        return grade_expected_value_criterion(sample, criterion)   # ← Cell 13

    if mode == "table":
        return grade_table_criterion(sample, criterion)            # ← Cell 14

    if mode == "visual":
        return grade_visual_criterion(sample, criterion)           # ← Cell 15

    # Fallback: cần LLM hoặc teacher review
    return {
        "criterion_id": criterion["criterion_id"],
        "score": 0,
        "status": "needs_llm_or_teacher_review",
        "teacher_review_required": True
    }
```

**Luồng dispatch:** Xác định mode → chọn grader → gọi hàm tương ứng

---

## 🎯 Level 4: Specialized Graders

### Cell 12: grade_expected_output_criterion()
```python
# File: pipeline (2).ipynb, Cell 12

def grade_expected_output_criterion(sample, criterion):
    """
    Chấm khi có expected_output hoặc expected_output_tokens.

    Ví dụ: Program trace C++ kỳ vọng output "3529"
    Student trả lời "3525"
    → Comparator so khớp chuỗi + fuzzy match
    """

    expected_output = criterion.get("expected_output")
    expected_output_tokens = criterion.get("expected_output_tokens")
    student_text = get_student_evidence_for_part(sample, criterion["part_label"])

    # Case 1: So khớp token by token
    if expected_output_tokens:
        correct_count = 0
        for i, expected_token in enumerate(expected_output_tokens):
            student_token = student_tokens[i] if i < len(student_tokens) else None
            if normalize_text(student_token) == normalize_text(expected_token):
                correct_count += 1

        ratio = correct_count / len(expected_output_tokens)
        score = max_score * ratio

    # Case 2: So khớp chuỗi toàn bộ
    else:
        if student_norm == expected_norm:
            score = max_score
        elif similarity(student_norm, expected_norm) >= 0.85:
            score = max_score  # Fuzzy match
        elif similarity(...) >= 0.65:
            score = max_score * 0.5
        else:
            score = 0

    return {
        "criterion_id": criterion["criterion_id"],
        "score": score,
        "status": "correct" if score == max_score else "partially_correct" if score > 0 else "wrong",
        "expected_output": expected_output,
        "student_answer": student_text,
        "token_evaluations": [...]  # detail
    }
```

**Chức năng:** So khớp output thực tế với kỳ vọng.

### Cell 13: grade_expected_value_criterion()
```python
# File: pipeline (2).ipynb, Cell 13

def grade_expected_value_criterion(sample, criterion):
    """
    Chấm khi criterion có expected_value dict.

    Ví dụ:
    expected_value = {
        "a_initial": 2,
        "b_initial": 4,
        "b_after_preincrement": 5
    }

    Kiểm tra xem các giá trị kỳ vọng có xuất hiện trong đáp án sinh viên không.
    """

    expected_value = criterion.get("expected_value", {})
    student_text = get_student_evidence_for_part(...)

    matched = []
    missing = []

    for key, value in expected_value.items():
        if normalize_text(str(value)) in normalize_text(student_text):
            matched.append(key)
        else:
            missing.append(key)

    ratio = len(matched) / len(expected_value)
    score = max_score * ratio

    return {
        "criterion_id": ...,
        "score": score,
        "status": "correct" if ratio == 1 else "partially_correct" if ratio > 0 else "wrong",
        "expected_value": expected_value,
        "matched": matched,
        "missing": missing
    }
```

**Chức năng:** Kiểm tra xem các key-value kỳ vọng có trong đáp án không.

### Cell 14: grade_table_criterion()
```python
# File: pipeline (2).ipynb, Cell 14

def grade_table_criterion(sample, criterion):
    """
    Chấm khi đáp án là bảng.

    - Trích xuất tất cả text từ các cell của bảng
    - Gom lại thành 1 chuỗi text
    - Gọi grade_expected_output hoặc grade_expected_value trên chuỗi đó
    """

    evidence = get_student_evidence_for_part(sample, part_label)
    tables = evidence.get("tables", [])

    if not tables:
        return {
            "score": 0,
            "status": "wrong",
            "reason": "No table found"
        }

    # Gom text từ bảng
    all_cell_texts = []
    for table in tables:
        for cell in table.get("cells", []):
            all_cell_texts.append(cell.get("text", ""))

    # Tạo fake sample để chấm như expected_output/expected_value
    fake_sample = {...}
    fake_sample["student_answer"]["full_text"] = " ".join(all_cell_texts)

    # Gọi grader phù hợp
    if criterion.get("expected_output"):
        return grade_expected_output_criterion(fake_sample, criterion)
    else:
        return grade_expected_value_criterion(fake_sample, criterion)
```

**Chức năng:** Xử lý đáp án dạng bảng.

### Cell 15: grade_visual_criterion()
```python
# File: pipeline (2).ipynb, Cell 15

def grade_visual_criterion(sample, criterion):
    """
    Chấm khi đáp án là hình vẽ/biểu đồ/flowchart.

    Hiện tại: Không chấm heuristic
    → Flag cần vision LLM hoặc teacher review
    """

    evidence = get_student_evidence_for_part(...)
    visuals = evidence.get("visual_answers", [])

    if not visuals:
        return {
            "score": 0,
            "status": "wrong",
            "teacher_review_required": True
        }

    return {
        "score": 0,
        "status": "needs_vision_llm_or_teacher_review",
        "visual_answers": visuals,
        "teacher_review_required": True,
        "reason": "Visual answer requires Vision LLM or teacher review"
    }
```

**Chức năng:** Visual questions cần LLM riêng → skip heuristic.

---

## 📈 Call Graph (Gọi hàm)

```
┌─────────────────────────────────────────┐
│ Cell 37: Batch Runner (Main Entry)      │
│ for sample in samples:                  │
│     res = grade_sample(sample)          │
└──────────────┬──────────────────────────┘
               │
               ↓
┌─────────────────────────────────────────┐
│ Cell 17: grade_sample()                 │
│ ├─ validate_sample_schema()             │
│ ├─ apply_question_routing()             │
│ │  └─ route_question() [Cell 9]         │
│ ├─ validate_sample_schema()             │
│ └─ for criterion in teacher_barem:      │
│    └─ grade_criterion() [Cell 16]       │
└──────────────┬──────────────────────────┘
               │
               ├─────────────────────────────────────────┐
               │                                         │
               ↓                                         ↓
    ┌──────────────────────┐          ┌──────────────────────────┐
    │ Cell 9:              │          │ Cell 16:                 │
    │ route_question()     │          │ grade_criterion()        │
    │                      │          │ ├─ infer_criterion...()  │
    │ Logic:               │          │ └─ Dispatch:             │
    │ 1. visual?           │          │    ├─ "expected_output"  │
    │ 2. table?            │          │    │  └─ Cell 12         │
    │ 3. program_trace?    │          │    ├─ "expected_value"   │
    │ 4. fill_blank?       │          │    │  └─ Cell 13         │
    │ 5. essay?            │          │    ├─ "table"            │
    │ 6. multi_part?       │          │    │  └─ Cell 14         │
    │ 7. unknown           │          │    └─ "visual"           │
    │                      │          │       └─ Cell 15         │
    └──────────────────────┘          └──────────────────────────┘
                                                     │
               ┌─────────────────────────────────────┼─────────────────────┐
               │                                     │                     │
               ↓                                     ↓                     ↓
    ┌──────────────────────┐     ┌──────────────────────┐  ┌─────────────────┐
    │ Cell 12:             │     │ Cell 13:             │  │ Cell 14: Table  │
    │ grade_expected_      │     │ grade_expected_      │  │ Cell 15: Visual │
    │ output_criterion()   │     │ value_criterion()    │  │                 │
    │                      │     │                      │  │ (Mostly passthrough)
    │ Logic:               │     │ Logic:               │  └─────────────────┘
    │ - So khớp token      │     │ - Kiểm tra key-      │
    │ - Fuzzy match        │     │   value trong text   │
    └──────────────────────┘     └──────────────────────┘
```

---

## 🔄 Data Flow: Input → Output

### Input: pipeline_input_cau_1_5_ma_de_1.json
```json
[
  {
    "sample_id": "cau_1_001",
    "question_type": "program_trace_output",
    "question": {
      "text": "Cho một chương trình..."
    },
    "teacher_barem": [
      {
        "criterion_id": "T1",
        "expected_value": {"a_initial": 2, ...},
        "score": 0.1
      }
    ],
    "student_answer": {
      "full_text": "3525",
      "lines": [...],
      "tokens": [...]
    },
    "max_score": 0.5
  }
]
```

### Processing Chain:
```
JSON Input
  ↓
grade_sample(sample)
  ├─ route_question() → "program_trace_output"
  └─ For each criterion:
     ├─ infer_criterion_grading_mode() → "expected_value"
     └─ grade_expected_value_criterion() → score = 0.0667
  ↓
Aggregate: score = 0.3167, status = "partially_correct"
```

### Output: grading_results_batch.json
```json
[
  {
    "sample_id": "cau_1_001",
    "question_type": "program_trace_output",
    "score": 0.3167,
    "max_score": 0.5,
    "status": "partially_correct",
    "criterion_results": [
      {
        "criterion_id": "T1",
        "score": 0.0667,
        "status": "partially_correct",
        "matched": [...],
        "missing": [...]
      }
    ],
    "feedback": "Bài làm đúng một phần theo barem..."
  }
]
```

---

## 📝 Summary: Call Order

**Thứ tự gọi hàm từ trên xuống:**

1. **Cell 37** - Batch Runner (Main entry point)
   - Đọc JSON
   - Lặp từng sample

2. **Cell 17** - grade_sample()
   - Validate before routing
   - **Cell 9** - route_question()
   - Validate after routing
   - Lặp từng criterion

3. **Cell 16** - grade_criterion()
   - Xác định mode
   - Dispatch:
     - **Cell 12** - grade_expected_output_criterion()
     - **Cell 13** - grade_expected_value_criterion()
     - **Cell 14** - grade_table_criterion()
     - **Cell 15** - grade_visual_criterion()

4. **Cell 17** (tiếp) - Aggregate & Feedback

5. **Cell 37** (tiếp) - Lưu JSON output

---

## 🎓 Key Functions Reference

| Function | Cell | Purpose |
|----------|------|---------|
| `route_question()` | 9 | Xác định question type |
| `apply_question_routing()` | 9 | Gắn routing vào sample |
| `grade_sample()` | 17 | Orchestrator sample-level |
| `infer_criterion_grading_mode()` | 16 | Chọn grading strategy |
| `grade_criterion()` | 16 | Dispatcher criterion-level |
| `grade_expected_output_criterion()` | 12 | Chấm output trace |
| `grade_expected_value_criterion()` | 13 | Chấm expected values |
| `grade_table_criterion()` | 14 | Chấm table answers |
| `grade_visual_criterion()` | 15 | Chấm visual answers |
| `get_student_evidence_for_part()` | 11 | Trích xuất đáp án từng part |
| `build_student_answer_index()` | 10 | Index student answer |
| `normalize_text()` | 4 | Chuẩn hóa text |
| `tokenize_answer()` | 4 | Tách token |
