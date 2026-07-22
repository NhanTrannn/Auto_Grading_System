# 📋 Kỹ Thuật và Phương Pháp Prompting trong Hệ Thống Chấm Thi

**Generated:** June 1, 2026  
**Hệ Thống:** Multi-Format Rubric-based Grading Pipeline  
**Model:** SaoLa-Llama3.1-planner (via FPT Cloud API)

---

## 📑 Mục Lục

1. [Tổng Quan Kiến Trúc](#tổng-quan-kiến-trúc)
2. [Kỹ Thuật Prompting Chính](#kỹ-thuật-prompting-chính)
3. [Các Hàm LLM](#các-hàm-llm)
4. [Prompt Templates Cụ Thể](#prompt-templates-cụ-thể)
5. [Cấu Hình Hiện Tại](#cấu-hình-hiện-tại)
6. [Lệnh Chạy Hiện Tại](#lệnh-chạy-hiện-tại)

---

## 🏗️ Tổng Quan Kiến Trúc

### Luồng Xử Lý Chung

```
Input Sample (JSON)
    ↓
Route Question Type (Heuristic + Parem Lookup)
    ↓
For each criterion:
    ├─ Infer grading mode (expected_output / expected_value / table / visual / llm)
    │
    ├─ Mode = "expected_output" → grade_expected_output_criterion_v2()
    ├─ Mode = "expected_value" → grade_expected_value_criterion()
    ├─ Mode = "table" → grade_table_criterion()
    ├─ Mode = "visual" → grade_visual_criterion()
    │
    └─ Mode = "llm_rubric" / "llm_or_teacher_review" 
        └─ grade_with_llm_cot() → 2-phase Chain-of-Thought LLM
            ├─ PHASE 1: THINK (Suy luận chi tiết - temp=0.2)
            └─ PHASE 2: DECIDE (Ra quyết định - temp=0)
    
Output: grading_results.json
```

### Các Hệ Thống (Systems)

| System | Kiến Trúc | Phương Pháp | Mô Tả |
|--------|-----------|-----------|-------|
| **S1** | Heuristic | Static matching + token matching | Baseline - không dùng LLM |
| **S2** | Hybrid | Heuristic → LLM fallback | Ưu tiên heuristic, LLM nếu không sure |
| **S3** | Pure LLM | LLM cho tất cả criteria | 100% dùng LLM + CoT |
| **S4** | LLM+Advisory | Heuristic advisory → LLM decision | Heuristic là góp ý, LLM ra quyết định cuối |

---

## 🎯 Kỹ Thuật Prompting Chính

### 1. **Chain-of-Thought (CoT) - Hai Bước**

**Nền Tảng Lý Thuyết:**
- Bắt LLM suy luận tường minh trước khi ra quyết định
- Giảm lỗi "nhảy thẳng" đến kết quả sai
- Tăng minh bạch (explainability)

**Cấu Trúc Hai Bước:**

#### **Bước 1: THINK (Suy Luận Chi Tiết)**
- **Mục đích:** LLM phân tích bài làm theo 5 bước có cấu trúc
- **Temperature:** 0.2 (cho phép một chút sáng tạo)
- **Max Tokens:** 600 (đủ để suy luận chi tiết)
- **Output:** `cot_reasoning` (text - suy luận toàn bộ)

**5 Bước Suy Luận:**
1. Đọc và hiểu tiêu chí: tiêu chí này yêu cầu gì?
2. Phân tích đáp án kỳ vọng: cần khớp điều gì?
3. Phân tích bài làm học sinh: học sinh làm gì, đúng/sai chỗ nào?
4. So sánh: mức độ khớp giữa bài làm và tiêu chí là bao nhiêu?
5. Kết luận sơ bộ: điểm dự kiến và lý do?

#### **Bước 2: DECIDE (Ra Quyết Định)**
- **Mục đích:** LLM quyết định điểm số dựa trên suy luận ở bước 1
- **Temperature:** 0 (hoàn toàn deterministic)
- **Max Tokens:** 300 (đủ cho JSON + tóm tắt)
- **Output:** JSON structured
  ```json
  {
    "score": <float 0 - max_score>,
    "status": "<correct|partially_correct|wrong>",
    "reasoning": "<tóm tắt ngắn gọn 1-2 câu>",
    "confidence": <float 0.0 - 1.0>
  }
  ```

**Lợi Ích CoT:**
- ✅ Giảm hallucination (LLM phải suy luận có cơ sở)
- ✅ Tăng consistency (reasoning process được chuẩn hóa)
- ✅ Dễ debug (có trace của suy luận từng bước)
- ✅ Cải thiện accuracy trên bài toán phức tạp

**Cách Bật CoT:**
```python
CFG["use_chain_of_thought"] = True  # Default: False
CFG["cot_max_tokens_think"] = 600   # Tokens cho THINK phase
CFG["cot_max_tokens_decide"] = 300  # Tokens cho DECIDE phase
```

---

### 2. **Heuristic Advisory (Góp Ý Heuristic)**

**Mục Đích:**
- Cung cấp context từ heuristic grader vào prompt LLM
- LLM ra quyết định cuối cùng, nhưng có biết heuristic nghĩ gì

**Cách Thực Hiện:**
```
Heuristic grader chạy trước → kết quả: {score, status, reason}
    ↓
Thêm vào prompt: "Heuristic grader cho điểm X, vì Y"
    ↓
LLM đọc này và có thể:
   - Đồng ý và dùng điểm đó
   - Không đồng ý và đưa ra điểm khác
```

**Ưu Điểm:**
- LLM có fast baseline từ heuristic
- Có thể phát hiện khi heuristic sai
- Giảm prompt length và token cost

---

### 3. **Conditional Output Resolution**

**Nền Tảng:**
- Các câu có đáp án khác nhau tùy theo học sinh (conditional)
- Ví dụ: "Nhập số 1-5" → đáp án kỳ vọng khác tùy số nhập

**Cách Thực Hiện:**

```python
# Trong criterion:
"conditional_outputs": [
  {
    "student_indices": [1, 2, 3],  # Áp dụng cho SV 1, 2, 3
    "expected_output": "output_A"
  },
  {
    "condition": "student_index >= 4 and student_index <= 6",  # Biểu thức condition
    "expected_output": "output_B"
  }
]
```

**Security:**
- Dùng `eval()` với restricted scope: chỉ cho phép biến `student_index`
- Không có `__builtins__` → không thể gọi hàm nguy hiểm

---

### 4. **Token-based Matching với Partial Credit**

**Nền Tảng:**
- Tách output thành các token (từ, số, ký tự)
- So sánh token-by-token
- Áp dụng partial credit rule nếu một phần đúng

**Partial Credit Rules:**

```python
"partial_credit_rule": {
  "type": "count_wrong_tokens",      # Dựa số token sai
  "condition": "wrong_token_count <= 2",
  "partial_score": 0.5  # 50% điểm nếu <= 2 token sai
}

"partial_credit_rule": {
  "type": "min_correct_tokens",      # Dựa số token đúng tối thiểu
  "threshold": 3,
  "score_if_above_threshold": 1.0,
  "score_if_below_threshold": 0
}

"partial_credit_rule": {
  "type": "date_partial_match",      # Riêng cho câu 12 (ngày tháng)
  "partial_score": 0.25  # 25% nếu tháng+năm đúng
}

"partial_credit_rule": {
  "type": "position_tolerance",      # Riêng cho câu 10 (sai ở vị trí đầu/cuối)
  "partial_score": 0.25  # 25% nếu sai ở 2 vị trí đầu hoặc 2 cuối
}
```

---

### 5. **Fuzzy Matching (Levenshtein Distance)**

**Nền Tảng:**
- So sánh độ giống nhau giữa câu trả lời học sinh và expected
- Dùng SequenceMatcher (Python's difflib)

**Ngưỡng (Thresholds):**

```python
similarity_ratio = SequenceMatcher(None, student_text, expected_text).ratio()

if similarity_ratio >= 0.85:
    score = max_score  # 85%+ giống → điểm tối đa
elif similarity_ratio >= 0.65:
    score = max_score * 0.5  # 65-84% giống → 50% điểm
else:
    score = 0  # < 65% giống → 0 điểm
```

**Normalize Before Matching:**
```python
def normalize_text(text):
    # Chuyển thành chữ thường
    # Loại bỏ khoảng trắng thừa
    # Chuyển ngoặc CJK sang ASCII
    # Chuyển quotes/dashes sang ASCII
    # etc.
```

---

### 6. **Role-Based Prompting**

**Kỹ Thuật:**
- Đặt role cụ thể cho LLM: "Bạn là giáo viên chấm thi"
- Tác động tới suy luận của LLM

**Ví Dụ:**
```
"Bạn là một giáo viên chấm thi lập trình đang phân tích bài làm.
Hãy SUY LUẬN CHI TIẾT từng bước trước khi đưa ra điểm số."
```

---

### 7. **Structured Output (JSON Schema)**

**Nền Tảng:**
- Yêu cầu LLM output JSON theo schema cụ thể
- Dễ parse + validate

**Schema Chuẩn:**
```json
{
  "score": "float (0 to max_score)",
  "status": "correct|partially_correct|wrong",
  "reasoning": "string (1-2 câu tóm tắt)",
  "confidence": "float (0.0 - 1.0)"
}
```

**Extraction Robust:**
- Strip markdown code fences (```json``` → "")
- Thử JSON.parse() trực tiếp
- Fallback: JSONDecoder.raw_decode() từ vị trí '{' đầu tiên
- Last resort: Regex greedy `\{.*\}`
- Nếu vẫn fail → error

---

### 8. **Context Layering (Xếp Lớp Context)**

**Nền Tảng:**
- Cung cấp context theo thứ tự ưu tiên
- Context gần (tiêu chí) → Context xa (câu hỏi)

**Cấu Trúc Prompt (CoT Think Phase):**
```
=== TIÊU CHÍ CHẤM ===           ← Cụ thể nhất
{criterion_content}

=== ĐÁP ÁN KỲ VỌNG ===           ← Định hướng
{expected_output}

=== RUBRIC ===                  ← Hướng dẫn
{rubric_text}

=== BÀI LÀM HỌC SINH ===         ← Dữ liệu
{student_text}

=== ĐIỂM TỐI ĐA ===              ← Ràng buộc
{max_score}

{question_context}              ← Ngữ cảnh (nếu có)
```

---

## 🔧 Các Hàm LLM

### 1. `call_llm_json(prompt, schema_name="generic", retries=3)`

**Vị Trí:** `pipeline.py` Lines 325-395

**Dùng Khi:**
- Gọi LLM một lần duy nhất
- Không cần suy luận chi tiết
- Output là JSON

**Cách Gọi:**
```python
result = call_llm_json(
    prompt="Bạn là ... JSON: {...}",
    schema_name="grading",
    retries=3
)
```

**Luồng:**
1. Kiểm tra `CFG["use_llm"]` → enabled?
2. Chuẩn bị headers (Authorization với API key)
3. Vòng retry (tối đa 3 lần):
   - POST đến `CFG["model_api"]`
   - Extract JSON từ response
   - Nếu thành công → return JSON
   - Nếu fail → retry
4. Tất cả fail → return error dict

**Payload API:**
```python
{
  "model": "SaoLa-Llama3.1-planner",
  "messages": [
    {
      "role": "system",
      "content": "Return only valid JSON. No markdown, no explanation."
    },
    {
      "role": "user",
      "content": prompt
    }
  ],
  "temperature": 0
}
```

**Settings:**
- **Temperature:** 0 (deterministic)
- **Retries:** 3 lần
- **Timeout:** 120 giây
- **Max Tokens:** Default (không giới hạn)

---

### 2. `call_llm_cot(question_context, criterion_content, expected_output, student_text, max_score, rubric_text, retries=3)`

**Vị Trí:** `pipeline.py` Lines 1246-1420

**Dùng Khi:**
- Cần suy luận chi tiết
- Cần giải thích từng bước
- Chấm điểm phức tạp (essay, short answer, etc.)

**Cách Gọi:**
```python
result = call_llm_cot(
    question_context="Bài toán là...",
    criterion_content="Tiêu chí: ...",
    expected_output="Đáp án kỳ vọng: ...",
    student_text="Bài làm của SV: ...",
    max_score=1.0,
    rubric_text="- Đầy đủ logic\n- Rõ ràng",
    retries=3
)
```

**Output:**
```python
{
  "cot_reasoning": "Suy luận chi tiết từ bước 1",
  "score": 0.8,
  "status": "partially_correct",
  "reasoning": "Tóm tắt 1-2 câu",
  "confidence": 0.85,
  "cot_used": True
}
```

**Luồng Hai Bước:**

#### **Bước 1: THINK**
```python
payload_think = {
  "model": "SaoLa-Llama3.1-planner",
  "messages": [
    {
      "role": "system",
      "content": "Bạn là giáo viên chấm thi. Hãy suy luận chi tiết bằng tiếng Việt."
    },
    {
      "role": "user",
      "content": think_prompt  # 5-bước reasoning
    }
  ],
  "temperature": 0.2,
  "max_tokens": 600
}
```

**Bước 2: DECIDE**
```python
payload_decide = {
  "model": "SaoLa-Llama3.1-planner",
  "messages": [
    {
      "role": "system",
      "content": "Trả về JSON và CHỈ JSON. Không markdown."
    },
    {
      "role": "user",
      "content": decide_prompt  # Dùng cot_reasoning từ bước 1
    }
  ],
  "temperature": 0,
  "max_tokens": 300
}
```

---

### 3. `grade_with_llm_cot(sample, criterion)`

**Vị Trí:** `pipeline.py` Lines 1426-1478

**Dùng Khi:**
- Chấm criterion phức tạp
- `use_chain_of_thought = True`

**Cách Gọi:**
```python
result = grade_with_llm_cot(sample, criterion)
```

**Luồng:**
1. Kiểm tra `CFG["use_chain_of_thought"]`
   - Nếu False → fallback về `grade_with_llm()`
2. Extract evidence từ sample (student answer text)
3. Kiểm tra blank → return 0 nếu trống
4. Chuẩn bị rubric text, expected output
5. Gọi `call_llm_cot()`
6. Parse kết quả, return detailed result

---

### 4. `grade_with_llm_advised(sample, criterion, heuristic_result)`

**Vị Trí:** `pipeline.py` Lines 1989-2100+

**Dùng Khi:**
- System 4: LLM + Advisory
- Heuristic chạy trước → kết quả làm advisory

**Cách Gọi:**
```python
heuristic_result = grade_criterion(sample, criterion)  # Run heuristic first
result = grade_with_llm_advised(
    sample,
    criterion,
    heuristic_result
)
```

**Luồng:**
1. Kiểm tra heuristic result confidence
   - Nếu high confidence → có thể skip LLM
2. Chuẩn bị advisory text từ heuristic
3. Thêm advisory vào prompt: "Heuristic: score=X, reason=Y"
4. Gọi `call_llm_cot()` (với advisory context)
5. Compare heuristic vs LLM (advisory_agreement flag)
6. Return result với advisory context

---

## 📝 Prompt Templates Cụ Thể

### **Template A: CoT THINK Phase**

```
Bạn là một giáo viên chấm thi lập trình đang phân tích bài làm.
Hãy SUY LUẬN CHI TIẾT từng bước trước khi đưa ra điểm số.

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
4. So sánh: mức độ khớp giữa bài làm và tiêu chí/đáp án kỳ vọng là bao nhiêu?
5. Kết luận sơ bộ: điểm dự kiến và lý do?
```

**Cấu Hình:**
- Temperature: 0.2
- Max Tokens: 600
- System Prompt: "Bạn là giáo viên chấm thi. Hãy suy luận chi tiết bằng tiếng Việt."

---

### **Template B: CoT DECIDE Phase**

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

**Cấu Hình:**
- Temperature: 0 (deterministic)
- Max Tokens: 300
- System Prompt: "Return only valid JSON. No markdown, no explanation."

---

### **Template C: Advisory Context (System 4)**

```
=== HEURISTIC ADVISORY ===
Heuristic grader đã phân tích bài làm này:
- Score: {heuristic_score}/{max_score}
- Status: {heuristic_status}
- Reason: {heuristic_reason}

Bạn (LLM) có thể đồng ý hoặc không đồng ý với heuristic.
Nếu bạn không đồng ý, hãy nêu rõ lý do khác.

{think_prompt}  ← 5-bước suy luận như Template A
```

---

## ⚙️ Cấu Hình Hiện Tại

### **CFG Dictionary** (từ `pipeline.py` lines 16-44)

```python
CFG = {
    # LLM Configuration
    "use_llm": True,
    "model_name": os.environ.get("LLM_MODEL_NAME", "SaoLa-Llama3.1-planner"),
    "base_url": os.environ.get("LLM_BASE_URL", "https://mkp-api.fptcloud.com"),
    "model_api": os.environ.get(
        "LLM_MODEL_API", 
        "https://mkp-api.fptcloud.com/v1/chat/completions"
    ),
    "api_key": os.environ.get(
        "LLM_API_KEY", 
        "sk-jlkMWMnKhhu6j3pBcOmhASGV7Ls_FYKVM-Ac1DmCKpA="
    ),
    
    # Model Fine-tuning
    "use_finetuned_model": False,
    
    # Grading Thresholds
    "teacher_review_threshold": 0.65,  # Score < 0.65 → teacher review
    
    # Feature Flags
    "enable_static_analysis": True,    # Dùng heuristic grading
    "enable_rubric_mapping": True,     # Map criteria từ rubric
    
    # Chain-of-Thought Configuration
    "use_chain_of_thought": False,     # ⚠️ CURRENTLY DISABLED
    "cot_max_tokens_think": 600,       # Max tokens cho THINK phase
    "cot_max_tokens_decide": 300,      # Max tokens cho DECIDE phase
}
```

### **Environment Variables**

```bash
# API Configuration
LLM_MODEL_NAME=SaoLa-Llama3.1-planner
LLM_BASE_URL=https://mkp-api.fptcloud.com
LLM_MODEL_API=https://mkp-api.fptcloud.com/v1/chat/completions
LLM_API_KEY=sk-jlkMWMnKhhu6j3pBcOmhASGV7Ls_FYKVM-Ac1DmCKpA=
```

---

## 🚀 Lệnh Chạy Hiện Tại

### **Lệnh Chính**

```bash
# Chạy pipeline chấm thi với 4 hệ thống khác nhau
python pipeline.py

# Chạy report hiển thị kết quả
python report.py [grading_results.json] [sample_parem.json] [test_input.json]
```

### **Lệnh Chi Tiết - Compare Systems**

```bash
# Compare các hệ thống
python compare_systems.py

# Run với test input perfect (100% đúng)
python pipeline.py --test-file test_input_perfect.json

# Run với specific system
python pipeline.py --system 3  # Chỉ chạy System 3 (Pure LLM)
```

### **Kích Hoạt CoT**

```python
# Sửa trong pipeline.py hoặc set env var:
os.environ["USE_COT"] = "true"

# Hoặc sửa file directly:
CFG["use_chain_of_thought"] = True
CFG["cot_max_tokens_think"] = 800    # Tăng tokens nếu cần
CFG["cot_max_tokens_decide"] = 400
```

### **Run Specific System**

```bash
# System 1: Heuristic Only (baseline)
python -c "from pipeline import grade_sample; print(grade_sample(sample_1, barem_dict))"

# System 2: Hybrid (Heuristic + LLM)
python -c "from pipeline import grade_sample_hybrid; print(grade_sample_hybrid(sample_2, barem_dict))"

# System 3: Pure LLM
python -c "from pipeline import grade_sample_pure_llm; print(grade_sample_pure_llm(sample_3, barem_dict))"

# System 4: LLM + Advisory
python -c "from pipeline import grade_sample_advised; print(grade_sample_advised(sample_4, barem_dict))"
```

### **Testing & Validation**

```bash
# Run với sample perfect
python report.py grading_results_s1.json sample_parem.json test_input_perfect.json

# Run với sample incomplete
python report.py grading_results_s2.json sample_parem.json test_input.json

# Generate report với MAE
python report.py grading_results_s3.json sample_parem.json test_input.json 2>&1 | tee report.txt
```

---

## 📊 Prompt Flow Diagram

```
┌─────────────────────────────────────────────────────┐
│                  Input Sample                        │
│  (question, student_answer, max_score, criteria)    │
└──────────────────┬──────────────────────────────────┘
                   ↓
         ┌─────────────────────┐
         │   Route Question    │
         │  Type (Heuristic +  │
         │   Parem Lookup)     │
         └─────────┬───────────┘
                   ↓
          ┌────────────────────┐
          │ For each Criterion │
          └────────┬───────────┘
                   ↓
       ┌───────────────────────────┐
       │  Infer Grading Mode       │
       │  (expected_output /       │
       │   expected_value /        │
       │   table / visual / llm)   │
       └─────────┬─────────────────┘
                 ↓
         ┌───────────────────┐
         │   Mode = "llm"?   │
         └────┬──────────┬───┘
         YES  │          │  NO
             ↓          ↓
    ┌───────────────┐  ┌─────────────────┐
    │ grade_with_   │  │ grade_criterion │
    │ llm_cot()     │  │ (heuristic)     │
    └────┬──────────┘  └────────┬────────┘
         │                      │
         │  ┌──────────────────┘
         └─→│
            ↓
    ┌──────────────────┐
    │  call_llm_cot()  │
    └────┬──────────┬──┘
         │          │
    THINK│          │DECIDE
    Ph1  │          │Ph2
         ↓          ↓
    ┌──────────┐  ┌─────────┐
    │ temp=0.2 │  │ temp=0  │
    │ 600 tok  │  │ 300 tok │
    │ FREE     │  │ JSON    │
    │ TEXT     │  │ ONLY    │
    └────┬─────┘  └────┬────┘
         │             │
         └──→ Parse cot_reasoning
             ├─ score
             ├─ status
             ├─ confidence
             └─ reasoning
                 ↓
         ┌──────────────────┐
         │  Aggregate Scores│
         │  per Question    │
         └────────┬─────────┘
                  ↓
         ┌──────────────────┐
         │  Output Results  │
         │ grading_results  │
         │ _s1/s2/s3/s4.json│
         └──────────────────┘
```

---

## 📚 Tài Liệu Liên Quan

- **LLM_PROMPT_FLOW.md** - Chi tiết luồng từng hàm
- **LLM_PROMPT_FLOW_QUICKREF.md** - Tham chiếu nhanh
- **LLM_PROMPT_FLOW_DETAILED.md** - Mở rộng toàn bộ
- **COT_IMPLEMENTATION_REPORT.md** - Báo cáo kết quả CoT
- **PIPELINE_EXECUTION_FLOW.md** - Chi tiết thực thi

---

## 🔗 Key Functions Map

| Hàm | Vị Trí | Tác Dụng | Phương Pháp |
|-----|--------|---------|-----------|
| `call_llm_json()` | L325 | Gọi LLM 1 lần | Direct JSON |
| `call_llm_cot()` | L1246 | Gọi LLM 2 lần | Chain-of-Thought |
| `grade_criterion()` | L1200+ | Lựa chọn mode chấm | Orchestrator |
| `grade_with_llm_cot()` | L1426 | Chấm bằng CoT LLM | CoT Flow |
| `grade_with_llm_advised()` | L1989 | Chấm LLM + Advisory | Advisory Flow |
| `grade_sample_hybrid()` | L1800+ | System 2 | Hybrid |
| `grade_sample_pure_llm()` | L1850+ | System 3 | Pure LLM |
| `grade_sample_advised()` | L1900+ | System 4 | LLM+Advisory |

---

## 💡 Tips & Best Practices

### ✅ Khi Nên Dùng CoT
- Chấm essay, short answer
- Yêu cầu reasoning complex
- Bài toán có nhiều tiêu chí
- Cần explainability cao

### ❌ Khi KHÔNG Nên Dùng CoT
- Output có sẵn (token matching)
- Regex pattern matching đơn giản
- Đơn giản lookup (expected_value)
- Cần speed cao, tokens ít

### 🎯 Tối Ưu Prompting
1. **Clarity First** - Tiêu chí phải rõ ràng
2. **Context Matters** - Cung cấp full context
3. **Structure Helps** - JSON schema giúp parse
4. **Temperature Balance** - Think=0.2, Decide=0
5. **Token Budget** - Think=600, Decide=300 là cân bằng

---

**Last Updated:** June 1, 2026  
**Generated By:** GitHub Copilot v4.5
