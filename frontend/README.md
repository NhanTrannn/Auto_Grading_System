# Frontend (Autograding2026)

React + TypeScript + Vite, styling bằng **CSS Modules thuần** (không Tailwind,
không component library). Toàn bộ màu/spacing/shadow lấy từ CSS custom
properties khai trong [`src/styles/global.css`](src/styles/global.css) — có sẵn
2 bảng màu sáng/tối, đổi qua nút ở cuối sidebar (lưu trong `localStorage`).

## Backend phía sau

`vite.config.ts` proxy `/api` tới `http://localhost:8000` — **một** service
duy nhất (`backend/app`), phục vụ chấm điểm, luồng pipeline, thư viện barem và
cả 3 module OCR (`/api/v1/ocr/*`). Trước đây OCR là service riêng ở port 8081
với prefix proxy `/ocr`.

Sidebar hiển thị trạng thái kết nối (poll 20s một lần qua
`src/hooks/useServiceHealth.ts`), nên nếu quên bật backend sẽ thấy ngay chấm
đỏ thay vì lỗi mù mờ khi bấm nút. Cùng request đó trả về `llm_configured` —
thiếu `.env` thì sidebar cảnh báo trước khi bạn tốn thời gian upload.

## Chạy local

```bash
# Terminal 1 — backend
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend && npm install && npm run dev
```

## Các màn hình

| Route | Nội dung |
| --- | --- |
| `/pipeline` | **Chấm cả lớp từ ảnh** — wizard 4 bước: (1) 2 file zip → (2) chọn mã đề, xem bảng gán `HS_N ← thư mục` → (3) chọn barem từ thư viện → (4) khai vùng bằng trình gán ROI hoặc `roi_config.json`. Có ước tính số lượt OCR trước khi chạy |
| `/pipeline/:jobId` | Tiến độ 2 giai đoạn (OCR → chấm điểm), nhật ký chạy trực tiếp, rồi 2 tab: **Bảng điểm** (cả lớp) và **Soát bài** (từng học sinh: ảnh cắt cạnh chữ OCR đọc được, lướt bằng phím ← →) |
| `/barem` | Trình soạn barem — xem mục riêng bên dưới. Nút **Lưu vào thư viện** đẩy rubric lên server để dùng ở `/pipeline` và `/` |
| `/` | Dashboard: thống kê phiên chấm, chấm từ Results JSON đã có (chọn barem **từ thư viện**, không phải upload lại), danh sách phiên gần đây |
| `/jobs/:jobId` | Kết quả một phiên chấm: stat card, phổ điểm, bảng điểm có tìm kiếm/lọc/sắp xếp, panel chi tiết từng tiêu chí + lý do LLM, tải CSV/JSON |
| `/ocr/roi` | Module 1 — phát hiện ROI, vẽ khung trực tiếp lên ảnh, xuất `roi_config.json` nháp |
| `/ocr/align` | Module 2 — căn chỉnh ảnh, thanh trượt chồng ảnh template ↔ ảnh đã căn, tải ảnh kết quả |
| `/ocr/text` | Module 3 — OCR chữ viết tay, hiển thị song song lượt 1 (thô) và lượt 2 (đã tự soát) |

## Cấu trúc

```
src/
  components/core/   Button, Badge, Card, PageHeader, FileDrop, StatCard,
                     Spinner, Tabs, EmptyState, ThemeToggle, Icon (SVG inline)
  app/layouts/       DashboardLayout — sidebar + <Outlet/>
  app/router/        định nghĩa route
  modules/grading/   UploadForm, JobStatusView, ResultsView, ScoreDistribution,
                     StudentDetailPanel, JobHistorySidebar, useJobStatus
  modules/pipeline/  PipelineUploadForm (wizard), RoiMapper (gán vùng trên
                     ảnh), PipelineProgress, LiveLogPanel, StudentReview
                     (soát bài), usePipelineJob, roiConfigUtils +
                     cauKeySuggestions
  modules/barem/     trình soạn barem (editor, validate, migrate, factory,
                     rescore, conditionEval, MatchingPreview) + BaremPicker
                     — picker nằm ở đây vì cả /pipeline lẫn / đều dùng
  modules/ocr/       RoiDetectView, AlignView, OcrView, OcrContent
  services/          api.ts (chấm điểm), pipelineApi.ts (luồng ảnh→điểm),
                     baremApi.ts (thư viện barem), ocrApi.ts (3 module OCR lẻ,
                     gọi /api/v1/ocr/*)
  types/             grading.ts, pipeline.ts, barem.ts, baremLibrary.ts,
                     ocr.ts — khớp schema backend
```

## Trình soạn barem (`/barem`)

Ba field dễ khai sai nhất được làm rõ ngay trong giao diện, vì luật của
`pipeline.py` không đoán ra được từ tên field:

- **`expected_outputs`** — mỗi ô là **một đáp án trọn vẹn**, so khớp nguyên văn
  từng ký tự. Đáp án nhiều dòng gõ xuống dòng **trong cùng một ô**; tách thành
  hai ô là thành hai đáp án riêng và bài của học sinh không khớp cái nào. Ô nhập
  giữ nguyên từng ký tự, không cắt khoảng trắng đầu/cuối (trước đây một textarea
  duy nhất tách theo dấu xuống dòng, nên đáp án nhiều dòng là *không thể khai*).
- **`expected_output_tokens`** — **không có dấu phân cách nào**: mỗi ô là một
  token riêng, tìm nguyên văn như một đoạn con, theo đúng thứ tự trên xuống.
  Khoảng trắng gõ trong một ô là một phần của token đó.
- **`conditional_outputs`** — chia 3 bước (lấy `value` từ đâu → các nhánh → thử).
  Nhánh xét từ trên xuống, **dừng ở nhánh đầu tiên đúng**, nên có nút đổi thứ tự.

Kèm hai công cụ thử tại chỗ:

- **Thử một bài mẫu** (tiêu chí `matching`): dán bài học sinh, xem khớp tuyệt đối
  hay không, token nào trúng ở vị trí nào, ra bao nhiêu điểm. Cảnh báo luôn hai
  bẫy: đủ 100% token vẫn chỉ là `partially_correct`, và `partial_credit_rule`
  **thay thế hoàn toàn** điểm theo tỉ lệ.
- **Thử giá trị** (conditional): nhập dải STT, xem giá trị nào rơi vào nhánh nào,
  **tô đỏ giá trị không nhánh nào nhận** (học sinh như vậy bị chấm với danh sách
  đáp án rỗng ⇒ luôn sai). `conditionEval.ts` là bản dựng lại
  `safe_eval_condition` bằng parser tự viết (không dùng `eval`, giữ đúng tính
  chất "barem không chạy được code"); đã đối chiếu **720 trường hợp** với Python
  và khớp 100%.

Ô **"Điểm cả câu"** đặt ngay cạnh `question_number`: câu không có điểm riêng nên
nhập vào đây sẽ **chia lại theo tỉ lệ** cho các tiêu chí con (giữ nguyên `weight`
và các con trong nhóm `all_or_nothing`, vì điểm của chúng vốn suy ra từ cha), rồi
sửa luôn con số "… điểm" trong `question.text` — nhưng chỉ khi đề bài có **đúng
một** cụm như vậy; nhiều hơn thì để tác giả tự sửa vì không suy ra được.

Tắt `all_or_nothing` sẽ tự gán `weight: 1` cho tiêu chí con nào chưa có điểm.
Nếu không, chúng mất chỗ gánh điểm: đo trên câu 15, chỉ bỏ tick thôi làm tổng
điểm câu tụt từ 1.00 xuống 0.75 kèm 6 lỗi validate.

## Lưu ý về chi phí

Các nút **“Chạy toàn bộ luồng”** (`/pipeline`), **“Bắt đầu chấm”** (`/`) và
**“Nhận dạng chữ viết”** (`/ocr/text`) đều gọi LLM thật và phát sinh chi phí
API — riêng `/pipeline` tốn nhiều nhất (mỗi vùng của mỗi học sinh là 2 lượt gọi
Qwen3-VL, cộng thêm phần chấm điểm), nên form có hiển thị sẵn con số ước tính
trước khi bạn bấm. Module 1 và Module 2 chỉ chạy OpenCV nên miễn phí.

Riêng phần chấm: mỗi tiêu chí văn bản tốn **6 request** (`cot_self_consistency_n
= 3` lần bỏ phiếu × 2 request THINK+DECIDE) — với `sample_parem.json` là khoảng
130 request/học sinh. Chỉnh `CFG["cot_self_consistency_n"]` trong
`backend/pipeline.py` nếu muốn đánh đổi độ ổn định lấy chi phí.
