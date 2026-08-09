# Schema `heuristic_result` theo từng grader

Bốn heuristic grader được `grade_criterion()` (heuristic router) dispatch tới theo `question_type`. Mỗi grader trả về một dict `heuristic_result` — dict này sau đó được đưa vào llm-router (`grade_criterion_with_llm()`) làm advisory cho LLM. Matching/Logical/Table đi qua blend heuristic+LLM bình thường; Table cụ thể còn được **gom theo part, chấm cả nhóm 1 lần gọi LLM** (`grade_table_group_with_llm`, xem mục 6); Visual bypass hoàn toàn phần blend (xem mục 4).

Cột **Value** liệt kê **toàn bộ tập giá trị có thể có** của field đó (enum thật), không phải chỉ 1 ví dụ. Với field tự do (string nội dung, dict evidence...) sẽ ghi rõ là "chuỗi/dict tự do".

---

## 1. Matching — `grade_expected_output_criterion`

Tất cả các nhánh đều build qua `_build_output_criterion_result`, nên field set giống nhau, chỉ khác **giá trị**.

| Field | Kiểu | Value (toàn bộ giá trị có thể) |
|---|---|---|
| `criterion_id` | `str` | chuỗi tự do (ID khai báo trong barem) |
| `part_label` | `str` | chuỗi tự do (VD `"a"`, `"b"`, `"main"`) |
| `criterion_content` | `str` | chuỗi tự do (nội dung câu hỏi trong barem) |
| `score` | `float` | `0` \| `max_score` (nhánh exact match) — hoặc `0 ≤ score ≤ max_score` theo tỷ lệ token/`partial_credit_rule` |
| `max_score` | `float` | số cố định khai báo trong barem cho criterion đó |
| `status` | `str` | `"correct"` \| `"partially_correct"` \| `"wrong"` \| `"needs_teacher_review"` |
| `reason` | `Optional[str]` | chuỗi mô tả tùy nhánh, hoặc `None` |
| `evidence` | `dict` | dict tự do: `student_answer` (nguyên văn học sinh viết), `tokens`, `tables`, `visual_answers`, `part_label`, `type`, `found`, `is_blank`... |
| `expected_outputs` | `List[str]` | list từ barem (đã resolve conditional nếu có) — `[]` ở nhánh `force_wrong` |
| `conditioning` | `dict` | xem cấu trúc chi tiết ở mục 1b |
| `detected_errors` | `List[dict]` | `[]` \| `[{"error_type": "wrong_output_token", "index", "token_index", "expected", "student", "message"}, ...]` |
| `expected_output_tokens` | `Optional[List[str]]` | list từ barem \| `None`/không có key |
| `student_tokens` | `Optional[List[Optional[str]]]` | mỗi phần tử: token khớp được (`str`, bằng đúng `expected_output_tokens[i]`) \| `None` (không tìm thấy) |
| `teacher_review_required` | `bool` | `True` (**chỉ** nhánh "không khớp gì") \| `False`/không có key (nhánh khác) |

> Không có field `is_correct`/`exact_match` — cả 2 đã bị bỏ hẳn (xem mục 7), `status` là nguồn thông tin duy nhất.

**3 nhánh cụ thể** quyết định tổ hợp giá trị trên:

- **Khớp chính xác tuyệt đối** (`_check_exact_output_match`) → `score=max_score`, `status="correct"`.
- **Không khớp tuyệt đối nhưng có `expected_output_tokens`** → chấm theo token/`partial_credit_rule` (`_grade_by_tokens`) → `score` theo tỷ lệ, `status="partially_correct"|"wrong"` — **không bao giờ `"correct"`**, kể cả khớp 100% token, vì đây là matching lỏng (position-tolerant), không phải exact match. **Quyết định thiết kế đã chốt, không sửa lại** — `status="correct"` chỉ dành riêng cho nhánh khớp tuyệt đối.
- **`force_wrong`** (self_reported slot rỗng) → `score=0`, `status="wrong"`, `expected_outputs=[]`.
- **Không khớp gì, không có token** → `score=0`, `status="needs_teacher_review"`, `teacher_review_required=True`.

### 1b. `conditioning` — thay cho `conditional_resolved`/`conditional_reason`

Luôn có mặt trong kết quả Matching, kể cả khi criterion không phải dạng điều kiện — để nơi đọc không phải tự check field có tồn tại hay không:

```
"conditioning": {
    "has_conditional": bool,        # criterion có conditional_outputs không
    "conditional_type": "sample_field" | "self_reported" | None,   # từ condition_source.get("type"); None nếu has_conditional=False
    "heuristic_conditional_define": {   # None nếu has_conditional=False
        "matched": bool,             # có case nào trong conditional_outputs khớp value không
        "expected_outputs": [...],
        "expected_output_tokens": [...],
        "reason": str,
    } | None,
}
```

Ví dụ thật (criterion `T3_main_s2`, `self_reported`, học sinh tự ghi STT=23):
```json
{
  "has_conditional": true,
  "conditional_type": "self_reported",
  "heuristic_conditional_define": {
    "matched": true,
    "expected_outputs": ["57918"],
    "expected_output_tokens": ["5", "7", "9", "18"],
    "reason": "Matched condition: 'value % 4 == 3' with value=23"
  }
}
```

---

## 2. Logical — `grade_expected_value_criterion`

Luôn cùng 1 schema, **không có branch điểm thật**:

| Field | Kiểu | Value (toàn bộ giá trị có thể) |
|---|---|---|
| `criterion_id` | `str` | chuỗi tự do |
| `part_label` | `str` | chuỗi tự do |
| `criterion_content` | `str` | chuỗi tự do |
| `score` | `float` | **hằng số `0`** (không có nhánh nào khác) |
| `max_score` | `float` | số từ barem |
| `status` | `str` | **hằng số `"needs_teacher_review"`** |
| `matched` | `List[dict]` | `[{"value": Any}, ...]` — 1 entry / keyword khớp (không còn `"key"` — xem ghi chú dưới) |
| `missing` | `List[dict]` | `[{"value": Any}, ...]` — 1 entry / keyword không khớp |
| `evidence` | `dict` | dict tự do, có `evidence["student_answer"]` |
| `reason` | `str` | `"Found:x/y expected keywords found: ..."` \| `"No expected_value provided."` |
| `teacher_review_required` | `bool` | **hằng số `True`** |
| `detected_errors` | `List[dict]` | `[]` \| `[{"error_type": "missing_expected_value", "expected", "message": "Không tìm thấy: {value}."}, ...]` |

> Không có field `is_correct` (đã bỏ hẳn). Nhánh sớm nhất — không có `expected_value` khai báo — thiếu hẳn `matched`/`missing`/`evidence`.

> **`expected_value` giờ chỉ có đúng 2 key khả dụng cho Logical**: `"keywords"` (`List[str]`, mỗi phần tử quét riêng qua `value_matches_student_text`) và `"sample_solution"` (code mẫu, KHÔNG bị quét — chỉ hiện cho LLM qua khối `"══ ĐÁP ÁN / LOGIC KỲ VỌNG ══"` riêng). Trước đây `grade_expected_value_criterion` loop qua **mọi key tùy ý** trong `expected_value` (VD `function`, `logic`, `struct_name`, `comparison`...) và giữ tên key trong `matched`/`missing` (`{"key": ..., "value": ...}`) — đã bỏ hẳn, giờ chỉ quét list `keywords`, nên entry không còn `"key"`, chỉ còn `"value"`.

---

## 3. Table — `grade_table_criterion` / `grade_table_row_criterion`

**Đã đại tu hoàn toàn** — không còn `column_map`, không còn nhánh "delegate" (gộp cả bảng thành 1 chuỗi rồi chấm như Matching/Logical), không còn `matched`/`missing`. Mỗi criterion giờ chỉ kiểm **đúng 1 ô** (`row_id` + `col_id`), và **heuristic không còn tự quyết đúng/sai bằng so khớp `expected_value`** — `expected_value` chỉ là 1 **ví dụ gợi ý** (VD đề "Tìm 3 ví dụ cho bài toán" chấp nhận bất kỳ cặp Input/Output nào đúng logic, không bắt buộc khớp y hệt mẫu) — so khớp cứng sẽ chấm sai oan mọi ví dụ hợp lệ khác.

2 nhánh:

**a) Không có bảng nào** → schema tối giản, mọi giá trị hằng số:

| Field | Value |
|---|---|
| `score` | `0` |
| `status` | `"wrong"` |
| `reason` | `"No table answer found."` |
| `detected_errors` | `[{"error_type": "missing_table_answer", "message"}]` |

**b) Có `row_id` + `col_id` + `expected_value`** → `grade_table_row_criterion`, 2 nhánh con:

| | Ô bị bỏ trống | Ô có nội dung |
|---|---|---|
| `score` | `0` | `0` (luôn — không phải điểm thật) |
| `status` | `"wrong"` (dứt khoát) | `"needs_teacher_review"` (luôn — kể cả khi khớp y hệt gợi ý mẫu) |
| `reason` | `"Ô {row_id}{col_id} bị bỏ trống."` | `"Học sinh viết '{cell_text}' tại {row_id}{col_id} (gợi ý mẫu: {expected_value!r}) — cần LLM verify logic, không so khớp cứng."` |
| `student_cell_text` | *(không có field này)* | `str` — nguyên văn học sinh viết ở đúng ô đó |
| `teacher_review_required` | *(không có)* | `True` |
| `detected_errors` | `[{"error_type": "blank_cell", "row_id", "col_id", "message"}]` | `[]` |

| Field chung (cả 2 nhánh) | Kiểu | Value |
|---|---|---|
| `criterion_id`, `part_label`, `criterion_content` | | chuỗi tự do |
| `max_score` | `float` | số từ barem |
| `row_id` | `str` | chuỗi từ barem (VD `"R3"`) |
| `col_id` | `str` | chuỗi từ barem (VD `"C1"`) |
| `evidence` | `dict` | dict tự do |

**c) Thiếu `row_id`/`col_id`/`expected_value`** (barem cấu hình thiếu) → `status="needs_teacher_review"`, `error_type="incomplete_table_criterion"` — không đoán mò, không còn nhánh gộp-toàn-bảng để fallback nữa.

> **Field đã bỏ hoàn toàn khỏi Table** so với bản trước: `is_correct`, `matched`, `missing`, `student_table_text`, `column_map` (input), `token_evaluations`. Xem mục 7 lý do.

---

## 4. Visual — `grade_visual_criterion`

4 nhánh, **field set khác nhau nhiều nhất**. Đây là grader duy nhất **bypass** phần blend LLM/heuristic (qua `grade_visual_with_llm`, chỉ chuẩn hóa vài field mặc định) — kết quả trả về là **final**, không có `heuristic_score`/`llm_score` tách biệt. Đây cũng là grader **duy nhất còn giữ `is_correct`/`teacher_review_required`** — vì cả 2 tính độc lập từ giá trị thật (`score >= max_score`, `confidence < threshold`), không trùng lặp với `status` như 3 grader kia.

**a) Không có `visual_answers`** — mọi giá trị hằng số:

| Field | Value |
|---|---|
| `score` | `0` |
| `status` | `"wrong"` |
| `is_correct` | `False` |
| `reason` | `"No visual answer found."` |
| `teacher_review_required` | `True` |
| `detected_errors` | `[{"error_type": "missing_visual_answer", "message"}]` |

**b) Có visual nhưng thiếu `image_path`** → thêm `visual_answers` (`List[dict]`), `status="needs_vision_teacher_review"` (hằng số ở nhánh này).

**c) Vision LLM lỗi** → thêm `visual_answers`, `status="needs_vision_teacher_review"`, `detected_errors=[{"error_type": "vision_llm_error", "message": str}]`.

**d) Thành công**:

| Field | Kiểu | Value (toàn bộ giá trị có thể) |
|---|---|---|
| `criterion_id`, `part_label`, `criterion_content` | | chuỗi tự do |
| `score` | `float` | `0 ≤ score ≤ max_score`, do Vision LLM tự chấm |
| `status` | `str` | theo Vision LLM trả về nguyên văn — **không được validate/ép về enum cố định** như stage 2 text-LLM (không có cơ chế `status_corrected` ở đây), thực tế thường là `"correct"`\|`"partially_correct"`\|`"wrong"` nhưng về lý thuyết có thể là chuỗi bất kỳ nếu LLM hallucinate |
| `is_correct` | `bool` | `True` (`score >= max_score`) \| `False` — lưu ý dùng `>=`, không phải `==` |
| `reason` | `str` | chuỗi tự do (= `reasoning` từ Vision LLM) |
| `confidence` | `float` | `0.0 ≤ confidence ≤ 1.0` |
| `vision_llm_used` | `bool` | **hằng số `True`** |
| `image_path` | `str` | đường dẫn ảnh, chuỗi tự do |
| `visual_answers` | `List[dict]` | list evidence gốc |
| `teacher_review_required` | `bool` | `True` nếu `confidence < CFG["teacher_review_threshold"]` (mặc định `0.65`) \| `False` |
| `detected_errors` | `List[dict]` | **hằng số `[]`** |

---

## 5. So sánh field giữa 4 grader

### Field chung cho cả 4 (mọi nhánh, mọi grader)

```
criterion_id, part_label, criterion_content, score, max_score,
status, reason, detected_errors
```

### Field chung cho 3 grader text (Matching / Logical / Table), KHÔNG có ở Visual

| Field | Ghi chú |
|---|---|
| `evidence` | dict tự do, có key `student_answer` (nguyên văn học sinh viết). Visual dùng `visual_answers` riêng, không có `evidence` |

### Field chỉ riêng của từng grader

| Grader | Field riêng | Value |
|---|---|---|
| **Matching** | `expected_outputs`, `expected_output_tokens`, `student_tokens`, `conditioning` | xem bảng mục 1 |
| **Logical** | `matched`, `missing` | xem bảng mục 2 |
| **Table** | `row_id`, `col_id`, `student_cell_text` (chỉ nhánh có nội dung) | xem bảng mục 3 |
| **Visual** | `confidence` (`0.0–1.0`), `vision_llm_used` (hằng số `True`), `image_path` (chuỗi), `visual_answers` (list), `is_correct`, `teacher_review_required` (độc lập thật, không trùng `status`) | xem bảng mục 4 |

### Field trùng tên nhưng ý nghĩa/nguồn gốc khác nhau

| Field | Value ở mỗi nơi | Khác biệt |
|---|---|---|
| `teacher_review_required` | Logical: **hằng số `True`**. Matching: `True` chỉ ở nhánh "không khớp gì". Table: `True` chỉ ở nhánh "có nội dung nhưng chưa xác định" (không có ở nhánh bỏ trống/không có bảng). Visual: `True`/`False` theo `confidence` threshold — **độc lập thật**, không suy ra được từ `status` như 3 grader kia | Ở Matching/Logical/Table field này 100% derivable từ `status` (`status in TRANSIENT_REVIEW_STATUSES`); ở Visual thì không |
| `confidence` | Visual: `0.0–1.0` (giá trị thật từ Vision LLM). Matching/Logical/Table: **field không tồn tại** trong `heuristic_result` | Chỉ Visual set `confidence` ngay ở heuristic; 3 grader kia chỉ có `confidence` sau khi qua LLM ở stage 2 |
| `is_correct` | Chỉ còn ở Visual (độc lập thật). Matching/Logical/Table: **đã bỏ hẳn**, dùng `status` thay | Xem mục 7 |

### Field chỉ tồn tại sau stage 2 (llm-router — `grade_criterion_with_llm` / `_grade_with_llm_advised_core` / `grade_table_group_with_llm`)

| Field | Value (toàn bộ giá trị có thể) |
|---|---|
| `stage` | `"heuristic"` \| `"llm"` \| `"llm_failed"` |
| `grading_method` | `"llm_advised_cot"` \| `"llm_advised_simple"` \| `"llm_table_batch_cot"` \| `"heuristic_llm_failed"` \| `"heuristic_exception"` \| `"blank_skip"` \| `"vision_llm"` |
| `llm_score` | `0 ≤ llm_score ≤ max_score` |
| `llm_status` | `"correct"` \| `"partially_correct"` \| `"wrong"` (đã validate qua `_VALID_LLM_STATUSES`, tự suy ra từ score nếu LLM trả giá trị lạ) |
| `llm_reasoning` | chuỗi tự do |
| `cot_reasoning` | chuỗi tự do (rỗng `""` nếu dùng chế độ simple, không CoT; ở table-batch là 1 đoạn CoT DÙNG CHUNG cho cả nhóm criterion) |
| `heuristic_score` | `0 ≤ heuristic_score ≤ max_score` (đúng bằng `score` gốc của heuristic) |
| `heuristic_status` | bất kỳ giá trị status nào mà heuristic của grader đó có thể trả (xem mục 1–4) |
| `heuristic_weight` | `0.0 ≤ heuristic_weight ≤ 1.0` (mặc định `CFG["heuristic_weight"]=0.5`, áp dụng đều cho mọi criterion, kể cả trong table-batch) |
| `agreed_with_heuristic` | `True` \| `False` (không có ở kết quả table-batch) |
| `status_corrected` | `True` \| `False` |
| `token_usage` | `{"prompt_tokens": int/float, "completion_tokens": int/float, "total_tokens": int/float}` — ở table-batch là **số thực** (chia đều token của 1 lần gọi LLM chung cho N criterion trong nhóm) |

> Visual là ngoại lệ — vì bypass stage 2, các field `vision_llm_used`/`image_path`/`confidence` đã có sẵn ngay từ `heuristic_result`, không cần đợi stage 2 mới xuất hiện.

---

## 6. Table batch grading — `grade_table_group_with_llm` / `call_llm_table_batch`

### 6a. Vì sao cần gom theo bảng

LLM chấm Table theo **cả nhóm criterion cùng 1 bảng, đúng 1 lần gọi LLM** — không phải mỗi ô/mỗi criterion tự gọi LLM riêng. Lý do: nếu chấm tách rời từng ô, LLM không bao giờ thấy được **quan hệ giữa các ô cùng hàng** (VD Input↔Output phải khớp logic toán học của bài toán) — mỗi lần gọi chỉ thấy đúng 1 ô, hoàn toàn cô lập.

### 6b. Ai gọi hàm này

Không phải `grade_criterion_with_llm` (đường 1-criterion) gọi — mà **`run_part`** (tầng batch runner) tự nhận diện: trong 1 part, criterion nào `question_type=="table"` thì gom hết lại, gọi `grade_table_group_with_llm(routed_sample, table_criteria)` **1 lần cho cả nhóm**, thay vì loop gọi `grade_criterion_advised` cho từng cái.

```
run_part (1 part của 1 câu)
  ├─ table_criteria = [c for c in part_criteria if question_type=="table"]
  ├─ other_criteria = phần còn lại
  ├─ other_criteria → grade_criterion_advised() từng cái (như cũ)
  └─ table_criteria (nếu có) → grade_table_group_with_llm() 1 LẦN cho cả nhóm
```

### 6c. Luồng bên trong `grade_table_group_with_llm`

1. Chạy `grade_table_criterion` heuristic riêng cho **từng** criterion trong nhóm (advisory, xem mục 3).
2. Nếu **toàn bộ** ô trong bảng đều rỗng → trả `status="wrong"`, `grading_method="blank_skip"` cho cả nhóm, **không gọi LLM**.
3. Build `table_text` — toàn bộ nội dung bảng, mỗi dòng 1 ô (`cell_id: text`):
   - Nếu criterion có `table_slot` (barem đính kèm qua `_attach_table_slots`, từ `question.parts[].tables[].table_slot`) → dùng khung `table_slot` đầy đủ (gồm cả ô `source:"printed"` — header, giá trị in sẵn) + tra giá trị thật cho ô `source:"student_text"` từ `evidence.tables`.
   - Không có `table_slot` → fallback dump thẳng `evidence.tables` (chỉ có ô học sinh viết, THIẾU ô in sẵn/header).
4. Gọi `call_llm_table_batch(table_text, criteria_specs)` — **đúng 1 "vòng" gọi LLM** (2 request HTTP: THINK rồi DECIDE, xem 6d) cho cả nhóm.
5. Với mỗi criterion: `_blend_heuristic_and_llm(h_score, llm_entry.score, llm_entry.status, max_score)` — **cùng công thức blend** với đường đơn-criterion (`_grade_with_llm_advised_core`), chỉ khác nguồn `llm_score` lấy từ response gộp thay vì gọi riêng.
6. LLM lỗi cả nhóm → mỗi criterion fallback **độc lập** về heuristic của chính nó (`heuristic_llm_failed`, ép `status="wrong"` nếu heuristic đang transient — giống hệt logic fallback đường đơn-criterion).

### 6d. `call_llm_table_batch` — 2 bước THINK/DECIDE (CoT)

Giống cấu trúc `_cot_single_pass` (dùng cho criterion đơn), áp dụng cho cả nhóm:
- **THINK**: LLM suy luận tự do, lần lượt qua từng `criterion_id` — đọc vị trí + đáp án gợi ý, đối chiếu giá trị thật, kiểm tra quan hệ với ô liên quan cùng hàng, kết luận sơ bộ.
- **DECIDE**: dựa trên đoạn suy luận ở bước THINK, trả JSON — 1 entry / `criterion_id`: `{"score", "status", "reasoning"}`.
- **Khác `call_llm_cot`**: không có self-consistency vote (giữ đơn giản, vì đã gộp nhiều criterion/lần gọi rồi).
- Token usage cộng cả 2 bước (think+decide), rồi `grade_table_group_with_llm` chia đều cho N criterion trong nhóm.

### 6e. 🔴 Bug đã biết, CHƯA fix: `max_score=0` khiến mọi kết quả batch luôn báo `"correct"`

Đường **tính điểm thật** (vòng lặp blend cuối `grade_table_group_with_llm`) lấy `max_score = c.get("score", 0)` — nhưng criterion Table 1-ô (VD `T15B1..T15B5`) **không có field `"score"` riêng** (chỉ có `"weight"`, vì điểm thật chỉ cấp ở cấp nhóm `all_or_nothing` cha) → `max_score` luôn là `0`. Trong `_blend_heuristic_and_llm`, `llm_score = clamp_score(x, 0, 0)` → luôn ép về `0`; rồi `status = "correct" if score == max_score else ...` — vì cả `score` và `max_score` đều `0`, biểu thức `0 == 0` **luôn đúng** → **mọi criterion trong nhóm batch luôn báo `status="correct"`**, bất kể LLM/heuristic thực sự nói gì. **Bug này chưa fix.**

Đã tái hiện thật: cho LLM trả lời rõ ràng 1 criterion là `"wrong"` (kèm giải thích đúng) — kết quả cuối vẫn ra `status="correct"`. Nhóm `all_or_nothing` (VD `T15B`) vì vậy có thể cho **trọn điểm oan** dù có ô sai thật.

> **Đã fix riêng phần hiển thị prompt** (không phải bug trên): `criteria_specs["max_score"]` — copy riêng chỉ dùng để build prompt (`call_llm_table_batch`), **không** phải giá trị dùng tính điểm ở trên — giờ là `c.get("score")` (không default) thay vì `c.get("score", 0)`, nên với `T15B1..T15B5` hiện đúng `Điểm tối đa: None` / `"score": <0..None>` trong prompt, không còn hiện `0` gây hiểu lầm là giáo viên thật sự khai max score = 0. Đây chỉ đổi những gì LLM **đọc thấy**, không đụng gì đến bug tính điểm ở trên (2 chỗ code khác nhau, đều tự lấy `c.get("score", ...)` riêng).

**Cần**: đổi nguồn `max_score` sang fallback không bao giờ là 0 (VD `c.get("score") or c.get("weight") or 1`) trước khi tin tưởng đường batch này.

---

## 7. Dọn field trùng lặp/thừa (đã áp dụng, xuyên suốt Matching/Logical/Table)

| Field đã bỏ | Phạm vi | Lý do | Thay bằng |
|---|---|---|---|
| `is_correct` | Matching, Logical, Table | 100% derivable từ `status` (`status=="correct"`) ở cả 3 grader này — giữ lại chỉ là trùng lặp thông tin. Ở Logical/Table trước đây còn là hằng số cố định, không mang thêm tin gì | `status` — `aggregate_with_group_rules` cũng đổi từ đọc `is_correct` sang `status=="correct"` để không phụ thuộc field đã bỏ |
| `teacher_review_required` | Matching (nhánh "không khớp gì"), Logical (hằng số) | Tương tự — derivable từ `status in TRANSIENT_REVIEW_STATUSES` | `status` (field này **vẫn giữ ở Visual** vì độc lập thật — xem mục 4) |
| `token_evaluations` (Matching) | Matching | Trùng hoàn toàn `expected_output_tokens[i]`/`student_tokens[i]` — is_correct từng token suy ra được bằng `student_tokens[i] is not None` | `expected_output_tokens` + `student_tokens` (helper `_format_token_detail` build lại prompt text từ 2 list này) |
| `student_answer_text` | Mọi grader | Trùng với `evidence["student_answer"]` — 1 chuỗi lưu 2 lần dưới 2 tên | Chỉ giữ `evidence` |
| `exact_match` | Matching, self-reported-index | Thừa vì `status` đã nói lên tình trạng chấm; tên field còn gây hiểu lầm vì `True` cả ở nhánh token/partial credit (không "exact" theo nghĩa đen) | *(bỏ hẳn, không thay)* |
| `conditional_resolved` / `conditional_reason` | Matching | 2 field rời rạc, không đủ ngữ cảnh cho LLM (không nói rõ nguồn điều kiện là gì) | `conditioning` — dict có cấu trúc, xem mục 1b |
| `matched` / `missing` / `column_map` / `student_table_text` | Table | Table không còn tự so khớp cứng nữa (xem mục 3) — các field phục vụ so khớp vị trí cũ (nhánh row đa-key, nhánh delegate gộp-text) không còn ý nghĩa | `student_cell_text` (giá trị thô học sinh viết, để LLM tự verify) |

Đồng thời đổi tên key `"text"` trong `evidence` (trả về từ `get_student_evidence_for_slot`) thành `"student_answer"` — tránh trùng tên với các key `"text"` khác trong codebase (line/token/cell objects ở `sample["student_answer"]["lines"/"tokens"]`, là schema hoàn toàn khác).

**Quyết định đã chốt, không sửa lại**:
- `_grade_by_tokens` (token/partial-credit path, Matching) sẽ **không** thêm nhánh `status="correct"` dù khớp 100% token — xem giải thích ở mục 1.
- `grade_table_row_criterion` sẽ **không** quay lại so khớp cứng `expected_value` — giá trị đó chỉ là ví dụ gợi ý, chấp nhận mọi ví dụ hợp lệ khác của học sinh, LLM (thấy cả bảng, có CoT) là người quyết định thật — xem mục 3 và 6.
- 2 chỗ `.strip()` tác động lên text học sinh (`convert_results_to_samples` khi build `lines[].text`/`tables[].cells[].text`; `get_student_evidence_for_slot` khi ghép nhiều dòng) — **giữ nguyên, không bỏ**. Chỉ trim khoảng trắng đầu/cuối (rác từ OCR), không lowercase, không gộp khoảng trắng giữa — không vi phạm tinh thần "không normalize câu trả lời học sinh".

---

## 8. So sánh cấu trúc PROMPT giữa 4 đường gọi LLM

4 hàm build prompt riêng biệt, không dùng chung 1 template:

| Hàm | Dùng cho | Nguồn gọi |
|---|---|---|
| `_cot_single_pass` (qua `call_llm_cot`) | Matching, Logical — khi `CFG["use_chain_of_thought"]=True` (mặc định) | `_grade_with_llm_advised_core` |
| `call_llm_simple` | Matching, Logical — khi `CFG["use_chain_of_thought"]=False` | `_grade_with_llm_advised_core` |
| `call_llm_table_batch` | Table — cả nhóm criterion cùng 1 bảng | `grade_table_group_with_llm` |
| `_call_vision_llm_for_criterion` | Visual | `grade_visual_criterion` (heuristic router, không qua stage 2) |

### 8a. Phần CHUNG

| Phần chung | Có ở | Không có ở |
|---|---|---|
| Cấu trúc 2 bước **THINK → DECIDE** (2 lần gọi HTTP riêng, DECIDE dựa trên `cot_reasoning` của THINK) | `_cot_single_pass`, `call_llm_table_batch`, `_call_vision_llm_for_criterion` | `call_llm_simple` (1 bước duy nhất) |
| System message DECIDE — **giống hệt nguyên văn**: *"You are a grading assistant. Based on the reasoning provided, output ONLY a valid JSON object. No markdown, no explanation outside the JSON."* | `_cot_single_pass`, `call_llm_table_batch`, `_call_vision_llm_for_criterion` | `call_llm_simple` (dùng system message khác, ngắn hơn: *"You are a grading assistant. Output ONLY a valid JSON object."*) |
| System message THINK — **giống hệt nguyên văn**: *"Bạn là giáo viên chấm thi. Hãy suy luận chi tiết bằng tiếng Việt."* | `_cot_single_pass`, `call_llm_table_batch` | `_call_vision_llm_for_criterion` (THINK **không có** message `role:"system"` — chỉ có `role:"user"` chứa ảnh + text); `call_llm_simple` (không có bước THINK) |
| `temperature=0` cho mọi lần gọi | Cả 4 | — |
| Section `=== TIÊU CHÍ ...===` (nội dung criterion) | Cả 4 (tên section khác chút: `TIÊU CHÍ CHẤM` vs `TIÊU CHÍ`) | — |
| Section đề bài gốc (`ĐỀ BÀI GỐC`) | `call_llm_table_batch` (chỉ khi có `question_text`), `_call_vision_llm_for_criterion` (chỉ khi có `question_text`) | `_cot_single_pass`/`call_llm_simple` — đề bài gốc ở đây nằm **trong** `question_context` (`══ ĐỀ BÀI GỐC ══`, do `_grade_with_llm_advised_core` build), không phải section riêng của chính hàm build prompt |
| `max_tokens` lấy từ `CFG["cot_max_tokens_think"/"cot_max_tokens_decide"]` | Cả 4 (kể cả `call_llm_simple`, dùng `cot_max_tokens_think` dù không có bước THINK — tên field hơi lệch thực tế) | — |
| Trả JSON dạng `{"score", "status", "reasoning"}` là 3 field lõi | Cả 4 | — |

### 8b. Phần KHÁC NHAU

| Khía cạnh | `_cot_single_pass` (text CoT) | `call_llm_simple` (text, không CoT) | `call_llm_table_batch` | `_call_vision_llm_for_criterion` |
|---|---|---|---|---|
| Input bài làm học sinh | Text (`student_text`), 1 section `=== BÀI LÀM HỌC SINH ===` | Text, giống `_cot_single_pass` | **Toàn bộ bảng** (`table_text`, mọi ô kể cả ô không thuộc criterion đang chấm) — không phải chỉ phần của 1 criterion | **Ảnh** (`image_url` base64) — không có bài làm dạng text trong prompt, LLM tự đọc/nhận dạng từ ảnh |
| Đơn vị chấm / 1 lần gọi | 1 criterion | 1 criterion | **N criterion cùng lúc** (cả nhóm bảng) — DECIDE trả `{criterion_id: {...}}` cho từng cái | 1 criterion |
| Ghi chú giáo viên (`grader_note`) | Có, qua `question_context` (`══ GHI CHÚ CỦA GIÁO VIÊN ══`) | Có, giống trên | **Không có** — `criteria_specs` không mang `grader_note` | Có, section riêng `=== GHI CHÚ GIÁO VIÊN (BẮT BUỘC TUÂN THỦ) ===` |
| Quy tắc điểm bán phần (`partial_credit_rule`) | Có, qua `question_context` | Có, giống trên | Không có | Không có |
| Gợi ý heuristic advisory | Khối `══ GỢI Ý TỪ HEURISTIC GRADER ══` — **khác theo grader** qua 2 tham số mới của `_grade_with_llm_advised_core` (`show_heuristic_score_status`, `heuristic_reason_label`): Matching vẫn giữ đủ `Score gợi ý`/`Status gợi ý`/`Lý do` (3 dòng, mặc định); **Logical đã bỏ 2 dòng `Score gợi ý`/`Status gợi ý`** (vì heuristic Logical luôn là hằng số `0`/`needs_teacher_review`, không mang tin gì thật — hiện ra chỉ gây nhiễu), chỉ còn 1 dòng `Found: ...` — cộng `extra_prompt_text` riêng theo wrapper (token detail cho Matching, matched/missing cho Logical) | Giống `_cot_single_pass` (cùng logic show/label theo grader, vì cùng gọi `_grade_with_llm_advised_core`) | **Đã bỏ hẳn** — dòng `Gợi ý heuristic: score=X, status=Y` từng gắn vào mỗi criterion trong `DANH SÁCH Ô CẦN CHẤM` đã bị xóa (cùng lý do Logical: với criterion có nội dung, `heuristic_score` luôn `None`/placeholder, `heuristic_status` luôn `needs_teacher_review` — không mang tin gì thật, chỉ gây nhiễu). `criteria_specs` cũng bỏ luôn 2 key `heuristic_score`/`heuristic_status` (dead sau khi bỏ dòng hiển thị) | **Không có** — Visual không có heuristic advisory nào feed vào (Vision LLM ở đây chính là bước ra quyết định đầu tiên, không phải review lại 1 heuristic khác) |
| "HƯỚNG DẪN CHAIN-OF-THOUGHT" (5 bước, có nhắc "so với gợi ý Heuristic") | Có (trong `question_context`) | Có (trong `question_context`, dù không CoT) | Không có khối này — thay bằng 4 bước riêng gắn liền trong `think_prompt` (đọc vị trí → đối chiếu → xét quan hệ hàng → kết luận) | Không có khối này — thay bằng 4 bước riêng (đọc ảnh → so sánh → đánh giá mức đúng → kết luận) |
| Câu "chấp nhận cách làm tương đương" | Có, **bật/tắt được** qua `accept_equivalent_solutions` (Matching truyền `False`, các wrapper khác giữ `True`) | Nhận tham số nhưng **không dùng** — prompt không có câu này | Không phải câu riêng biệt, mà **lồng thẳng vào câu mở đầu THINK** ("...KHÔNG chỉ so khớp chuỗi cứng...vẫn đúng logic/quan hệ toán học...vẫn tính đúng") — luôn bật, không toggle được | Có, **luôn bật, không toggle được** (`equivalence_note` hardcode, không nhận tham số) |
| Self-consistency voting (`cot_self_consistency_n` lần, `_vote_majority`) | Có (ở tầng `call_llm_cot` bọc ngoài `_cot_single_pass`) | Có (ở tầng `call_llm_simple`) | **Không** — batch nhiều criterion/lần gọi rồi nên giữ đơn giản, 1 pass | **Không** — 1 pass |
| Format khối DECIDE input | `--- BẮT ĐẦU PHÂN TÍCH ---\n{cot_reasoning}\n--- KẾT THÚC PHÂN TÍCH ---` | *(không áp dụng — không có DECIDE riêng)* | Giống `_cot_single_pass` (cùng marker `BẮT ĐẦU/KẾT THÚC PHÂN TÍCH`) | Khác — không có marker, chỉ `"Dựa trên phân tích sau:\n\n{cot_reasoning}\n\n..."` |
| JSON schema yêu cầu ở DECIDE | `score, status, reasoning, confidence, feedback, suggestion` (6 field — nhiều nhất, có cả gợi ý sửa bài) | Giống hệt schema của `_cot_single_pass` (6 field) dù prompt 1-bước | Chỉ `score, status, reasoning` (3 field), lặp lại N lần — 1 entry/criterion_id, **không có `confidence`** | `score, status, reasoning, confidence` (4 field, viết trên 1 dòng thay vì nhiều dòng) |
| `max_tokens` DECIDE/THINK có nhân theo số lượng | Không | Không | **Có** — nhân với `len(criteria_specs)` (batch càng nhiều ô, budget token càng lớn) | Không |
| Ai build `question_context`/advisory | `_grade_with_llm_advised_core` (dùng chung 1 lần, truyền cho cả `_cot_single_pass` lẫn `call_llm_simple`) | *(nhận sẵn từ trên, không tự build)* | `grade_table_group_with_llm` tự build `criteria_text` — không tái dùng `_grade_with_llm_advised_core` | `_call_vision_llm_for_criterion` tự build `context_block` riêng — cũng không tái dùng `_grade_with_llm_advised_core` |

### 8c. Nhận xét

`question_context` (khối advisory giàu nhất: heuristic score/status/lý do, đề bài gốc, `sample_solution`, `grader_note`, `partial_credit_rule`, hướng dẫn CoT 5 bước) **chỉ được build 1 lần** ở `_grade_with_llm_advised_core` và dùng chung cho cả `call_llm_cot`/`call_llm_simple` — đây là lý do 2 hàm này có prompt gần như giống hệt nhau về nội dung advisory, chỉ khác cấu trúc gọi (1 bước hay 2 bước). Ngược lại, `call_llm_table_batch` và `_call_vision_llm_for_criterion` **mỗi hàm tự build phần advisory/context riêng** — không tái dùng logic của `_grade_with_llm_advised_core` — nên bị thiếu 1 số phần mà 2 hàm text kia có (VD `grader_note`/`partial_credit_rule` ở table-batch, heuristic advisory ở visual).
