# LLM Prompt Flow Documentation

## 1. TỔNG QUAN CẤU TRÚC HÀM LLM

```
grade_sample_advised() [SYSTEM 4]
    ↓
grade_criterion_advised()
    ↓
grade_heuristic_first() → heuristic_result
    ↓
grade_with_llm_advised()
    ├─ Input: sample, criterion, heuristic_result
    ├─ Kiểm tra: Bài có trống không? → skip LLM
    ├─ Chuẩn bị: rubric_text, expected_output, question_context
    └─ Gọi: call_llm_cot()
        ├─ BƯỚC 1: THINK (call_llm_cot)
        │   ├─ think_prompt xây dựng (5 bước suy luận)
        │   ├─ API call đến LLM với temperature=0.2
        │   └─ Lấy cot_reasoning
        │
        └─ BƯỚC 2: DECIDE (call_llm_cot)
            ├─ decide_prompt xây dựng (dùng cot_reasoning)
            ├─ API call đến LLM với temperature=0
            ├─ Parse JSON kết quả
            └─ Trả về: score, status, reasoning, confidence
```

---

## 2. CÁC HÀM LLM CHÍNH

### A. call_llm_json() - ĐƠN GIẢN (1 lần gọi)

**Vị trí:** Line 325-395

**Khi nào dùng:**

- Gọi LLM một lần duy nhất
- Không cần suy luận chi tiết
- Yêu cầu prompt đơn giản

**Luồng:**

```
call_llm_json(prompt, schema_name, retries=3)
    ├─ Kiểm tra: CFG["use_llm"] enabled?
    ├─ Chuẩn bị headers với Authorization
    ├─ Retry loop (tối đa 3 lần)
    │   ├─ POST đến model_api
    │   ├─ Extract JSON từ response
    │   └─ Return if success
    └─ Nếu fail tất cả: trả về error
```

**Prompt Template:**

```python
prompt = f"""Bạn là [role].
[Task description]

[Context/Input]

Trả về JSON:
{{
    "field1": "...",
    "field2": "..."
}}"""
```

**Settings:**

- `temperature`: 0 (deterministic)
- `max_tokens`: default (không giới hạn)
- `retry`: 3 lần

---

### B. call_llm_cot() - CHAIN OF THOUGHT (2 lần gọi)

**Vị trí:** Line 1117-1290

**Khi nào dùng:**

- Yêu cầu suy luận chi tiết
- Cần giải thích từng bước
- Chấm điểm phức tạp

**Luồng:**

```
call_llm_cot(
    question_context,
    criterion_content,
    expected_output,
    student_text,
    max_score,
    rubric_text,
    retries=3
)
    ├─ BƯỚC 1: THINK (Suy luận)
    │   ├─ Xây dựng think_prompt (gồm 5 bước)
    │   ├─ POST với temperature=0.2
    │   └─ Lấy cot_reasoning (600 tokens max)
    │
    ├─ BƯỚC 2: DECIDE (Ra quyết định)
    │   ├─ Xây dựng decide_prompt (dùng cot_reasoning)
    │   ├─ POST với temperature=0
    │   ├─ Parse JSON response
    │   └─ Return score, status, confidence (300 tokens max)
    │
    └─ Error handling: Return error message
```

**Think Prompt Template:**

```
Bạn là một giáo viên chấm thi lập trình đang phân tích bài làm.
Hãy SUY LUẬN CHI TIẾT từng bước trước khi đưa ra điểm số.

=== TIÊU CHÍ CHẤM ===
{criterion_content}

=== ĐÁP ÁN KỲ VỌNG ===
{expected_output or "(không có đáp án cố định — dùng rubric)"}

=== RUBRIC ===
{rubric_text or "(không có rubric bổ sung)"}

=== BÀI LÀM HỌC SINH ===
{student_text or "(trống — học sinh không trả lời)"}

=== ĐIỂM TỐI ĐA ===
{max_score}

Hãy suy luận tuần tự theo các bước sau (viết rõ từng bước):
1. Đọc và hiểu tiêu chí: tiêu chí này yêu cầu gì?
2. Phân tích đáp án kỳ vọng (nếu có): cần khớp điều gì?
3. Phân tích bài làm học sinh: học sinh đã làm gì, đúng chỗ nào, sai chỗ nào?
4. So sánh: mức độ khớp giữa bài làm và tiêu chí/đáp án kỳ vọng là bao nhiêu?
5. Kết luận sơ bộ: điểm dự kiến và lý do.
```

**Decide Prompt Template:**

```
Dựa trên phân tích sau đây:

--- BẮT ĐẦU PHÂN TÍCH ---
{cot_reasoning}
--- KẾT THÚC PHÂN TÍCH ---

Hãy đưa ra quyết định chấm điểm chính thức.
Điểm tối đa: {max_score}

Trả về JSON (và CHỈ JSON):
{
  "score": <số thực từ 0 đến {max_score}>,
  "status": "<correct|partially_correct|wrong>",
  "reasoning": "<tóm tắt lý do ngắn gọn 1-2 câu>",
  "confidence": <số thực từ 0.0 đến 1.0>
}
```

**Settings:**

- THINK: `temperature=0.2`, `max_tokens=600`
- DECIDE: `temperature=0`, `max_tokens=300`
- `retry`: 3 lần

---

### C. grade_with_llm_advised() - SYSTEM 4

**Vị trí:** Line 1802-1910

**Khi nào dùng:**

- System 4: LLM + Heuristic Advisory
- Luôn chạy heuristic trước
- LLM suy luận dựa trên advisory

**Luồng Chi Tiết:**

```
grade_with_llm_advised(sample, criterion, heuristic_result)
    ├─ Step 1: Extract data
    │   ├─ criterion_id, part_label, max_score
    │   └─ evidence = get_student_evidence_for_part(sample, part_label)
    │
    ├─ Step 2: Blank check
    │   └─ Nếu trống → return score=0, skip LLM
    │
    ├─ Step 3: Chuẩn bị heuristic advisory
    │   ├─ h_score, h_status, h_reason từ heuristic_result
    │   ├─ token_detail (nếu có token_evaluations)
    │   └─ rubric_text từ criterion.rubric
    │
    ├─ Step 4: Xây dựng question_context
    │   ├─ Include: "GỢI Ý TỪ HEURISTIC GRADER"
    │   │   - Score gợi ý: {h_score}/{max_score}
    │   │   - Status gợi ý: {h_status}
    │   │   - Lý do: {h_reason}
    │   │   - Chi tiết token (nếu có)
    │   │
    │   └─ Include: "HƯỚNG DẪN CHAIN-OF-THOUGHT"
    │       - Suy luận độc lập, không bị ảnh hưởng
    │       - Phân tích chi tiết từng tiêu chí
    │       - So sánh kết luận với heuristic
    │       - Đưa ra quyết định cuối cùng
    │
    ├─ Step 5: Gọi call_llm_cot()
    │   ├─ cot_result = call_llm_cot(
    │   │       question_context,
    │   │       criterion_content,
    │   │       expected_output,
    │   │       student_text,
    │   │       max_score,
    │   │       rubric_text,
    │   │       retries=3
    │   │   )
    │   │
    │   └─ Kiểm tra error
    │       └─ Nếu fail → fallback heuristic
    │
    ├─ Step 6: Extract kết quả
    │   ├─ score = min(cot_result.score, max_score)
    │   ├─ status = cot_result.status
    │   ├─ confidence = cot_result.confidence
    │   ├─ cot_reasoning = cot_result.cot_reasoning (full 5-step)
    │   └─ reasoning = cot_result.reasoning (summary)
    │
    ├─ Step 7: So sánh với heuristic
    │   └─ agreed_with_heuristic = (score ≈ h_score AND status == h_status)
    │
    └─ Step 8: Return formatted result
        ├─ criterion_id, part_label, score, max_score
        ├─ status, is_correct, llm_used
        ├─ grading_method: "llm_advised_cot"
        ├─ llm_reasoning (summary)
        ├─ cot_reasoning (full 5-step)
        ├─ agreed_with_heuristic (boolean)
        ├─ confidence (0.0-1.0)
        ├─ heuristic_score, heuristic_status, heuristic_reason
        └─ student_answer_text, evidence
```

**Question Context Template (Advisory):**

```
══ GỢI Ý TỪ HEURISTIC GRADER ══
Score gợi ý : {h_score}/{max_score}
Status gợi ý: {h_status}
Lý do       : {h_reason}
Chi tiet tung token:
  [0] expected='3' student='3' > [OK]
  [1] expected='5' student='5' > [OK]
  ...

══ HƯỚNG DẪN CHAIN-OF-THOUGHT ══
1. Trước hết, suy luận độc lập mà KHÔNG bị ảnh hưởng bởi gợi ý
2. Phân tích chi tiết từng tiêu chí, so sánh bài làm với tiêu chuẩn
3. Sau khi suy luận xong, so sánh kết luận của bạn với gợi ý của Heuristic:
   - Nếu bạn đồng ý → hãy giải thích tại sao
   - Nếu bạn không đồng ý → giải thích tại sao gợi ý có thể không chính xác
4. Đưa ra quyết định cuối cùng dựa trên suy luận của bạn
```

---

## 3. HÀM GỌI THEO SYSTEM

### System 1: Heuristic Only

```
grade_sample()
├─ Không gọi LLM
└─ Chỉ dùng heuristic grading
```

### System 2: Hybrid (Heuristic + Optional LLM)

```
grade_sample_hybrid()
├─ Gọi heuristic trước
├─ Nếu confidence thấp → gọi LLM
└─ (Sử dụng call_llm_json - đơn giản)
```

### System 3: Pure LLM

```
grade_sample_pure_llm()
├─ Luôn gọi LLM
├─ Không dùng heuristic
└─ (Sử dụng call_llm_cot - CoT)
```

### System 4: LLM + Advisory (HIỆN TẠI)

```
grade_sample_advised()
├─ Gọi heuristic trước (required)
├─ Luôn gọi LLM với heuristic advisory
└─ (Sử dụng call_llm_cot - CoT + Advisory)
```

---

## 4. CONFIG SETTINGS (CFG)

```python
CFG = {
    "use_llm": True,
    "model_name": "SaoLa-Llama3.1-planner",
    "base_url": "https://mkp-api.fptcloud.com",
    "model_api": "https://mkp-api.fptcloud.com/v1/chat/completions",
    "api_key": os.environ.get("LLM_API_KEY", "..."),

    # Chain of Thought settings
    "use_chain_of_thought": True,
    "cot_max_tokens_think": 600,      # THINK phase
    "cot_max_tokens_decide": 300,     # DECIDE phase

    # Threshold
    "teacher_review_threshold": 0.65,  # Nếu confidence < 0.65 → cần review
}
```

---

## 5. ERROR HANDLING & FALLBACK

```
call_llm_cot()
    ├─ Attempt 1-3: Try API call
    ├─ If timeout/error → Retry
    └─ After 3 retries fail → Return error

grade_with_llm_advised()
    ├─ If cot_result has error
    └─ Fallback: return heuristic_result
        └─ grading_method: "heuristic_cot_failed"
```

---

## 6. OUTPUT STRUCTURE (Result JSON)

```json
{
  "criterion_id": "T1",
  "part_label": "main",
  "criterion_content": "...",

  "score": 0.5,
  "max_score": 0.5,
  "status": "correct",
  "is_correct": true,

  "llm_used": true,
  "grading_method": "llm_advised_cot",

  "llm_reasoning": "Tóm tắt ngắn gọn kết luận",
  "cot_reasoning": "1. Bước 1...\n2. Bước 2...\n...",

  "agreed_with_heuristic": true,
  "confidence": 0.95,

  "heuristic_score": 0.5,
  "heuristic_status": "correct",
  "heuristic_reason": "...",

  "student_answer_text": "...",
  "evidence": { ... }
}
```

---

## 7. FLOW DIAGRAM (Text Format)

```
┌─ Sample Input
│
├─ grade_sample_advised()
│   │
│   ├─ For each criterion:
│   │   │
│   │   ├─ grade_criterion_advised()
│   │   │   │
│   │   │   ├─ Heuristic: grade_criterion()
│   │   │   │   └─ heuristic_result
│   │   │   │
│   │   │   └─ grade_with_llm_advised()
│   │   │       │
│   │   │       ├─ Check: Blank?
│   │   │       │   └─ YES → skip LLM, return score=0
│   │   │       │
│   │   │       ├─ Prepare: evidence, rubric, context
│   │   │       │
│   │   │       ├─ call_llm_cot()
│   │   │       │   │
│   │   │       │   ├─ THINK (Step 1)
│   │   │       │   │   └─ LLM suy luận 5 bước
│   │   │       │   │
│   │   │       │   └─ DECIDE (Step 2)
│   │   │       │       └─ LLM ra quyết định JSON
│   │   │       │
│   │   │       └─ Return: score, status, cot_reasoning, confidence
│   │   │
│   │   └─ criterion_result with CoT details
│   │
│   └─ Aggregate all criterion results
│
└─ Output: grading_results_s4.json with full CoT logs
```

---

## 8. QUICK REFERENCE

| Hàm                        | Bước | Temperature | Max Tokens | Dùng cho           |
| -------------------------- | ---- | ----------- | ---------- | ------------------ |
| `call_llm_json()`          | 1    | 0           | -          | Simple grading     |
| `call_llm_cot()` THINK     | 1    | 0.2         | 600        | Detailed reasoning |
| `call_llm_cot()` DECIDE    | 2    | 0           | 300        | JSON decision      |
| `grade_with_llm_advised()` | -    | -           | -          | System 4 wrapper   |

---

## 9. EXAMPLE: SYSTEM 4 EXECUTION

Input: 1 sample, 1 criterion

```
Sample: cau_1_001
Criterion: T1 (score requirement: 0.5)
Expected output: "3529"
Student answer: "3529"

1. grade_sample_advised() starts
2. grade_criterion_advised() for criterion T1
3. Heuristic: grade_criterion() → score=0.5, status="correct"
4. grade_with_llm_advised(sample, criterion, heuristic_result)
   └─ question_context includes heuristic advisory
   └─ call_llm_cot() with 2 API calls:
       ├─ API Call 1 (THINK): LLM reasons through 5 steps
       │   → cot_reasoning: "1. Đọc tiêu chí...\n2. Phân tích...\n..."
       │
       └─ API Call 2 (DECIDE): LLM decides
           → {score: 0.5, status: "correct", confidence: 0.95}
5. Return: {
     grading_method: "llm_advised_cot",
     score: 0.5,
     cot_reasoning: "...",
     agreed_with_heuristic: true,
     confidence: 0.95
   }
6. Output saved to grading_results_s4.json
```
