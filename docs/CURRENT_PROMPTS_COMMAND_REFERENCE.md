# 🎯 Lệnh Prompt Hiện Tại - Quick Reference

**Hệ Thống:** Multi-Format Rubric-based Grading Pipeline  
**Ngày:** June 1, 2026  
**Status:** CoT DISABLED (use_chain_of_thought = False)

---

## 📍 Lệnh Chạy Hiện Tại

### **1. Pipeline Chấm (Chạy Tất Cả 4 Hệ Thống)**

```bash
python pipeline.py
```

**Output:**
- `grading_results_s1.json` (System 1: Heuristic)
- `grading_results_s2.json` (System 2: Hybrid)
- `grading_results_s3.json` (System 3: Pure LLM)
- `grading_results_s4.json` (System 4: LLM+Advisory)

---

### **2. Hiển Thị Kết Quả**

```bash
python report.py grading_results_s3.json sample_parem.json test_input.json
```

**Format Output:**
- Bảng kết quả màu sắc
- Tính MAE (Mean Absolute Error)
- Hiện Groundtruth từ sample_parem.json
- So sánh predicted vs expected

---

### **3. So Sánh Các Hệ Thống**

```bash
python compare_systems.py
```

**So Sánh:**
- System 1 vs 2 vs 3 vs 4
- Chỉ số: Accuracy, MAE, F1, Precision, Recall

---

## 🔧 Cấu Hình Hiện Tại (CFG)

### **Trạng Thái CoT**

```python
CFG["use_chain_of_thought"] = False  # ⚠️ HIỆN ĐANG TẮT

# Để bật CoT:
CFG["use_chain_of_thought"] = True
CFG["cot_max_tokens_think"] = 600
CFG["cot_max_tokens_decide"] = 300
```

### **Model API**

```python
{
    "model": "SaoLa-Llama3.1-planner",
    "base_url": "https://mkp-api.fptcloud.com",
    "model_api": "https://mkp-api.fptcloud.com/v1/chat/completions",
    "api_key": "sk-jlkMWMnKhhu6j3pBcOmhASGV7Ls_FYKVM-Ac1DmCKpA=",
}
```

---

## 📝 Prompt Hiện Tại Được Sử Dụng

### **Khi CoT = False (Hiện Tại)**

```python
# System 2 & 4 fallback về grade_with_llm() 
# → Gọi heuristic trước
# → Nếu confidence < 0.6 → gọi LLM

# System 3 gọi trực tiếp:
result = grade_with_llm(sample, criterion)
    ↓
if CFG["use_chain_of_thought"]:
    call_llm_cot()  # 2 API calls
else:
    # Hiện tại: dùng call_llm_json() (1 API call)
    call_llm_json(prompt)  # Trực tiếp JSON
```

### **Prompt Direct JSON (Hiện Tại - CoT Disabled)**

```python
# Gọi hàm:
call_llm_json(
    prompt=f"""Bạn là một giáo viên chấm thi lập trình.
    
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

Chấm điểm. Trả về JSON:
{{
  "score": <số thực 0-{max_score}>,
  "status": "<correct|partially_correct|wrong>",
  "reasoning": "<ngắn gọn>"
}}""",
    schema_name="grading",
    retries=3
)
```

**Cấu Hình:**
- Temperature: 0
- Max Tokens: default (không giới hạn)
- Timeout: 120 giây
- API Calls: 1 lần duy nhất

---

### **Khi Bật CoT (use_chain_of_thought = True)**

#### **Phase 1: THINK**

```python
think_prompt = f"""Bạn là một giáo viên chấm thi lập trình đang phân tích bài làm.
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
5. Kết luận sơ bộ: điểm dự kiến và lý do?"""

# API Call 1:
payload_think = {
    "model": "SaoLa-Llama3.1-planner",
    "messages": [
        {
            "role": "system",
            "content": "Bạn là giáo viên chấm thi. Hãy suy luận chi tiết bằng tiếng Việt."
        },
        {"role": "user", "content": think_prompt}
    ],
    "temperature": 0.2,      # ← Cho phép sáng tạo
    "max_tokens": 600        # ← Đủ để suy luận chi tiết
}

resp = requests.post(model_api, headers=headers, json=payload_think)
cot_reasoning = resp.json()["choices"][0]["message"]["content"]
```

**Settings:**
- Temperature: 0.2 (Hơi sáng tạo, không deterministic)
- Max Tokens: 600
- Output: Free-form text reasoning

---

#### **Phase 2: DECIDE**

```python
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
  "confidence": <số thực từ 0.0 đến 1.0>
}}"""

# API Call 2:
payload_decide = {
    "model": "SaoLa-Llama3.1-planner",
    "messages": [
        {
            "role": "system",
            "content": "You are a grading assistant. Based on the reasoning provided, output ONLY a valid JSON object. No markdown, no explanation outside the JSON."
        },
        {"role": "user", "content": decide_prompt}
    ],
    "temperature": 0,        # ← Hoàn toàn deterministic
    "max_tokens": 300        # ← Đủ cho JSON
}

resp = requests.post(model_api, headers=headers, json=payload_decide)
decide_text = resp.json()["choices"][0]["message"]["content"]
parsed = json.loads(decide_text)  # Parse JSON
result = {
    "cot_reasoning": cot_reasoning,
    "score": parsed["score"],
    "status": parsed["status"],
    "reasoning": parsed["reasoning"],
    "confidence": parsed["confidence"],
    "cot_used": True
}
```

**Settings:**
- Temperature: 0 (Hoàn toàn deterministic)
- Max Tokens: 300
- Output: Structured JSON

---

## 📊 So Sánh: Direct JSON vs CoT

| Khía Cạnh | Direct JSON | CoT (2 Phases) |
|-----------|-----------|----------------|
| **API Calls** | 1 | 2 |
| **Temperatures** | 0 (fixed) | 0.2, 0 |
| **Max Tokens** | default | 600 + 300 = 900 |
| **Cost** | Thấp | Cao (2x) |
| **Accuracy** | ~83-87% | ~90%+ |
| **Reasoning** | None | Detailed (cot_reasoning) |
| **Khi Nên Dùng** | Output đơn giản | Complex grading |
| **Status** | **HIỆN DÙNG** | **ĐỀ XUẤT BẬT** |

---

## 🚀 Để Bật CoT (Hiện Tại Đang Tắt)

### **Cách 1: Sửa File**

Mở `pipeline.py` line 39:

```python
# Từ:
"use_chain_of_thought": False,

# Thành:
"use_chain_of_thought": True,
```

Sau đó chạy lại:
```bash
python pipeline.py
```

### **Cách 2: Set Environment Variable**

```bash
# Linux/Mac
export LLM_USE_COT=true
python pipeline.py

# Windows PowerShell
$env:LLM_USE_COT="true"
python pipeline.py

# Windows CMD
set LLM_USE_COT=true
python pipeline.py
```

### **Cách 3: Sửa CFG trong Code**

```python
# Tại đầu pipeline.py hoặc trước grade_sample():
CFG["use_chain_of_thought"] = True
CFG["cot_max_tokens_think"] = 800  # Tăng nếu cần chi tiết hơn
CFG["cot_max_tokens_decide"] = 400

# Sau đó chạy:
python pipeline.py
```

---

## 📈 Impact Khi Bật CoT

**Từ Test Report:**

| System | Trước CoT | Sau CoT | Thay Đổi |
|--------|----------|---------|---------|
| S2 (Hybrid) | 82.1% | 83.1% | +1.0% ✅ |
| S3 (Pure LLM) | 90.7% | 90.8% | +0.1% ✅ |
| S4 (Advisory) | 87.8% | 81.4% | -6.4% ⚠️ |

**Ghi Chú:**
- S4 variance cao vì LLM response không deterministic
- Re-run có thể khác kết quả
- CoT giúp S2 & S3 ổn định hơn

---

## 🔍 Debugging: Xem Prompt Thực Tế

### **Lưu Prompt ra File**

Sửa hàm `call_llm_cot()` để log:

```python
# Thêm sau line 1294:
with open("debug_think_prompt.txt", "w", encoding="utf-8") as f:
    f.write(think_prompt)
print(f"✅ THINK prompt saved: debug_think_prompt.txt")

# Thêm sau line 1359:
with open("debug_decide_prompt.txt", "w", encoding="utf-8") as f:
    f.write(decide_prompt)
print(f"✅ DECIDE prompt saved: debug_decide_prompt.txt")
```

Chạy lại:
```bash
python pipeline.py
cat debug_think_prompt.txt
cat debug_decide_prompt.txt
```

### **Xem Response từ LLM**

```python
# Thêm trong call_llm_cot():
print(f"=== THINK Response ===\n{cot_reasoning}\n")
print(f"=== DECIDE Response ===\n{decide_text}\n")
```

---

## 💾 File Tham Chiếu

| File | Nội Dung |
|------|---------|
| **pipeline.py** | Code chính, hàm LLM, prompts |
| **PROMPTING_TECHNIQUES_AND_METHODS.md** | (**NEW**) Tài liệu chi tiết prompting |
| **LLM_PROMPT_FLOW.md** | Luồng từng hàm |
| **LLM_PROMPT_FLOW_QUICKREF.md** | Tham chiếu nhanh |
| **COT_IMPLEMENTATION_REPORT.md** | Báo cáo kết quả CoT |
| **report.py** | Hiển thị kết quả |
| **compare_systems.py** | So sánh S1-S4 |

---

## ⚡ Quick Command Cheat Sheet

```bash
# Chạy chấm tất cả hệ thống
python pipeline.py

# Xem kết quả System 3 (Pure LLM)
python report.py grading_results_s3.json sample_parem.json test_input.json

# So sánh tất cả hệ thống
python compare_systems.py

# Chạy với test input perfect
python pipeline.py test_input_perfect.json

# Xem prompt đang dùng
grep -n "THINK\|DECIDE" pipeline.py | head -20
```

---

**Last Updated:** June 1, 2026  
**Status:** ⚠️ CoT Currently Disabled (use_chain_of_thought = False)  
**Recommendation:** 🟢 Enable CoT for better accuracy (+1% on S2/S3)
