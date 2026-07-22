# Đánh Giá Toàn Diện Pipeline Chấm Điểm

**Ngày đánh giá:** 31 Tháng 5, 2026
**Trạng thái:** ⚠️ **CHƯA SẴN SÀNG CHẠY HOÀN TOÀN** - Cần sửa các lỗi cấp độ cao trước

---

## 📋 Tóm Tắt Vấn Đề

Pipeline hiện tại có **3 hệ thống chấm điểm** (Heuristic, Hybrid, Pure LLM) nhưng khi chạy với `test_input.json` + `sample_parem.json` sẽ gặp **nhiều lỗi tiềm ẩn** dẫn đến **hiệu suất chấm điểm thấp** và **phát hiện lỗi sai**.

---

## 🔴 CÁC LỖI NGHIÊM TRỌNG (CRITICAL)

### 1. **DATA MISMATCH - Không phù hợp giữa dữ liệu test và rubric**

#### Vấn đề:

```
test_input.json:
  cau_1_001:
    student_answer: "3 4 2 9"      ← Token thứ 3 là "2"

sample_parem.json:
  cau_1_001:
    expected_output_tokens: ["3", "5", "2", "9"]   ← Token thứ 2 là "5"

❌ MISMATCH: "4" ≠ "5" (vị trí thứ 2)
```

#### Hậu quả:

- **Câu 1 sẽ chấm SALAADS**: Expected 3 hoặc 4 đúng, nhưng thực tế chỉ có 3 token đúng (3, 2, 9)
- **Partial credit rule không thể áp dụng đúng**: `correct_token_count in [2, 3]` → 0.25 điểm, nhưng logic có thể sai
- **Điểm cuối cùng sẽ thấp hơn thực tế**

#### Code liên quan:

```python
# File: pipeline (2).ipynb, Cell 10-11
expected_output_tokens = ["3", "5", "2", "9"]  # từ sample_parem
student_tokens = ["3", "4", "2", "9"]  # từ test_input

correct_count = 0
for i, exp_token in enumerate(expected_output_tokens):
    if normalize_text(student_tokens[i]) == normalize_text(exp_token):
        correct_count += 1

# correct_count = 3 (chỉ đúng token 0, 2, 3; sai token 1)
# Partial credit rule: correct_token_count in [2, 3] → score = 0.25 * max_score
```

#### ✅ Giải pháp:

1. **Kiểm tra lại dữ liệu đầu vào**: Xác minh đáp án đúng cho cau_1_001 là "3529" hay "3429"
2. **Cập nhật sample_parem.json hoặc test_input.json** để đồng nhất
3. **Thêm validation** khi load dữ liệu để phát hiện mismatch này

---

### 2. **QUESTION_TYPE LÀ NULL - Routing không hoạt động**

#### Vấn đề:

```python
test_input.json:
{
  "sample_id": "cau_1_001",
  "question_type": null,  # ← NULL!
  "question": {
    "text": "Cho một chương trình C++ và yêu cầu xác định kết quả in ra..."
  }
}
```

#### Hậu quả:

- **Route question → phải gọi hàm routing trước khi chấm**
- **Routing dựa trên heuristic** (keyword matching, visual signals):
  - Câu 1-2: Có "kết quả in ra" → `program_trace_output` (conf ≈ 0.85)
  - Câu 3: Có "giá trị nhập vào" + "kết quả in ra" → `program_trace_output` hoặc `fill_in_the_blank`
  - **Nếu routing conf < 0.75 → cần teacher review hoặc LLM fallback**
- **Nếu routing sai → chấm bị sai luôn**

#### Code liên quan:

```python
# File: Cell 9 (apply_question_routing)
def apply_question_routing(sample, barem_dict=None):
    """Tự động xác định question_type nếu là None"""
    if sample.get("question_type") is None:
        routing_result = route_question_with_heuristic(sample)  # ← Gọi routing
        sample["question_type"] = routing_result["question_type"]
        sample["routing"] = routing_result
    return sample

# Heuristic routing dựa trên: visual signals, keywords, code markers, tables, etc.
```

#### ✅ Giải pháp:

1. **Thêm question_type trong test_input.json** hoặc **tối ưu routing heuristic**
2. **Tăng confidence threshold** để giảm false positives
3. **Test routing function** trước chạy batch grading:
   ```python
   for sample in test_input:
       routing = route_question_with_heuristic(sample)
       print(f"{sample['sample_id']}: {routing['question_type']} (conf={routing['confidence']})")
       # Xác minh kết quả
   ```

---

### 3. **MISSING STUDENT_INDEX - Conditional outputs không resolve**

#### Vấn đề:

```python
test_input.json:
{
  "sample_id": "cau_3_001",  # student index = 1 (từ _001)
  "student_index": null  # ← MISSING!
}

sample_parem.json:
{
  "sample_id": "cau_3_001",
  "conditional_outputs": [
    {"student_indices": [1, 5, 9, ...], "expected_output": "35716"},
    {"student_indices": [2, 6, 10, ...], "expected_output": "46817"},
    ...
  ]
}
```

#### Hậu quả:

- **Conditional outputs không thể resolve** (không biết student_index nào)
- **Pipeline sẽ chấm sai** vì không biết expected output nào dùng
- **Partial credit rule sẽ áp dụng sai**

#### Code liên quan:

```python
# File: Cell 25 (resolve_conditional_output)
def resolve_conditional_output(sample, criterion):
    student_index = sample.get("student_index")  # ← None!

    for cond in conditional_outputs:
        if student_index in cond.get("student_indices", []):  # ← Không match
            return cond.get("expected_output")

    # Fallback: return cái gì? → Sẽ fail hoặc chấm sai
```

#### ✅ Giải pháp:

1. **Thêm student_index trong test_input.json**:
   ```python
   # Auto-extract từ sample_id format: cau_X_YYY
   sample_id = "cau_3_001"
   match = re.match(r'cau_\d+_(\d+)', sample_id)
   student_index = int(match.group(1))  # = 1
   ```
2. **Hoặc tối ưu resolve_conditional_output()** để auto-extract từ sample_id:

   ```python
   def resolve_conditional_output(sample, criterion):
       student_index = sample.get("student_index")

       # Auto-extract nếu missing
       if student_index is None:
           sample_id = sample.get("sample_id", "")
           match = re.match(r'cau_\d+_(\d+)', sample_id)
           if match:
               student_index = int(match.group(1))

       # ... rest của logic
   ```

---

### 4. **PARTIAL CREDIT RULE - Logic phức tạp và có thể sai**

#### Vấn đề:

```python
sample_parem.json:
{
  "cau_1_001": {
    "partial_credit_rule": {
      "type": "count_correct_tokens",
      "partial_score": 0.25,  # 25% of max_score
      "condition": "correct_token_count in [2, 3]"  # ← Điều kiện Python
    }
  },

  "cau_2_001": {
    "partial_credit_rule": {
      "type": "count_correct_tokens",
      "partial_score": 0.25,
      "condition": "correct_token_count == 1"  # ← Condition khác
    }
  },

  "cau_3_001": {
    "partial_credit_rule": {
      "type": "count_wrong_tokens",  # ← Type khác!
      "partial_score": 0.25,
      "condition": "wrong_token_count in [1, 2]"  # ← Condition khác!
    }
  }
}
```

#### Hậu quả:

- **3 loại partial_credit_rule khác nhau** (count_correct_tokens, count_wrong_tokens, ?)
- **Code chỉ hỗ trợ 2 loại** (xem Cell 25 - grade_expected_output_criterion_v2)
- **Điều kiện Python eval có thể chậy hoặc fail nếu invalid**
- **Nếu rule không match → điểm toàn bộ hoặc 0, không partial**

#### Code liên quan:

```python
# File: Cell 25 (grade_expected_output_criterion_v2)
if partial_credit_rule:
    rule_type = partial_credit_rule.get("type")

    if rule_type == "count_correct_tokens":
        # Câu 1, 2: correct_token_count in [2, 3] hoặc == 1
        condition_str = partial_credit_rule.get("condition")
        try:
            correct_token_count = correct_count
            if eval(condition_str):  # ← eval() có nguy hiểm!
                score = partial_credit_rule.get("partial_score") * max_score
        except:
            pass  # ← Silent fail!

    elif rule_type == "count_wrong_tokens":
        # Câu 3: wrong_token_count in [1, 2]
        condition_str = partial_credit_rule.get("condition")
        try:
            wrong_token_count = wrong_count
            if eval(condition_str):
                score = partial_credit_rule.get("partial_score") * max_score
        except:
            pass  # ← Silent fail!
```

#### ✅ Giải pháp:

1. **Thêm error logging**: Thay `pass` bằng `print()` hoặc logging
2. **Validate partial_credit_rule trước chạy**: Kiểm tra toàn bộ rule có valid không
3. **Hỗ trợ tất cả rule types**: Kiểm tra xem còn rule type nào không được xử lý
4. **Thay `eval()` bằng AST parsing** để an toàn hơn

---

### 5. **NEGATIVE NUMBER TOKENIZATION - "-4" có thể bị tách sai**

#### Vấn đề:

```python
test_input.json:
{
  "cau_2_001": {
    "student_answer": "12 -4"  # ← Negative number
  }
}

sample_parem.json:
{
  "cau_2_001": {
    "expected_output": "12 -4",
    "expected_output_tokens": ["12", "-4"],  # ← Negative should be "-4" not ["", "4"]
  }
}
```

#### Hậu quả:

- **tokenize_answer("12 -4")** → Nếu tokenization sai → ["12", "", "4"] hoặc ["12", "-", "4"]
- **Comparison sẽ fail**: expected ["12", "-4"], actual ["12", "", "4"]
- **Câu 2 sẽ chấm SALAADS**

#### Code liên quan:

```python
# File: Cell 4 (tokenize_answer)
def tokenize_answer(text):
    if re.search(r"\s+", text):
        return [t for t in re.split(r"\s+", text) if t]  # ← Đúng, giữ "-4"
    return [text]
```

**Note**: Hàm `tokenize_answer()` có vẻ ổn. Nhưng cần test với negative numbers.

#### ✅ Giải pháp:

1. **Test tokenize_answer() với negative numbers**:
   ```python
   test_cases = [
       ("3 4 2 9", ["3", "4", "2", "9"]),
       ("12 -4", ["12", "-4"]),
       ("1.5 -2.5 3", ["1.5", "-2.5", "3"]),
   ]
   for text, expected in test_cases:
       result = tokenize_answer(text)
       assert result == expected, f"Mismatch: {result} != {expected}"
   ```

---

## 🟡 CÁC LỖI CÓ NGUY HIỂM CAO (HIGH)

### 6. **LLM API CALL FAILURE - Không có LLM config hợp lệ**

#### Vấn đề:

```python
# File: Cell 2 (CFG)
CFG = {
    "use_llm": True,  # ← Bật LLM
    "model_api": "https://mkp-api.fptcloud.com/v1/chat/completions",
    "api_key": "sk-jlkMWMnKhhu6j3pBcOmhASGV7Ls_FYKVM-Ac1DmCKpA=",  # ← API key có hạn!
}

# Khi chạy System 2 (Hybrid) hoặc System 3 (Pure LLM):
# - Nếu LLM API fail → Fallback to teacher review hoặc score=0
# - Nếu LLM response format sai → JSON parse error
```

#### Hậu quả:

- **Nếu API key hết hạn → TOÀN BỘ LLM calls fail**
- **System 2 (Hybrid) sẽ fallback to heuristic** (OK)
- **System 3 (Pure LLM) sẽ trả về score=0** (LỖI!)
- **Khó debug vì error message bị truncate**

#### Code liên quan:

```python
# File: Cell 10 (call_llm_json)
response = requests.post(model_api, headers=headers, json=payload, timeout=120)
response.raise_for_status()

# Nếu fail:
# - return {"error": "...", "message": "LLM API failed..."}
# - Grading sẽ bỏ qua hoặc trả score=0
```

#### ✅ Giải pháp:

1. **Test LLM API trước chạy batch**:
   ```python
   test_prompt = "Test LLM connection. Return JSON: {\"status\": \"ok\"}"
   result = call_llm_json(test_prompt)
   assert "error" not in result, "LLM API is down!"
   ```
2. **Ghi log LLM calls**: Để trace khi nào fail
3. **Disable LLM nếu không cần**: `CFG["use_llm"] = False`

---

### 7. **ROUTING CONFIDENCE LOW - Chương trình có thể rơi vào teacher review quá nhiều**

#### Vấn đề:

```python
compute_routing_confidence() sử dụng weights cứng:
{
  "visual": 0.9,
  "expected_output": 0.85,
  "expected_value": 0.55,
  "q_code": 0.6,
  "essay": 0.45,
  ...
}

Các câu hỏi không rõ dạng → confidence thấp → cần teacher review
```

#### Hậu quả:

- **Câu 3 (conditional output)**: Có "giá trị nhập vào" + "kết quả in ra" → conf ≈ 0.7 (medium)
- **Nếu conf < 0.6 → set teacher_review_required = true**
- **Batch grading sẽ flag quá nhiều samples cần review**
- **Hiệu suất chấm điểm tự động giảm**

#### ✅ Giải pháp:

1. **Tối ưu weights** dựa trên test data
2. **Thêm more signals** (ví dụ: sample_id format, question_number, etc.)
3. **Nâng confidence threshold** nếu heuristic đã tốt

---

### 8. **VALIDATION ERRORS - Schema không match hoặc trường missing**

#### Vấn đề:

```python
test_input.json:
{
  "sample_id": "cau_1_001",
  "question": { "text": "..." },
  "student_answer": { "full_text": "3 4 2 9" },
  "max_score": 0.5,
  # ← Missing: "teacher_barem" (nên embedded trong sample hoặc từ barem_dict)
  # ← Missing: "question_number" (có thể auto-extract từ sample_id)
}

sample_parem.json:
{
  # ← Missing: "ma_de" (exam code)
  # ← Missing: "exam_id"
  "teacher_barem": [...]
}
```

#### Hậu quả:

- **validate_sample_schema()** sẽ trả về **errors**
- **Pipeline sẽ set teacher_review_required = true**
- **Nhiều samples sẽ cần review thủ công**

#### ✅ Giải pháp:

1. **Auto-extract missing fields**:
   ```python
   sample_id = "cau_1_001"
   if "question_number" not in sample:
       sample["question_number"] = int(re.search(r'cau_(\d+)_', sample_id).group(1))
   ```
2. **Validate schema before batch**: Kiểm tra toàn bộ samples trước chạy

---

## 🟢 CÁC CẢNH BÁO VỪA (MEDIUM)

### 9. **FUNCTION REFERENCES IN CODE - grade_expected_output_criterion_v2 được gọi nhưng không xác định ở đâu**

Lỗi: Cell 16 (grade_criterion) gọi `grade_expected_output_criterion_v2()` nhưng hàm này định nghĩa ở Cell 25, có thể execution order sai.

### 10. **SILENT FAILS IN EXCEPTION HANDLERS**

Nhiều try-except blocks chỉ `pass` mà không log:

```python
try:
    correct_token_count = correct_count
    if eval(condition_str):
        score = ...
except:
    pass  # ← Lỗi bị swallow!
```

---

## 📊 BẢNG TÓMLƯỢC VẤNĐỀ

| ID  | Tiêu Đề                          | Mức Độ      | Loại   | Ảnh Hưởng                |
| --- | -------------------------------- | ----------- | ------ | ------------------------ |
| 1   | Data Mismatch (test vs expected) | 🔴 Critical | Data   | Câu 1 sẽ chấm sai        |
| 2   | Question Type Null               | 🔴 Critical | Input  | Routing phải chạy trước  |
| 3   | Missing Student Index            | 🔴 Critical | Data   | Conditional outputs fail |
| 4   | Partial Credit Rule Complex      | 🟡 High     | Logic  | Điểm partial sai         |
| 5   | Negative Number Tokenization     | 🟡 High     | Logic  | Câu 2 sẽ chấm sai        |
| 6   | LLM API Failure                  | 🟡 High     | Infra  | System 2,3 fail          |
| 7   | Routing Confidence Low           | 🟡 High     | Logic  | Quá nhiều teacher review |
| 8   | Validation Errors                | 🟡 High     | Schema | Schema mismatch          |
| 9   | Function Reference Order         | 🟢 Medium   | Code   | Cell execution order     |
| 10  | Silent Exception Handlers        | 🟢 Medium   | Code   | Debugging khó            |

---

## ✅ CÁC ĐIỂM TÍCH CỰC

### Những gì Pipeline làm TỐT:

1. **Kiến trúc 3 Systems** (Heuristic, Hybrid, Pure LLM) - linh hoạt
2. **Hỗ trợ Conditional Outputs** (cau_3, 8, 9) - xử lý parametric rubric
3. **Token-by-token Comparison** - chính xác cho program output
4. **Fallback Mechanism** - LLM fallback khi heuristic không sure
5. **Error Detection** - phát hiện lỗi học sinh (detected_errors field)
6. **Partial Credit Support** - cho phép tính điểm từng phần
7. **Validation Framework** - kiểm tra schema trước/sau routing
8. **Comprehensive Logging** - detailed results + feedback

---

## 🚀 KHUYẾN CÁO TRƯỚC KHI CHẠY BATCH

### 1. **DATA VALIDATION CHECKLIST**

```python
# Kiểm tra test_input.json
for sample in test_input:
    # A. Required fields
    assert "sample_id" in sample, f"Missing sample_id"
    assert "question" in sample, f"Missing question"
    assert "student_answer" in sample, f"Missing student_answer"

    # B. Auto-extract missing fields
    if "question_number" not in sample:
        q_num = int(re.search(r'cau_(\d+)_', sample["sample_id"]).group(1))
        sample["question_number"] = q_num

    if "student_index" not in sample:
        s_idx = int(re.search(r'cau_\d+_(\d+)', sample["sample_id"]).group(1))
        sample["student_index"] = s_idx

    # C. Check student_answer tokens
    ans_text = sample["student_answer"].get("full_text", "")
    print(f"{sample['sample_id']}: tokens = {tokenize_answer(ans_text)}")
```

### 2. **RUBRIC VALIDATION CHECKLIST**

```python
# Kiểm tra sample_parem.json
for criterion in sample_parem["teacher_barem"]:
    # A. Check partial_credit_rule
    rule = criterion.get("partial_credit_rule")
    if rule:
        rule_type = rule.get("type")
        condition_str = rule.get("condition")

        # Validate condition is valid Python expression
        try:
            if rule_type == "count_correct_tokens":
                correct_token_count = 2  # test
                eval(condition_str)
            elif rule_type == "count_wrong_tokens":
                wrong_token_count = 1  # test
                eval(condition_str)
        except SyntaxError as e:
            print(f"❌ Invalid condition in {criterion['criterion_id']}: {condition_str}")

    # B. Check conditional_outputs
    cond_outs = criterion.get("conditional_outputs", [])
    if cond_outs:
        for cond in cond_outs:
            assert "expected_output" in cond, "Missing expected_output in conditional"
            assert "student_indices" in cond or "condition" in cond, "Missing student_indices/condition"
```

### 3. **ROUTING TEST**

```python
# Test routing trên một vài samples
for i, sample in enumerate(test_input[:3]):
    routing = route_question_with_heuristic(sample)
    print(f"[{i}] {sample['sample_id']}")
    print(f"    Type: {routing['question_type']} (conf={routing['confidence']:.2f})")
    print(f"    Candidates: {[(c['type'], f\"{c['score']:.2f}\") for c in routing['candidates'][:3]]}")
```

### 4. **GRADING DRY RUN**

```python
# Test grading trên 1 sample trước batch
sample = test_input[0]
result = grade_sample(sample, PARAMETRIC_BAREM_DICT)

print(f"Sample: {sample['sample_id']}")
print(f"Score: {result['score']}/{result['max_score']}")
print(f"Status: {result['status']}")
print(f"Criteria results:")
for cr in result.get('criterion_results', []):
    print(f"  - {cr['criterion_id']}: {cr['score']}/{cr['max_score']} ({cr['status']})")
    if cr.get('detected_errors'):
        print(f"    Errors: {cr['detected_errors']}")
```

### 5. **BATCH CONFIGURATION**

```python
# Cấu hình trước chạy batch
CFG = {
    "use_llm": False,  # Tắt LLM nếu không chắc API
    "teacher_review_threshold": 0.75,  # Câu conf < 0.75 cần review
    "enable_static_analysis": True,
    "enable_rubric_mapping": True
}

# Chạy grading
results = []
for i, sample in enumerate(test_input):
    result = grade_sample(sample, PARAMETRIC_BAREM_DICT)
    results.append(result)

    # Print progress
    if (i + 1) % 10 == 0:
        print(f"Processed {i + 1}/{len(test_input)} samples")

    # Check for issues
    if result.get('teacher_review_required'):
        print(f"  ⚠ {sample['sample_id']} needs review")

# Save results
with open("grading_results_batch.json", "w") as f:
    json.dump(results, f, indent=2)
```

---

## 📝 KẾT LUẬN VÀ KHUYẾN NGHỊ

### Kết Luận:

Pipeline **có khả năng cao sẽ chạy sai** hoặc **báo sai lỗi** do:

- Data mismatch giữa test_input và sample_parem
- Missing fields (question_number, student_index)
- Partial credit rule logic phức tạp
- Routing confidence có thể thấp

### Khuyến Nghị Ưu Tiên:

**🔴 Cần sửa NGAY (Before Running Batch):**

1. ✅ Kiểm tra lại dữ liệu: test_input cau_1_001 student_answer = "3 4 2 9" vs expected = "3529" hay "3 4 2 9"?
2. ✅ Thêm auto-extract student_index và question_number vào test_input
3. ✅ Test routing function trên tất cả samples
4. ✅ Test partial_credit_rule evaluation trước batch
5. ✅ Validate all schemas trước batch

**🟡 Nên sửa (Before Production):** 6. ✅ Thay `eval()` bằng safer expression evaluator 7. ✅ Add logging cho LLM API calls 8. ✅ Optimize routing weights dựa trên test results 9. ✅ Remove silent exception handlers (add logging)

**🟢 Có thể sửa sau (Nice to Have):** 10. ✅ Refactor grade_criterion_pure_llm_v2() vào Cell trước grade_criterion() 11. ✅ Add comprehensive test suite 12. ✅ Create data validation utility functions

---

## 📎 Danh Sách File Cần Kiểm Tra

- `test_input.json` - Kiểm tra dữ liệu + thêm question_number, student_index
- `sample_parem.json` - Kiểm tra partial_credit_rule + conditional_outputs
- `pipeline (2).ipynb` Cell 2 - CFG settings
- `pipeline (2).ipynb` Cell 4 - tokenize_answer() function
- `pipeline (2).ipynb` Cell 9 - route_question functions
- `pipeline (2).ipynb` Cell 16 - grade_criterion() orchestrator
- `pipeline (2).ipynb` Cell 25 - grade_expected_output_criterion_v2() + resolve_conditional_output()

---

**Prepared by:** AI Code Reviewer
**Date:** 31/5/2026
**Status:** Ready for Action
