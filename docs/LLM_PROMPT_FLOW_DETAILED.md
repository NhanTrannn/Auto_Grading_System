# LLM Prompt Execution Flow - Visual Diagram

## 1. ARCHITECTURE DIAGRAM

```
┌──────────────────────────────────────────────────────────────────────┐
│                    GRADING PIPELINE (System 4)                        │
└──────────────────────────────────────────────────────────────────────┘

INPUT: Sample + Criteria
   ↓
   ├─ route_question() → determine question_type
   │
   └─ grade_sample_advised()
       │
       └─ For each Criterion:
           │
           ├─ HEURISTIC PHASE (Required)
           │   │
           │   └─ grade_criterion()
           │       ├─ Check question_type (fill_in_the_blank, code_execution, etc.)
           │       ├─ Run static analysis
           │       └─ Return: heuristic_result {score, status, reason}
           │
           └─ LLM ADVISORY PHASE
               │
               └─ grade_with_llm_advised()
                   │
                   ├─ Extract evidence from sample
                   ├─ Check if blank → Skip if true
                   ├─ Prepare context (rubric, expected_output)
                   │
                   └─ call_llm_cot()
                       │
                       ├─ THINK PHASE (Detailed Reasoning)
                       │   │
                       │   ├─ Build think_prompt with 5 steps
                       │   ├─ API POST with temperature=0.2
                       │   ├─ Wait for LLM thinking...
                       │   └─ Extract cot_reasoning
                       │
                       └─ DECIDE PHASE (JSON Decision)
                           │
                           ├─ Build decide_prompt (uses cot_reasoning)
                           ├─ API POST with temperature=0
                           ├─ Parse JSON response
                           └─ Return: {score, status, confidence}

OUTPUT: Detailed Result with CoT
   {
     score: 0.5,
     status: "correct",
     grading_method: "llm_advised_cot",
     cot_reasoning: "1. Đọc...\n2. Phân tích...",
     agreed_with_heuristic: true,
     confidence: 0.95
   }
```

---

## 2. FUNCTION CALL TREE

```
run_batch()
├─ load_barem()
├─ load_test_input()
├─ For each system: [1, 2, 3, 4]
│   │
│   └─ [System 4] grade_sample_advised()
│       │
│       ├─ validate_sample_schema(before_routing=False)
│       ├─ apply_question_routing()
│       ├─ validate_sample_schema(after_routing=True)
│       │
│       └─ For each criterion in criteria_list:
│           │
│           └─ grade_criterion_advised()
│               │
│               ├─ grade_criterion()  [HEURISTIC]
│               │   ├─ get_student_evidence_for_part()
│               │   ├─ Check answer type (token, line, table, visual)
│               │   └─ Return heuristic_result
│               │
│               └─ grade_with_llm_advised()  [LLM ADVISORY]
│                   │
│                   ├─ get_student_evidence_for_part()
│                   ├─ Blank check → early exit?
│                   ├─ Prepare rubric_text, expected_output
│                   ├─ Prepare question_context (with heuristic advisory)
│                   │
│                   └─ call_llm_cot()  [2 API CALLS]
│                       │
│                       ├─ THINK: requests.post(model_api)
│                       │          temperature=0.2, max_tokens=600
│                       │          → cot_reasoning
│                       │
│                       └─ DECIDE: requests.post(model_api)
│                                  temperature=0, max_tokens=300
│                                  → {score, status, confidence}
│
└─ save_results_to_json()
```

---

## 3. PROMPT COMPOSITION FLOW

```
┌─ grade_with_llm_advised()
│
├─ Build rubric_text
│   └─ Join criterion.rubric items with "- key: value"
│
├─ Build question_context (Advisory Info)
│   ├─ Include heuristic scores and reasoning
│   ├─ Add token evaluation details (if available)
│   └─ Add CoT instructions
│
├─ Prepare student_text
│   └─ From evidence.get("text", "")
│
├─ CALL 1: call_llm_cot()
│   │
│   └─ THINK_PROMPT built from:
│       ├─ TIÊU CHÍ CHẤM: {criterion_content}
│       ├─ ĐÁP ÁN KỲ VỌNG: {expected_output}
│       ├─ RUBRIC: {rubric_text}
│       ├─ BÀI LÀM HỌC SINH: {student_text}
│       ├─ ĐIỂM TỐI ĐA: {max_score}
│       │
│       └─ 5 BƯỚC SỰ LUẬN:
│           1. Đọc tiêu chí
│           2. Phân tích đáp án kỳ vọng
│           3. Phân tích bài làm
│           4. So sánh
│           5. Kết luận sơ bộ
│
│   └─ API Response: cot_reasoning (string, 600 tokens)
│
├─ CALL 2: call_llm_cot() (uses cot_reasoning from Call 1)
│   │
│   └─ DECIDE_PROMPT built from:
│       ├─ "Dựa trên phân tích sau đây:"
│       ├─ {cot_reasoning}
│       ├─ "Hãy đưa ra quyết định chấm điểm chính thức"
│       ├─ "Điểm tối đa: {max_score}"
│       │
│       └─ JSON FORMAT REQUIRED:
│           {
│             "score": <float>,
│             "status": "correct|partially_correct|wrong",
│             "reasoning": "<summary>",
│             "confidence": <float 0-1>
│           }
│
│   └─ API Response: JSON (parsed)
│
└─ Return combined result:
    {
      score, status, confidence, cot_reasoning, llm_reasoning,
      grading_method: "llm_advised_cot",
      agreed_with_heuristic: (score ≈ heuristic_score)
    }
```

---

## 4. API CALL PAYLOAD EXAMPLE

### CALL 1: THINK Phase

```json
{
  "model": "SaoLa-Llama3.1-planner",
  "messages": [
    {
      "role": "system",
      "content": "Bạn là giáo viên chấm thi. Hãy suy luận chi tiết bằng tiếng Việt."
    },
    {
      "role": "user",
      "content": "Bạn là một giáo viên chấm thi lập trình đang phân tích bài làm.\nHãy SUY LUẬN CHI TIẾT từng bước...\n\n=== TIÊU CHÍ CHẤM ===\nGhi đúng kết quả chương trình...\n\n=== ĐÁP ÁN KỲ VỌNG ===\n3529\n\n=== BÀI LÀM HỌC SINH ===\n3529\n\nHãy suy luận tuần tự:\n1. Đọc và hiểu tiêu chí...\n2. Phân tích đáp án kỳ vọng...\n..."
    }
  ],
  "temperature": 0.2,
  "max_tokens": 600,
  "timeout": 120
}
```

**Response:**

```json
{
  "choices": [
    {
      "message": {
        "content": "1. Đọc và hiểu tiêu chí: Tiêu chí này yêu cầu ghi đúng kết quả chương trình, đáp án đúng là 3529. Nếu đúng 2 hoặc 3 con số thì được 0.25 điểm.\n\n2. Phân tích đáp án kỳ vọng: Đáp án kỳ vọng là 3529, tức là chương trình phải đưa ra kết quả chính xác này.\n\n3. Phân tích bài làm học sinh: Bài làm của học sinh cũng đưa ra kết quả 3529. Học sinh đã thực hiện đúng yêu cầu của bài toán, đưa ra kết quả chính xác.\n\n4. So sánh: Mức độ khớp giữa bài làm và tiêu chí/đáp án kỳ vọng là hoàn toàn phù hợp.\n\n5. Kết luận sơ bộ: Học sinh đã đưa ra kết quả chính xác 3529."
      }
    }
  ]
}
```

---

### CALL 2: DECIDE Phase

```json
{
  "model": "SaoLa-Llama3.1-planner",
  "messages": [
    {
      "role": "system",
      "content": "You are a grading assistant. Based on the reasoning provided, output ONLY a valid JSON object. No markdown, no explanation outside the JSON."
    },
    {
      "role": "user",
      "content": "Dựa trên phân tích sau đây:\n\n--- BẮT ĐẦU PHÂN TÍCH ---\n1. Đọc và hiểu tiêu chí: Tiêu chí này yêu cầu ghi đúng kết quả chương trình...\n2. Phân tích đáp án kỳ vọng: Đáp án kỳ vọng là 3529...\n3. Phân tích bài làm học sinh: Bài làm của học sinh cũng đưa ra kết quả 3529...\n4. So sánh: Mức độ khớp giữa bài làm và tiêu chí...\n5. Kết luận sơ bộ: Học sinh đã đưa ra kết quả chính xác 3529.\n--- KẾT THÚC PHÂN TÍCH ---\n\nHãy đưa ra quyết định chấm điểm chính thức.\nĐiểm tối đa: 0.5\n\nTrả về JSON (và CHỈ JSON):\n{\n  \"score\": <số thực từ 0 đến 0.5>,\n  \"status\": \"<correct|partially_correct|wrong>\",\n  \"reasoning\": \"<tóm tắt lý do ngắn gọn 1-2 câu>\",\n  \"confidence\": <số thực từ 0.0 đến 1.0>\n}"
    }
  ],
  "temperature": 0,
  "max_tokens": 300,
  "timeout": 60
}
```

**Response:**

```json
{
  "choices": [
    {
      "message": {
        "content": "{\"score\": 0.5, \"status\": \"correct\", \"reasoning\": \"Học sinh đã đưa ra kết quả chính xác 3529, đáp ứng đầy đủ yêu cầu của bài toán.\", \"confidence\": 0.95}"
      }
    }
  ]
}
```

---

## 5. TIME & TOKEN BREAKDOWN

```
Sample Processing Time (per criterion):

HEURISTIC PHASE: ~50ms
├─ Evidence extraction: ~10ms
├─ Static analysis: ~30ms
└─ Return heuristic_result: ~10ms

LLM ADVISORY PHASE: ~5-10 seconds
├─ Blank check: <1ms
├─ Prompt preparation: ~50ms
│
├─ CALL 1 (THINK):
│   ├─ Network: ~1-2 seconds
│   ├─ LLM thinking: ~2-4 seconds
│   └─ Response parsing: ~100ms
│
├─ CALL 2 (DECIDE):
│   ├─ Network: ~1-2 seconds
│   ├─ LLM deciding: ~1-2 seconds
│   └─ JSON parsing: ~50ms
│
└─ Result assembly: ~50ms

TOTAL PER CRITERION: ~5-10 seconds

Token Usage:
├─ THINK phase: ~600 tokens (max)
│   ├─ Input: ~400 tokens (criteria + student text)
│   └─ Output: ~200 tokens (5-step reasoning)
│
└─ DECIDE phase: ~300 tokens (max)
    ├─ Input: ~200 tokens (cot_reasoning)
    └─ Output: ~100 tokens (JSON)

Total tokens per criterion: ~900 tokens
```

---

## 6. ERROR HANDLING FLOW

```
grade_with_llm_advised()
├─ Call call_llm_cot()
│   │
│   └─ For attempt in range(3):
│       ├─ Try THINK API call
│       │   ├─ If timeout/connection error → Retry
│       │   ├─ If empty response → Retry
│       │   └─ If success → Proceed to DECIDE
│       │
│       ├─ Try DECIDE API call
│       │   ├─ If timeout → Retry
│       │   ├─ If JSON parse fails → Retry
│       │   └─ If success → Return cot_result
│       │
│       └─ If attempt < 2 → Continue loop
│
├─ Receive cot_result
│   │
│   └─ If "error" in cot_result OR not cot_result.get("cot_used"):
│       │
│       └─ FALLBACK TO HEURISTIC
│           ├─ Copy heuristic_result
│           ├─ Set grading_method: "heuristic_cot_failed"
│           ├─ Set llm_used: False
│           ├─ Set llm_error: "CoT LLM failed"
│           └─ Return fallback result
│
└─ If success → Return cot_result with full details
```

---

## 7. CONFIGURATION & SETTINGS

```python
# API Configuration
CFG = {
    "use_llm": True,  # Enable/disable LLM entirely
    "model_name": "SaoLa-Llama3.1-planner",
    "base_url": "https://mkp-api.fptcloud.com",
    "model_api": "https://mkp-api.fptcloud.com/v1/chat/completions",
    "api_key": os.environ.get("LLM_API_KEY"),

    # CoT Settings
    "use_chain_of_thought": True,
    "cot_max_tokens_think": 600,     # Max tokens for THINK phase
    "cot_max_tokens_decide": 300,    # Max tokens for DECIDE phase

    # Quality Threshold
    "teacher_review_threshold": 0.65,  # If confidence < this, flag for review
}
```

---

## 8. SUMMARY TABLE

| Phase        | Function                   | API Calls | Temperature | Tokens   | Purpose            |
| ------------ | -------------------------- | --------- | ----------- | -------- | ------------------ |
| Heuristic    | `grade_criterion()`        | 0         | N/A         | N/A      | Static analysis    |
| LLM Advisory | `grade_with_llm_advised()` | 2         | -           | -        | Wrapper            |
| - THINK      | `call_llm_cot()` call 1    | 1         | 0.2         | 600      | Detailed reasoning |
| - DECIDE     | `call_llm_cot()` call 2    | 1         | 0           | 300      | JSON decision      |
| **Total**    | **System 4**               | **3**     | -           | **~900** | Full grading       |

---

## 9. KEY METRICS & STATISTICS

```
Execution Time per Sample (15 criteria):
- Heuristic phase: ~750ms (50ms × 15)
- LLM advisory phase: ~75-150 seconds (5-10s × 15)
- Total: ~75-150 seconds per sample

Token Cost per Sample:
- Average: ~13,500 tokens (900 × 15 criteria)

Accuracy Improvement:
- Heuristic alone: ~80% baseline
- LLM advisory: +5-10% (from 80% → 85-90%)

Example Results:
- test_input_perfect.json: 8.44/10.00 (84.4%)
- Output: grading_results_s4.json with full CoT logs
```

---

## 10. QUICK DEBUG CHECKLIST

```
❓ LLM not responding?
  └─ Check: CFG["use_llm"] == True
  └─ Check: API key in environment variable
  └─ Check: Network connectivity to model_api

❓ Prompt too long?
  └─ Check: student_text length
  └─ Check: rubric_text length
  └─ Reduce max_tokens if needed

❓ JSON parse errors?
  └─ Check: temperature=0 in DECIDE phase
  └─ Check: "Trả về JSON" explicitly in prompt
  └─ Check: _extract_json_from_text() robustness

❓ Fallback to heuristic?
  └─ Check: LLM error in cot_result
  └─ Check: grading_method == "heuristic_cot_failed"
  └─ Check: llm_used == False

❓ Confidence score too low?
  └─ Check: Model uncertainty
  └─ Check: Ambiguous criteria or student answer
  └─ Consider: Lower teacher_review_threshold
```
