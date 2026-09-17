# Toàn bộ cảnh báo và lỗi của hệ thống

Liệt kê mọi thông báo hệ thống có thể sinh ra, chia theo **thứ bạn nhìn thấy
trên giao diện** và **thứ chỉ nằm trong log**. Mục thứ hai mới là mục đáng đọc:
đó là những vấn đề vẫn xảy ra thật, vẫn ảnh hưởng tới điểm, nhưng không có gì
báo cho bạn biết.

Cập nhật: 2026-08-12.

---

## Phần 1 — Hiện lên giao diện

### 1.1 Bảng kiểm tra barem (`/barem`, panel bên phải)

Chạy lại sau **mỗi lần gõ**, trên chính bản nháp đang mở. Đây là bản dựng lại
`validate_barem()` của backend bằng TypeScript, cộng thêm các phép kiểm mà
backend **không** làm (`frontend/src/modules/barem/validate.ts`).

Phân biệt hai mức:

- **❌ error** — `load_barem()` từ chối, hoặc chắc chắn chấm sai
- **⚠️ warning** — barem vẫn nạp được nhưng nhiều khả năng không đúng ý bạn

#### Điểm số và nhóm

| Mức | Thông báo |
|---|---|
| ❌ | Tổng điểm tính từ barem khác `total_score` khai báo |
| ❌ | `score` để trống nhưng không thuộc nhóm `all_or_nothing` — không nơi nào bù điểm |
| ❌ | `score` âm |
| ❌ | `criterion_id` trùng lặp / thiếu `criterion_id` |
| ❌ | Nhóm: `group_max_score` không nhất quán giữa các thành viên |
| ❌ | Thuộc nhóm `all_or_nothing` nhưng tiêu chí cha thiếu `criterion_id` |
| ⚠️ | Nhóm chỉ có 1 thành viên — `all_or_nothing` vô nghĩa |

#### Cấu trúc câu, part, slot

| Mức | Thông báo |
|---|---|
| ❌ | Câu chưa có part nào / part thiếu `part_label` / `part_label` trùng |
| ❌ | `grading_rule` rỗng — câu này sẽ không được chấm |
| ❌ | `part_label` không tồn tại trong `question.parts` |
| ❌ | `slot_ids` trỏ tới slot không tồn tại |
| ❌ | `question_number` trùng — `load_barem()` chỉ giữ entry cuối |
| ❌ | `slot_id` trùng lặp |
| ⚠️ | Chưa khai `slot_ids` — phải lùi về lọc theo `part_label`, kém chính xác |
| ⚠️ | Part chưa có `answer_slot` nào / part không có tiêu chí nào chấm |
| ⚠️ | `content` để trống — nguồn chính LLM dùng để hiểu tiêu chí |
| ⚠️ | `sample_id` trùng lặp |
| ⚠️ | Thiếu hoặc lạ `question_type` |

#### Matching

| Mức | Thông báo |
|---|---|
| ❌ | Cần `expected_outputs` hoặc `conditional_outputs` |
| ❌ | `partial_credit_rule` thiếu `condition` |
| ⚠️ | Token không xuất hiện trong bất kỳ đáp án nào — bắt lỗi gõ nhiều token vào một ô |
| ⚠️ | Đáp án có khoảng trắng ở đầu/cuối (so khớp là byte-exact) |
| ⚠️ | Đáp án trùng nhau |
| ⚠️ | Đáp án là chuỗi rỗng |
| ⚠️ | Có `partial_credit_rule` nhưng `expected_output_tokens` rỗng |
| ⚠️ | `partial_score` lớn hơn điểm tối đa của tiêu chí |

#### Conditional

| Mức | Thông báo |
|---|---|
| ❌ | Có `conditional_outputs` nhưng thiếu `condition_source` |
| ❌ | `sample_field` phải khai `field` / `self_reported` phải khai `slot_ids` (LIST) |
| ❌ | `slot_ids` trỏ tới slot không tồn tại |
| ❌ | Nhánh thiếu `condition` / thiếu `expected_outputs` |
| ❌ | `condition` không phân tích được — nhánh bị bỏ qua với **mọi** học sinh |
| ⚠️ | `condition` không dùng biến `value` |
| ⚠️ | Khai `condition_source` nhưng không có `conditional_outputs` |

#### Logical

| Mức | Thông báo |
|---|---|
| ❌ | `expected_value` phải là object `{keywords, sample_solution}` |
| ❌ | Chỉ chấp nhận đúng 2 key — key thừa bị bỏ qua hoàn toàn khi chấm |
| ❌ | `keywords` phải là list phẳng các chuỗi |
| ⚠️ | Chưa có keyword nào |

#### Table

| Mức | Thông báo |
|---|---|
| ❌ | Phải khai cả `row_id` và `col_id` — mỗi tiêu chí chấm đúng 1 ô |
| ❌ | Part chưa khai bảng nào / ô không tồn tại trong `table_slot` |
| ❌ | `cell_id` không khớp `row_id`+`col_id` / ô khai trùng |
| ⚠️ | Ô `printed` nhưng text rỗng |
| ⚠️ | Ô `student_text` nhưng có sẵn text — text đó bị bỏ qua |
| ⚠️ | `expected_value` trống — LLM không có ví dụ gợi ý |

### 1.2 Cảnh báo tại chỗ trong trình soạn barem

Không nằm trong bảng kiểm tra, mà hiện ngay cạnh ô đang gõ.

| Chỗ | Thông báo |
|---|---|
| Ô đáp án / token | Dòng rỗng — sẽ được lưu nguyên vào barem |
| Ô đáp án / token | Có khoảng trắng ở đầu/cuối — được giữ nguyên và tính vào so khớp |
| Ô "Điểm cả câu" | Điểm không được âm |
| Ô "Điểm cả câu" | Các tiêu chí đang là 0 điểm nên không có tỉ lệ để chia |
| Nhóm tiêu chí | Nhóm có `grader_note` + con loại `table` ⇒ bật `group_llm_decided` |

**Ô "Thử một bài mẫu"** (tiêu chí `matching`):

- Đủ 100% token vẫn không bao giờ thành `correct` — chỉ đường khớp tuyệt đối mới đạt
- Có `partial_credit_rule` ⇒ điểm theo tỉ lệ bị **thay thế hoàn toàn**; không khớp quy tắc nào thì về 0

**Ô "Thử giá trị"** (conditional):

- Tô đỏ giá trị không rơi vào nhánh nào, kèm đếm số lượng
- Cảnh báo khi hai nhánh cùng đúng (nhánh sau bị bỏ qua)
- Báo điều kiện không đọc được, kèm lý do cú pháp

### 1.3 Khai vùng ROI (`/pipeline` bước 4)

Kiểm ở trình duyệt trước khi gửi, và kiểm lại lần nữa ở server.

| Thông báo |
|---|
| `rois[i]` thiếu trường bắt buộc |
| `rois[i]` có `task_type` không hợp lệ |
| `rois[i]` là bảng nên bắt buộc có số hàng và số cột |
| `rois[i]` trỏ tới trang N nhưng đề mẫu chỉ có M trang |
| `rois[i]` trùng `cau_key` với một vùng trước đó |
| File không có mảng `rois` |

### 1.4 Lỗi trả về từ API

Hiện nguyên văn (`detail` của FastAPI) tại chỗ bạn vừa bấm.

| Mã | Thông báo |
|---|---|
| 400 | Barem phải là một object JSON |
| 400 | Barem thiếu trường `ma_de` / thiếu danh sách `teacher_barem` |
| 400 | File không phải JSON hợp lệ |
| 400 | Cần chọn barem từ thư viện (`barem_id`) hoặc tải lên `barem_file` |
| 400 | Không giải nén được file zip |
| 400 | `roi_config` thiếu danh sách `rois` (hoặc rỗng) |
| 400 | `task_type` không hợp lệ / `task_type='table'` yêu cầu `n_rows` và `n_cols` |
| 404 | Không tìm thấy barem trong thư viện / không tìm thấy barem đã chọn |
| 404 | Không thấy mã đề trong zip |
| 404 | Đề mẫu chỉ có N trang |
| 404 | upload không tồn tại (hoặc đã bị dọn) |
| 409 | Phiên chấm chưa xong |
| 409 | OCR chưa hoàn tất cho job này |
| 503 | Module 3 chưa cấu hình LLM (thiếu `.env`) |

### 1.5 Trạng thái phiên chấm và kết nối

| Chỗ | Thông báo |
|---|---|
| Sidebar | Chấm đỏ khi backend không kết nối được |
| Sidebar | Chưa cấu hình LLM trong `.env` — OCR và chấm điểm đều không chạy được |
| Trang phiên chấm | Trạng thái `failed` kèm nguyên văn thông báo lỗi |
| `/pipeline/:jobId` | **Nhật ký chạy** — đọc trực tiếp stdout của tiến trình |
| Tab Soát bài | **Vùng không khớp câu nào trong barem** — bắt lỗi gõ nhầm `cau_key` |

---

## Phần 2 — KHÔNG hiện lên giao diện

Đây là phần quan trọng. Những thứ dưới đây xảy ra thật và ảnh hưởng tới điểm,
nhưng không có gì báo lên màn hình.

### 2.1 Lỗi barem của `validate_barem()` không chặn việc chấm

`load_barem()` chạy `validate_barem()` rồi **chỉ `print()` kết quả**. Nó
**không `raise`**. Nghĩa là một barem có lỗi thật vẫn nạp bình thường và vẫn
được đem đi chấm:

```
  [ERROR] validate_barem: 3 barem format errors
    - Q4/T4: score âm (-0.5)
```

Dòng đó nằm trong log của tiến trình, không xuất hiện ở đâu trên web.

`load_barem()` chỉ ném lỗi thật với đúng hai trường hợp: thiếu `ma_de`, và
không tìm thấy file barem.

**Giảm thiểu**: soạn barem trong `/barem` và đọc bảng kiểm tra ở đó — nó bắt
được các lỗi này *trước* khi chấm. Nhưng nếu bạn nạp barem bằng đường khác
(upload thẳng file, hoặc chạy CLI), không có lớp bảo vệ nào.

### 2.2 Luồng chấm từ file JSON không có chỗ xem log

`/api/v1/pipeline/jobs/{id}/log` chỉ tồn tại cho luồng chấm cả lớp từ ảnh.
Luồng chấm từ JSON ở trang chủ **không có endpoint tương ứng**, dù worker vẫn
ghi đầy đủ vào `var/jobs/{job_id}/worker.log`.

Hệ quả: mọi cảnh báo ở mục 2.1, 2.3, 2.4 dưới đây đều **hoàn toàn vô hình**
khi chấm bằng trang chủ. Muốn đọc thì phải mở file trên máy chủ:

```bash
cat backend/var/jobs/<job_id>/worker.log
```

### 2.3 Cảnh báo trong lúc chấm

Chỉ in ra stdout:

| Thông báo | Nghĩa là gì |
|---|---|
| `⚠ Condition eval failed: '...'` | Một nhánh conditional có điều kiện sai cú pháp — nhánh đó bị bỏ qua với **mọi** học sinh |
| `⚠ prepare_conditional_output: KHÔNG điều kiện nào khớp value=...` | Học sinh này được chấm với danh sách đáp án **rỗng** ⇒ luôn sai dù bài đúng |
| `⚠ partial_credit_rule eval failed` | Quy tắc điểm bán phần không chạy được ⇒ về 0 điểm |
| `[ERROR] Invalid 'ma_de' value in input data` | Trả về danh sách sample rỗng |
| `[WARN] validate_input: N cảnh báo` | Dữ liệu bài làm có vấn đề |

### 2.4 Câu không khớp barem — chấm 0/0 trong im lặng

`cau_key` gõ sai (hoặc câu không có trong barem) thì `barem_dict.get(q_num, [])`
trả về danh sách rỗng. Câu đó được chấm **0.00 / 0.00**, `wrong: []`.

Trên bảng điểm nó trông **y hệt một bài bỏ trắng**. Không có cảnh báo nào.

Đây chính là thứ từng gây ra `ZeroDivisionError` (đã sửa): khi *mọi* câu đều
không khớp, tổng điểm tối đa bằng 0.

**Giảm thiểu**: luồng chấm cả lớp từ ảnh có mục **"Vùng không khớp câu nào
trong barem"** ở tab Soát bài. Luồng chấm từ JSON thì **chưa có gì**.

### 2.5 Chất lượng OCR — không có cảnh báo nào cả

Module 3 trả về `status: "completed"` kể cả khi đọc sai chữ. Đã ghi nhận thật:

- Đọc `'giả định sai'` thành `'gia tri sai'` — sai một ô bảng, sai điểm cả nhóm
- Lượt 2 (tự soát) thường trả về y hệt lượt 1, không sửa gì

Không có ngưỡng tin cậy nào chặn việc này lại. `confidence` trong `module3.py`
chỉ nhận đúng hai giá trị: `1.0` khi gọi API thành công, `0.0` khi thất bại —
nó nói **có đọc được hay không**, hoàn toàn không nói **đọc có đúng hay không**.
Đừng dùng nó để lọc bài cần soát.

**Giảm thiểu**: tab **Soát bài** đặt ảnh cắt cạnh chữ máy đọc. Đây là cách duy
nhất phát hiện, và phải làm thủ công.

### 2.6 Module 1 khoanh sai vùng

Không có cảnh báo. Bạn phải tự nhìn khung vẽ trên ảnh.

Đã biết: với ảnh đề mẫu 595×816 (~72 DPI) trong repo, nó bỏ sót phần lớn dòng
chấm và đôi khi khoanh vào giữa khối code. Nguyên nhân là độ phân giải, không
phải tham số — xem `backend/ocr/README.md`.

Ảnh hưởng hạn chế: đây chỉ là **gợi ý**, `roi_config.json` bạn chốt mới quyết
định. Nhưng nếu bạn tin nó mà không kiểm, vùng cắt sẽ lệch và mọi thứ phía sau
sai theo.

### 2.7 Căn trang thất bại — lý do biến mất khỏi kết quả

Trang nào không căn được (thiếu trang, ORB không tìm đủ đặc trưng, ảnh lệch quá)
thì mọi vùng trên trang đó nhận `status: "failed_at_cropping"` với
`content.lines` **rỗng**. Bài làm coi như bỏ trắng, và chấm ra 0 điểm.

Lý do cụ thể (`thiếu trang 3`, `FEATURE_ERROR`, `HOMOGRAPHY_ERROR`…) chỉ được
gắn vào **thông báo tiến độ** trong lúc chạy:

```
HS_7 · Cau_11 (trang 3: HOMOGRAPHY_ERROR)
```

Dòng đó trôi qua trên thanh tiến độ rồi mất — **không** được ghi vào file kết
quả. Mở `/api/v1/pipeline/jobs/{id}/ocr-result` sau đó chỉ thấy
`failed_at_cropping`, không biết vì sao.

Nói cách khác: một học sinh bị 0 điểm vì scan lệch, và bảng điểm của bạn trông
giống hệt như em đó không làm bài.

Còn một trạng thái nữa là `failed_all_samples` — dùng khi không encode được ảnh
crop, hoặc module 3 gọi API thất bại sau khi đã retry.

### 2.8 Điểm hiển thị của ô bảng không phải điểm thật của nhóm

Với nhóm `group_llm_decided`, điểm từng ô vẫn hiện đúng trạng thái riêng của nó,
nhưng **điểm thật của nhóm do LLM quyết**, không phải tổng các ô. Panel chi tiết
có hiện khối `group_overrides` kèm lý do — nhưng nếu chỉ nhìn cột điểm từng tiêu
chí thì con số không cộng lại thành tổng, rất dễ tưởng hệ thống tính sai.

---

## Tóm tắt: chỗ nào nên nhìn

| Muốn biết | Xem ở đâu |
|---|---|
| Barem có hợp lệ không | Bảng kiểm tra ở `/barem` — **trước** khi chấm |
| Chấm cả lớp đang chạy tới đâu | Nhật ký chạy ở `/pipeline/:jobId` |
| OCR đọc có đúng không | Tab **Soát bài** — bắt buộc phải tự đọc |
| `cau_key` có khớp barem không | Mục "Vùng không khớp câu nào" (chỉ có ở luồng ảnh) |
| Chấm từ JSON có cảnh báo gì | `backend/var/jobs/<job_id>/worker.log` trên máy chủ |
| Vì sao một học sinh bị 0 điểm cả trang | Thanh tiến độ **lúc đang chạy** — sau đó lý do mất luôn |

## Việc nên làm để bớt điểm mù

Xếp theo tỉ lệ lợi ích trên công sức:

1. **Thêm `/api/v1/grading/jobs/{id}/log`** cho luồng chấm từ JSON — file log đã
   ghi sẵn rồi, chỉ thiếu chỗ đọc. Copy nguyên endpoint của luồng pipeline là
   xong, và nó mở khoá toàn bộ mục 2.1–2.4 cùng lúc.
2. **Ghi `page_error` vào file kết quả** thay vì chỉ nhét vào thông báo tiến độ,
   để biết vì sao một trang bị 0 điểm sau khi phiên chấm đã kết thúc.
3. **Cảnh báo trên bảng điểm** khi có câu `0.00 / 0.00` do không khớp barem —
   hiện tại nhìn y hệt bài bỏ trắng.
4. **Trả cảnh báo của `validate_barem()`** về theo job, thay vì chỉ in ra log.
