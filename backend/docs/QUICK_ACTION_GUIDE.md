# Tóm Tắt Khuyến Nghị Hành Động Ngay

## 🚨 TÌNH HÌNH HIỆN TẠI

Pipeline chưa sẵn sàng chạy batch production với test_input.json + sample_parem.json

**Kỳ vọng lỗi sai:** 40-60% câu sẽ chấm sai hoặc báo sai lỗi

---

## 🔴 HÀNH ĐỘNG ƯU TIÊN #1: XÁC MINH DỮ LIỆU ĐẦU VÀO

### Vấn đề:

```
test_input.json cau_1_001:
  student_answer = "3 4 2 9"

sample_parem.json cau_1_001:
  expected = ["3", "5", "2", "9"]

❌ KHÔNG KHỚP: token thứ 2 là "4" vs "5"
```

### Hành động:

1. **Xác minh lại dữ liệu**: Đáp án đúng cho cau_1_001 là gì?
   - Nếu đúng là "3 5 2 9" → Cập nhật test_input.json
   - Nếu đúng là "3 4 2 9" → Cập nhật sample_parem.json

2. **Kiểm tra tất cả sample**: Toàn bộ test_input có match với sample_parem không?

   ```bash
   # Script check:
   for each sample in test_input:
       q_num = sample.question_number
       expected_output = sample_parem[q_num].expected_output
       student_answer = sample.student_answer

       if student_answer != expected_output:
           PRINT "⚠ MISMATCH: {sample_id}"
   ```

---

## 🔴 HÀNH ĐỘNG ƯU TIÊN #2: THÊMISSING FIELDS

### Vấn đề:

```
test_input.json:
  {
    "sample_id": "cau_1_001",
    "question_type": null,           # ← NULL
    "student_index": undefined,      # ← MISSING
    # ← Missing "question_number"
  }
```

### Hành động - Cách 1 (Nhanh - Fix dữ liệu):

```python
import json
import re

# Load test_input
with open('test_input.json', 'r') as f:
    samples = json.load(f)

# Thêm missing fields
for sample in samples:
    sample_id = sample['sample_id']

    # Extract question_number từ sample_id format: cau_X_YYY
    if 'question_number' not in sample:
        match = re.match(r'cau_(\d+)_', sample_id)
        if match:
            sample['question_number'] = int(match.group(1))

    # Extract student_index từ sample_id format: cau_X_YYY
    if 'student_index' not in sample:
        match = re.match(r'cau_\d+_(\d+)', sample_id)
        if match:
            sample['student_index'] = int(match.group(1))

# Save back
with open('test_input.json', 'w') as f:
    json.dump(samples, f, indent=2, ensure_ascii=False)

print("✓ Updated test_input.json with question_number and student_index")
```

### Hành động - Cách 2 (Nếu không muốn edit file):

```python
# Thêm auto-extract vào grade_sample() function trước chạy:
def grade_sample(sample, barem_dict=None):
    # Auto-extract missing fields
    if "question_number" not in sample:
        match = re.match(r'cau_(\d+)_', sample.get("sample_id", ""))
        if match:
            sample["question_number"] = int(match.group(1))

    if "student_index" not in sample:
        match = re.match(r'cau_\d+_(\d+)', sample.get("sample_id", ""))
        if match:
            sample["student_index"] = int(match.group(1))

    # ... rest of function
```

---

## 🔴 HÀNH ĐỘNG ƯU TIÊN #3: TEST ROUTING

### Vấn đề:

```
Tất cả samples có question_type: null
→ Pipeline phải auto-route
→ Nếu routing sai → chấm bị sai
```

### Hành động:

```python
# Script test routing trên tất cả samples
from pathlib import Path
import json

with open('test_input.json') as f:
    samples = json.load(f)

print("Testing routing on all samples:\n")
for sample in samples:
    sample_id = sample['sample_id']
    routing_result = route_question_with_heuristic(sample)

    q_type = routing_result['question_type']
    confidence = routing_result['confidence']

    # ⚠ Flag nếu confidence thấp
    status = "✓" if confidence >= 0.75 else "⚠"

    print(f"{status} {sample_id}: {q_type} (conf={confidence:.2f})")

    # Xem candidates để debug
    if confidence < 0.75:
        candidates = routing_result.get('candidates', [])
        for c in candidates[:3]:
            print(f"    → {c['type']}: {c['score']:.2f}")

# Nếu quá nhiều ⚠, cần fix routing heuristic
```

---

## 🔴 HÀNH ĐỘNG ƯU TIÊN #4: TEST GRADING TRÊN 1 SAMPLE

### Hành động:

```python
# Test grading trên sample đầu tiên
from pathlib import Path
import json

with open('test_input.json') as f:
    samples = json.load(f)

with open('sample_parem.json') as f:
    barem_data = json.load(f)

# Build barem_dict (question_number -> criteria list)
barem_dict = {}
for criterion in barem_data.get('teacher_barem', []):
    q_num = criterion.get('question_number')
    if q_num:
        if q_num not in barem_dict:
            barem_dict[q_num] = []
        barem_dict[q_num].append(criterion)

# Grade first sample
sample = samples[0]
print(f"Testing sample: {sample['sample_id']}\n")

result = grade_sample(sample, barem_dict)

print(f"Score: {result['score']}/{result['max_score']}")
print(f"Status: {result['status']}")
print(f"Feedback: {result['feedback']}\n")

print("Criterion results:")
for cr in result.get('criterion_results', []):
    print(f"  - {cr['criterion_id']}: {cr['score']}/{cr['max_score']} ({cr['status']})")
    if cr.get('detected_errors'):
        for err in cr['detected_errors']:
            print(f"    Error: {err['message']}")

# Nếu có lỗi, debug:
print(f"\nValidation before routing: {result['validation_before_routing']}")
print(f"Validation after routing: {result['validation_after_routing']}")
print(f"Routing: {result.get('routing', {})}")
```

---

## 🟡 HÀNH ĐỘNG ƯU TIÊN #5: VALIDATE PARTIAL CREDIT RULES

### Vấn đề:

```
sample_parem.json có 3 loại partial_credit_rule:
- count_correct_tokens: "correct_token_count in [2, 3]"
- count_wrong_tokens: "wrong_token_count in [1, 2]"

Code trong Cell 25 chỉ hỗ trợ 2 loại
Nếu condition invalid → silent fail
```

### Hành động:

```python
# Validate tất cả partial_credit_rules
from pathlib import Path
import json

with open('sample_parem.json') as f:
    barem_data = json.load(f)

print("Validating partial_credit_rules:\n")
for criterion in barem_data['teacher_barem']:
    rule = criterion.get('partial_credit_rule')

    if not rule:
        continue

    q_num = criterion['question_number']
    criterion_id = criterion['criterion_id']
    rule_type = rule.get('type')
    condition_str = rule.get('condition')

    print(f"[{criterion_id}] Type: {rule_type}")
    print(f"     Condition: {condition_str}")

    # Test eval
    try:
        if rule_type == 'count_correct_tokens':
            correct_token_count = 2  # test value
            result = eval(condition_str)
            print(f"     ✓ Valid (eval result: {result})")
        elif rule_type == 'count_wrong_tokens':
            wrong_token_count = 1  # test value
            result = eval(condition_str)
            print(f"     ✓ Valid (eval result: {result})")
        else:
            print(f"     ❌ Unknown type: {rule_type}")
    except Exception as e:
        print(f"     ❌ INVALID: {e}")

    print()
```

---

## 📋 CHECKLIST TRƯỚC CHẠY BATCH

- [ ] **Data Validation**: test_input.json + sample_parem.json match?
- [ ] **Missing Fields**: question_number + student_index have been added?
- [ ] **Routing Test**: Chạy routing trên tất cả samples, conf >= 0.75?
- [ ] **Single Sample Test**: grade_sample() chạy OK trên sample[0]?
- [ ] **Partial Credit Test**: Tất cả partial_credit_rules are valid?
- [ ] **Tokenization Test**: Negative numbers like "-4" tokenized correctly?
- [ ] **LLM Config**: Nếu dùng System 2/3, test LLM API?
- [ ] **Error Logging**: Add logging thay vì silent pass?

---

## 🚀 CHẠY BATCH SAFELY

```python
# Sau khi pass tất cả checklist:

from pathlib import Path
import json

# Load data
with open('test_input.json') as f:
    samples = json.load(f)

with open('sample_parem.json') as f:
    barem_data = json.load(f)

# Build barem_dict
barem_dict = {}
for criterion in barem_data.get('teacher_barem', []):
    q_num = criterion.get('question_number')
    if q_num:
        if q_num not in barem_dict:
            barem_dict[q_num] = []
        barem_dict[q_num].append(criterion)

# Grade all samples
print(f"Grading {len(samples)} samples...\n")
results = []

for i, sample in enumerate(samples):
    try:
        result = grade_sample(sample, barem_dict)
        results.append(result)

        status = "✓" if result['status'] == 'correct' else "⚠"
        print(f"{status} [{i+1}/{len(samples)}] {sample['sample_id']}: {result['score']}/{result['max_score']} ({result['status']})")

    except Exception as e:
        print(f"❌ [{i+1}/{len(samples)}] {sample['sample_id']}: ERROR - {e}")
        results.append({
            'sample_id': sample['sample_id'],
            'status': 'error',
            'error_message': str(e)
        })

# Save results
with open('grading_results_batch.json', 'w') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print(f"\n✓ Saved results to grading_results_batch.json")

# Summary
total = len(results)
correct = sum(1 for r in results if r.get('status') == 'correct')
errors = sum(1 for r in results if r.get('status') == 'error')

print(f"\nSummary:")
print(f"  Total: {total}")
print(f"  Correct: {correct} ({100*correct/total:.1f}%)")
print(f"  Errors: {errors}")
```

---

## 📞 Nếu Gặp Lỗi

1. **Data mismatch errors**: Check test_input vs sample_parem
2. **Routing errors**: Run routing test script để debug
3. **Partial credit errors**: Check partial_credit_rule validation
4. **Negative number errors**: Test tokenize_answer("-4")
5. **Silent errors**: Add logging + error messages

---

**Deadline khuyến cáo:** Hoàn thành actions #1-4 trong 1-2 giờ
