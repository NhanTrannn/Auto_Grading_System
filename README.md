# Auto Grading System

Pipeline chấm điểm tự động bài thi/bài tập tự luận tiếng Việt, kết hợp **rubric (barem) có cấu trúc**, **so khớp heuristic** và **LLM (Chain-of-Thought + self-consistency voting)** để chấm điểm từng tiêu chí (criterion) trong bài làm của học sinh — cùng một web app (FastAPI + React) bọc quanh pipeline đó.

## Cấu trúc repo

```
.
├── backend/     # pipeline chấm điểm gốc (pipeline.py + dữ liệu/tool) + FastAPI web API bọc quanh nó
├── frontend/    # React + TypeScript + Vite, giao diện web cho hệ thống
├── CLAUDE.md    # tài liệu kiến trúc/hành vi chi tiết của pipeline.py (đọc trước khi sửa pipeline.py)
├── FE_ARCHITECTURE_OVERVIEW.md    # hướng dẫn cấu trúc thư mục frontend/src
└── FE_BE_INTEGRATION_GUIDE.md     # cách frontend gọi backend, danh sách endpoint hiện có
```

`pipeline.py` và mọi dữ liệu/tool đi kèm nó (`testing/input/`, `testing/output/`, `structure/`, `scripts/`, `tool/`, `docs/`...) nằm trong `backend/`, cạnh package FastAPI (`backend/app/`) — không tách biệt hay nhân bản; `backend/app/services/grading_engine/wrapper.py` import thẳng `pipeline.py` trong cùng tiến trình, không qua subprocess/HTTP. Xem `backend/README.md` để biết cách chạy web API, `CLAUDE.md` để hiểu kiến trúc chấm điểm bên trong `pipeline.py`.

## Chạy nhanh

Pipeline CLI (không cần web server):

```bash
cd backend
pip install -r requirements.txt
python pipeline.py --test
```

### Dev (hot-reload)

```bash
# Terminal 1 — backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload   # mặc định port 8000

# Terminal 2 — frontend
cd frontend
npm install
npm run dev   # http://localhost:5173, proxy /api -> backend
```

### Production (backend Docker, frontend build tĩnh)

```bash
# Backend — cần Docker Desktop đang chạy (docker info phải thành công)
cd backend
docker compose -f docker-compose.prod.yaml up --build -d
curl http://localhost:8000/api/v1/health   # {"status":"ok","llm_configured":true}

# Frontend — build production rồi phục vụ dist/
cd frontend
npm install
npm run build
npm run preview -- --host   # http://localhost:4173, --host để máy cùng LAN vào được
```

Dừng backend: `docker compose -f docker-compose.prod.yaml down` (thêm `-v` để
xoá luôn volume — mất toàn bộ lịch sử job/barem). Dừng frontend: Ctrl+C ở
terminal đang chạy `vite preview`, hoặc kill tiến trình `node` tương ứng.

Cả 2 chế độ đều cần `.env` (mục Cấu hình bên dưới) ở **repo root**.

### Cổng 8000 đã bị chiếm sẵn trên máy?

Có thể xảy ra thật (đã gặp: 1 project khác không liên quan trên cùng máy dev
đã bind sẵn port 8000) — triệu chứng là `docker compose up` báo thành công,
`docker ps` hiện cổng đã map, nhưng `curl localhost:8000/...` lại không trả
đúng response app này (hoặc không phản hồi gì), vì có tiến trình khác trên
host đang trả lời thay. Kiểm tra bằng `netstat -ano | grep ":8000"` (Windows)
— nếu thấy nhiều hơn 1 tiến trình, đổi sang cổng khác:

1. `backend/docker-compose.prod.yaml` (hoặc lệnh `uvicorn --port` nếu chạy
   dev không qua Docker): đổi **phía host** của port mapping, VD `"8001:8000"`
   — phía container/uvicorn giữ nguyên 8000, không cần đụng gì trong code.
2. Tạo `frontend/.env` (không commit) với `VITE_BACKEND_PORT=8001` (đổi đúng
   số vừa chọn ở bước 1) — cả `vite.config.ts` (proxy dev lẫn `preview`) và
   sidebar frontend (nhãn "Backend :port") đều đọc chung biến này, chỉ cần
   sửa 1 chỗ.
3. Chạy lại `npm run dev` hoặc `npm run build && npm run preview -- --host`.

## Mục lục (chi tiết pipeline chấm điểm)

- [Tổng quan](#tổng-quan)
- [Kiến trúc chấm điểm](#kiến-trúc-chấm-điểm)
- [Cấu trúc thư mục backend/](#cấu-trúc-thư-mục-backend)
- [Cài đặt](#cài-đặt)
- [Cấu hình](#cấu-hình)
- [Định dạng dữ liệu đầu vào](#định-dạng-dữ-liệu-đầu-vào)
- [Cách chạy](#cách-chạy)
- [Kết quả đầu ra](#kết-quả-đầu-ra)
- [Công cụ hỗ trợ](#công-cụ-hỗ-trợ)

## Tổng quan

Hệ thống nhận vào:
1. **Barem** (`backend/sample_parem.json`) — rubric chấm điểm dạng cây, mỗi câu hỏi có các `criterion` con với điểm số, loại chấm (fill-in-blank, expected-value, table, visual...).
2. **Bài làm học sinh** (OCR hoặc dữ liệu đã trích xuất) — text, token, bảng, ảnh vẽ tay theo từng `part_label`.

Từ đó sinh ra điểm chi tiết theo từng tiêu chí, kèm giải thích (reasoning) của LLM, phục vụ việc review lại của giáo viên. Web app (`backend/app/` + `frontend/`) bọc quanh pipeline này để upload input/barem và theo dõi kết quả qua trình duyệt thay vì chỉ chạy CLI.

## Kiến trúc chấm điểm

Pipeline hỗ trợ nhiều "hệ thống" chấm điểm khác nhau, có thể so sánh chất lượng với nhau (xem [backend/tool/compare_systems.py](backend/tool/compare_systems.py)):

| Hệ thống | Mô tả |
|---|---|
| **Heuristic** | So khớp câu trả lời bằng rule-based (regex, normalize text, similarity, so khớp bảng/giá trị số) — không gọi LLM, nhanh và rẻ. |
| **Hybrid** | Kết hợp heuristic cho phần dễ chấm + LLM cho phần cần suy luận. |
| **Pure LLM (Chain-of-Thought)** | LLM tự suy luận (THINK) trước khi ra quyết định (DECIDE) qua 2 lần gọi tách biệt; có **self-consistency voting** (gọi lại N lần độc lập, lấy kết quả đa số) để giảm sai số do model nhỏ/flaky. |
| **Advisory (System 4: LLM + Heuristic Advisory)** | LLM chấm chính, heuristic đóng vai trò "cố vấn" cung cấp gợi ý/route câu hỏi, dùng cho batch chấm thật (`run_batch`). |

Các cơ chế chính trong [backend/pipeline.py](backend/pipeline.py):
- `flatten_criteria` — làm phẳng cây barem (`grading_rule` / `sub_questions` / `sub_criteria`) thành danh sách tiêu chí phẳng để chấm tuần tự, hỗ trợ nhóm `all_or_nothing`.
- `apply_question_routing` / `compute_routing_confidence` — định tuyến câu hỏi vào đúng chế độ chấm (fill-in-blank, expected-value, table, visual...).
- `grade_criterion` / `grade_criterion_advised` — chấm từng tiêu chí, chọn chế độ chấm phù hợp (`infer_criterion_grading_mode`).
- `call_llm_cot` / `_cot_single_pass` / `_vote_majority` — gọi LLM theo chế độ Chain-of-Thought với voting.
- `grade_sample_advised` / `run_batch` — chấm toàn bộ batch mẫu, xuất kết quả + log token/latency.
- `convert_results_to_samples` — tự nhận diện và convert định dạng "Results" (dữ liệu OCR thô) sang định dạng sample chuẩn của pipeline.

## Cấu trúc thư mục backend/

```
backend/
├── pipeline.py              # Pipeline chấm điểm chính (CLI entry point)
├── app/                      # FastAPI web API bọc quanh pipeline.py — xem backend/README.md
├── sample_parem.json         # Barem/rubric mẫu
├── extract_token_cost.py     # Trích xuất chi phí token từ log/kết quả
├── testing/                  # Dữ liệu test/dữ liệu mẫu (không phải code) — gom vào đây để tách khỏi pipeline.py + app/
│   ├── input/                 # Dữ liệu đầu vào (ground truth, bài làm học sinh)
│   ├── output/                # Kết quả chấm điểm, log token/latency (sinh ra khi chạy)
│   ├── Diagram/                # Ảnh minh họa câu hỏi có hình vẽ (dùng cho chấm visual)
│   └── scratch_smoke/
├── docs/                     # Tài liệu thiết kế, báo cáo, hướng dẫn prompt
│   ├── PIPELINE_EXECUTION_FLOW.md
│   ├── LLM_PROMPT_FLOW*.md
│   ├── PROMPTING_TECHNIQUES_AND_METHODS.md
│   └── grading_audit_report.md
├── structure/                # Đặc tả cấu trúc dữ liệu input/barem (structure_input.txt, structure_parem.txt)
├── scripts/                  # Script tiện ích (convert_results_to_samples.py)
├── tool/                     # Công cụ debug/so sánh (compare_systems.py, report.py, Print_barem_dict.py)
└── requirements.txt
```

`.env` (biến môi trường/API key, không commit) nằm ở **repo root** (không phải trong `backend/`) — cả `pipeline.py` (qua `python-dotenv`, tự tìm ngược lên thư mục cha) lẫn FastAPI (`app/core/config.py`) đều đọc từ đó.

## Cài đặt

Yêu cầu Python 3.9+.

```bash
cd backend
pip install -r requirements.txt
```

## Cấu hình

Tạo file `.env` ở **repo root** (cạnh `README.md` này, không phải trong `backend/`):

```
LLM_API_KEY=your_api_key_here
LLM_MODEL_NAME=qwen/qwen3-vl-32b-instruct
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL_API=https://openrouter.ai/api/v1/chat/completions
```

Pipeline hiện đang gọi model qua [OpenRouter](https://openrouter.ai). Có thể đổi sang provider/model khác miễn tương thích chuẩn OpenAI chat-completions.

Các tham số chấm điểm khác (bật/tắt Chain-of-Thought, số lần self-consistency voting, ngưỡng review giáo viên...) cấu hình trong dict `CFG` ở đầu [backend/pipeline.py](backend/pipeline.py):

```python
CFG = {
    "teacher_review_threshold": 0.65,
    "use_chain_of_thought": True,
    "cot_max_tokens_think": 600,
    "cot_max_tokens_decide": 500,
    "cot_self_consistency_n": 3,
    "heuristic_weight": 0.5,
    ...
}
```

## Định dạng dữ liệu đầu vào

Mỗi sample chấm điểm theo cấu trúc (xem đầy đủ tại [backend/structure/structure_input.txt](backend/structure/structure_input.txt)):

```jsonc
{
  "sample_id": "cau_1_001__HS_2",
  "student_index": 2,
  "ma_de": "1",
  "question_type": "fill_in_the_blank" | "multi_type",
  "question": {
    "text": "...",
    "parts": [{ "part_label": "a", "text": "...", "tables": [], "answer_slots": [...] }]
  },
  "question_number": 1,
  "max_score": 1.0,
  "student_answer": {
    "full_text": "...",
    "lines": [...],
    "tokens": [...],
    "tables": [],
    "visual_answers": []
  }
}
```

Cấu trúc barem chi tiết xem tại [backend/structure/structure_parem.txt](backend/structure/structure_parem.txt).

Pipeline tự nhận diện nếu input ở định dạng "Results" thô (OCR export) và tự convert sang định dạng sample chuẩn (`detect_results_format` + `convert_results_to_samples`), lưu bản convert ra `*.converted.json` để kiểm tra.

## Cách chạy

Chạy smoke test (không cần dữ liệu ngoài, kiểm tra nhanh logic chấm điểm):

```bash
cd backend
python pipeline.py --test
```

Chấm điểm một bộ input với barem tương ứng:

```bash
cd backend
python pipeline.py --input testing/input/test_1_HS.json --barem sample_parem.json --output-dir testing/output
```

Tham số CLI:

| Tham số | Mặc định | Mô tả |
|---|---|---|
| `--input`, `-i` | `testing/input/test_1_HS.json` | File dữ liệu bài làm học sinh |
| `--barem`, `-b` | `sample_parem.json` | File rubric/barem |
| `--output-dir`, `-o` | `testing/output` | Thư mục ghi kết quả |
| `--test` | — | Chạy smoke test thay vì chấm batch |

## Kết quả đầu ra

Ghi vào `backend/testing/output/`:
- `grading_results.json` — điểm chi tiết theo từng tiêu chí + reasoning của LLM cho từng sample.
- `token_usage.csv`, `prompt_tokens.csv`, `completion_tokens.csv` — thống kê token đã dùng.
- `latency.csv` — thời gian gọi LLM theo từng sample/criterion.
- `llm_reasoning.csv`, `llm_reasoning_per_cau.csv` — giải thích chấm điểm của LLM, phục vụ giáo viên review lại.
- `cost_summary.txt` — tổng chi phí ước tính (dùng cùng [backend/extract_token_cost.py](backend/extract_token_cost.py)).

## Công cụ hỗ trợ

- [backend/tool/compare_systems.py](backend/tool/compare_systems.py) — so sánh kết quả giữa các hệ thống chấm (Heuristic/Hybrid/Pure LLM/Advisory).
- [backend/tool/report.py](backend/tool/report.py) — sinh báo cáo tổng hợp từ kết quả chấm.
- [backend/tool/Print_barem_dict.py](backend/tool/Print_barem_dict.py) — in cấu trúc barem đã load để debug.
- [backend/scripts/convert_results_to_samples.py](backend/scripts/convert_results_to_samples.py) — convert độc lập định dạng Results sang sample (không qua pipeline).
- [backend/extract_token_cost.py](backend/extract_token_cost.py) — trích xuất và tổng hợp chi phí token từ log chạy pipeline.

Tài liệu thiết kế chi tiết hơn về luồng prompt, kỹ thuật prompting, và audit chất lượng chấm điểm: xem thư mục [backend/docs/](backend/docs/).

## Web app (FastAPI + React)

- `backend/app/` — FastAPI, gọi thẳng `pipeline.run_batch`/`grade_sample_advised` trong cùng tiến trình (`backend/app/services/grading_engine/wrapper.py`). Chấm điểm chạy trong một **subprocess riêng** (`python -m app.worker`), không dùng `BackgroundTasks`, để không bị cắt ngang nếu server API bị restart/kill giữa chừng. Trạng thái job lưu trong bảng `grading_jobs` (SQLite qua SQLAlchemy) — sống sót qua restart. Xem `backend/README.md` để biết chi tiết + endpoint.
- `frontend/` — React + TypeScript + Vite, nối vào API thật (không còn placeholder) — xem các route ở `frontend/README.md`: chấm cả lớp từ ảnh (`/pipeline`), chấm từ file JSON (`/`), soạn/quản lý barem (`/barem`, `/barem-library`), 3 module OCR riêng lẻ (`/ocr/*`). Xem `FE_ARCHITECTURE_OVERVIEW.md` cho cấu trúc thư mục `src/`.
- `FE_BE_INTEGRATION_GUIDE.md` — danh sách endpoint hiện có và cách frontend gọi backend.

**Trạng thái**: đã verify bằng `docker build`/`docker run` thật (2026-08-11) — health check, luồng tạo/theo dõi grading/pipeline job, và chấm 1 batch thật end-to-end (OCR + LLM) đều chạy được trong container. Chưa có auth.
