# LLM Prompt Flow - Quick Reference

## SYSTEM 4 LLM ADVISORY FLOW (Current)

```
Input Sample + Criteria
    ↓
grade_sample_advised()
    ↓
For each criterion:
    ├─ HEURISTIC: grade_criterion()
    │   └─ Return: heuristic_result {score, status, reason}
    │
    └─ LLM ADVISORY: grade_with_llm_advised()
        │
        ├─ Extract evidence
        ├─ Check blank? → Skip if yes
        ├─ Prepare rubric + context
        │
        └─ call_llm_cot() → 2 API calls
            ├─ CALL 1 - THINK (Suy luận 5 bước)
            │   └─ temp=0.2, tokens=600
            │   └─ Output: cot_reasoning (text)
            │
            └─ CALL 2 - DECIDE (Ra quyết định)
                └─ temp=0, tokens=300
                └─ Output: JSON {score, status, confidence}
Output: grading_results_s4.json
```

---

## LLM FUNCTIONS

### 1. call_llm_json() - Simple (1 call)

- **Use:** Basic grading without CoT
- **Calls:** 1 API call
- **Temp:** 0 (deterministic)
- **Returns:** Parsed JSON

### 2. call_llm_cot() - Chain of Thought (2 calls)

- **Use:** Detailed grading with reasoning
- **Calls:** 2 API calls (THINK + DECIDE)
- **Temps:** THINK=0.2, DECIDE=0
- **Tokens:** THINK=600, DECIDE=300
- **Returns:** {cot_reasoning, score, status, confidence}

### 3. grade_with_llm_advised() - System 4

- **Use:** LLM with heuristic advisory
- **Calls:** call_llm_cot() (2 API calls)
- **Workflow:** Heuristic → LLM (with advisory context)
- **Returns:** Full result with cot_reasoning + agreement flag

---

## PROMPT TEMPLATES

### A. THINK Prompt (Phase 1)

```
Bạn là giáo viên chấm thi lập trình.
Hãy SUY LUẬN CHI TIẾT từng bước trước khi đưa ra điểm số.

=== TIÊU CHÍ CHẤM ===
{criterion_content}

=== ĐÁP ÁN KỲ VỌNG ===
{expected_output}

=== RUBRIC ===
{rubric_text}

=== BÀI LÀM HỌC SINH ===
{student_text}

=== ĐIỂM TỐI ĐA ===
{max_score}

Suy luận tuần tự:
1. Đọc và hiểu tiêu chí: tiêu chí này yêu cầu gì?
2. Phân tích đáp án kỳ vọng: cần khớp điều gì?
3. Phân tích bài làm học sinh: học sinh làm gì, đúng/sai chỗ nào?
4. So sánh: mức độ khớp là bao nhiêu?
5. Kết luận sơ bộ: điểm dự kiến và lý do?
```

### B. DECIDE Prompt (Phase 2)

```
Dựa trên phân tích:

--- BẮT ĐẦU PHÂN TÍCH ---
{cot_reasoning}
--- KẾT THÚC PHÂN TÍCH ---

Đưa ra quyết định chấm điểm chính thức.
Điểm tối đa: {max_score}

Trả về JSON:
{
  "score": <0 to {max_score}>,
  "status": "correct|partially_correct|wrong",
  "reasoning": "<summary 1-2 sentences>",
  "confidence": <0.0-1.0>
}
```

### C. Advisory Context (in question_context)

```
══ GỢI Ý TỪ HEURISTIC GRADER ══
Score gợi ý : {h_score}/{max_score}
Status gợi ý: {h_status}
Lý do       : {h_reason}
Chi tiết token:
  [0] expected='3' student='3' > [OK]
  ...

══ HƯỚNG DẪN CHAIN-OF-THOUGHT ══
1. Suy luận độc lập, KHÔNG bị ảnh hưởng
2. Phân tích chi tiết từng tiêu chí
3. So sánh kết luận của bạn với heuristic:
   - Đồng ý → giải thích tại sao
   - Không đồng ý → giải thích tại sao gợi ý không chính xác
4. Đưa ra quyết định cuối cùng
```

---

## CONFIGURATION (CFG)

```python
CFG = {
    "use_llm": True,
    "model_name": "SaoLa-Llama3.1-planner",
    "model_api": "https://mkp-api.fptcloud.com/v1/chat/completions",
    "api_key": os.environ.get("LLM_API_KEY"),

    "use_chain_of_thought": True,
    "cot_max_tokens_think": 600,      # THINK phase
    "cot_max_tokens_decide": 300,     # DECIDE phase

    "teacher_review_threshold": 0.65,  # Flag if confidence < 0.65
}
```

---

## OUTPUT STRUCTURE

```json
{
  "criterion_id": "T1",
  "score": 0.5,
  "max_score": 0.5,
  "status": "correct",

  "llm_used": true,
  "grading_method": "llm_advised_cot",

  "cot_reasoning": "1. Đọc...\n2. Phân tích...\n3. So sánh...\n4. Kết luận...",
  "llm_reasoning": "Tóm tắt kết luận",

  "agreed_with_heuristic": true,
  "confidence": 0.95,

  "heuristic_score": 0.5,
  "heuristic_status": "correct"
}
```

---

## SYSTEMS COMPARISON

| System | Heuristic | LLM      | Method               |
| ------ | --------- | -------- | -------------------- |
| 1      | Only      | ✗        | Static analysis      |
| 2      | First     | Optional | If confidence low    |
| 3      | No        | Always   | Pure LLM grading     |
| 4      | First     | Always   | LLM + Advisory (CoT) |

---

## API CALL SEQUENCE (System 4)

```
1. grade_sample_advised()
   ├─ grade_criterion_advised()
   │   ├─ Call 1: grade_criterion() → heuristic_result
   │   └─ Call 2: grade_with_llm_advised()
   │       └─ call_llm_cot()
   │           ├─ API Call A: POST to model_api (THINK)
   │           │   ├─ Request: criterion + student_text + rubric
   │           │   ├─ Temperature: 0.2
   │           │   └─ Response: cot_reasoning (600 tokens)
   │           │
   │           └─ API Call B: POST to model_api (DECIDE)
   │               ├─ Request: cot_reasoning
   │               ├─ Temperature: 0
   │               └─ Response: JSON {score, status, confidence}
   │
   └─ Return: Result with full CoT details
```

**Total API Calls per Sample (15 criteria):**

- Heuristic: 15 calls (internal, no API)
- LLM THINK: 15 API calls
- LLM DECIDE: 15 API calls
- **Total: 30 API calls** (~75-150 seconds)

---

## ERROR HANDLING

```
call_llm_cot()
├─ Retry loop (max 3 times)
├─ On each failure:
│   └─ Continue to next attempt
└─ After 3 failures:
    └─ Return {error: "...", cot_used: false}

grade_with_llm_advised()
├─ If error from call_llm_cot():
│   └─ FALLBACK to heuristic_result
│   └─ Set grading_method: "heuristic_cot_failed"
└─ Return fallback or LLM result
```

---

## EXECUTION EXAMPLE

```
Input: sample=cau_1_001, criterion=T1
Expected: "3529", Student: "3529"

1. Heuristic scores: 0.5 (correct)
2. LLM Advisory:
   THINK → "1. Tiêu chí: ghi đúng kết quả chương trình...
            2. Đáp án: 3529...
            3. Bài làm: 3529...
            4. So sánh: khớp 100%...
            5. Kết luận: đúng → 0.5 điểm"

   DECIDE → {"score": 0.5, "status": "correct",
             "confidence": 0.95}

3. Result: score=0.5, agreed_with_heuristic=true, confidence=0.95
   grading_method="llm_advised_cot"
```

---

## FILES

1. **LLM_PROMPT_FLOW.md** - Detailed reference with all sections
2. **LLM_PROMPT_FLOW_DETAILED.md** - Visual diagrams and examples
3. **LLM_PROMPT_FLOW_QUICKREF.md** - This file (quick lookup)

---

## KEY METRICS

- **Execution time:** 75-150 seconds per 15-criterion sample
- **API calls:** 30 per sample (2 × 15 criteria)
- **Token usage:** ~13,500 per sample (900 × 15)
- **Accuracy:** 84.4% on test_input_perfect.json
- **Improvement:** +5-10% vs heuristic baseline

---

## QUICK DEBUG

| Issue                 | Check                                            |
| --------------------- | ------------------------------------------------ |
| LLM not responding    | CFG["use_llm"] == True, API key, network         |
| JSON parse error      | Temperature=0 in DECIDE, "Trả về JSON" in prompt |
| Fallback to heuristic | grading_method="heuristic_cot_failed"            |
| Low confidence        | Model uncertainty, ambiguous criteria            |
| Blank answers skipped | Early exit when evidence.is_blank==True          |
