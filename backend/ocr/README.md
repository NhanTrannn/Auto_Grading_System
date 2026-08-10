# Backend — mmlab-auto-grading (OCR service, vendored)

> Vendored from https://github.com/camtran3506/mmlab-auto-grading (`backend/`
> subfolder of that repo) on 2026-08-10, copied as a snapshot (no git history,
> no submodule/subtree link). This is a **separate, standalone FastAPI
> service** — it does not import from or get imported by `pipeline.py`
> anywhere in this repo yet. Its `src/lib/roi`, `src/lib/ocr` frontend
> (React/TanStack) and the `qwenver15update-*.ipynb` notebooks referenced
> below were not copied — only the Python backend (`app/module1.py` = ROI
> detection, `app/module2.py` = template alignment, `app/module3.py` = Qwen3-VL
> handwriting OCR) and the two notebooks it directly ports (module1, module2).
> Run it as its own service (`uvicorn app.main:app --port 8081` from inside
> `backend/ocr/`, own venv per `requirements.txt`) — it is not wired into
> `backend/app/` (the grading API), but [`ocr_main.py`](ocr_main.py) (added
> separately from the vendored code) now assembles module1/2/3's output into
> the exact "Results" (`HS_N`-keyed) JSON `pipeline.py`'s
> `load_input()`/`convert_results_to_samples()` expects — see its module
> docstring for `roi_config.json`'s shape and usage. It imports
> `module1`/`module2`/`module3` in-process (no HTTP server needed). ROI-to-
> question mapping (`cau_key`/`task_type`) in `roi_config.json` is authored
> by hand — module1's auto-detection only gives generic geometry, not which
> barem question/part a region belongs to.
>
> **`module3.py` was also modified from the vendored original** (also on
> 2026-08-10): the original loaded `Qwen/Qwen3-VL-8B-Instruct` locally via
> `transformers`/`bitsandbytes` (4-bit, needs GPU/CUDA). It now calls
> Qwen3-VL-32B through an OpenAI-compatible chat-completions API instead
> (`_call_qwen_vl()` in `module3.py`), reading `LLM_API_KEY`/`LLM_MODEL_API`/
> `LLM_MODEL_NAME` from the same `.env` `backend/pipeline.py` already uses —
> no GPU/CUDA/torch/transformers/bitsandbytes/qwen_vl_utils needed anymore.
> The 2-pass extraction+self-reflection prompts/JSON-repair logic are
> unchanged from the vendored version. This has **not been run against the
> real API yet** — only syntax-checked, no live request made.

FastAPI service chạy `opencv-python` y hệt logic trong các notebook gốc
(`mmlab-module1-roi-detection.ipynb`, ...), thay cho các bản port TS thủ công
trong `src/lib/roi/*.ts`.

## Cài đặt (1 lần)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Chạy dev server

Frontend (`src/lib/roi/api.ts`, `api2.ts`, `src/lib/ocr/api3.ts`) gọi thẳng
backend bằng URL tuyệt đối tại **port 8081** (biến `VITE_BACKEND_PORT` nếu
bạn muốn đổi), KHÔNG qua Vite dev proxy — vì app dùng TanStack Start có
router riêng, dễ nuốt mất request `/api/...` trước khi tới được Vite proxy.
Nhớ chạy backend đúng port 8081 (hoặc set `VITE_BACKEND_PORT` khớp port bạn
chọn):

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8081
```

- Swagger UI để test thử bằng tay: http://localhost:8081/docs
- Health check: http://localhost:8081/health (có thêm field
  `module3_llm_configured` báo `.env` đã có đủ `LLM_API_KEY`/`LLM_MODEL_API`/
  `LLM_MODEL_NAME` chưa)

## Chạy song song với frontend

Cần **2 terminal**:

```bash
# Terminal 1 — backend
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8081

# Terminal 2 — frontend (Vite dev server, port 5173 mặc định)
npm run dev   # hoặc bun run dev
```

Nếu chạy backend ở port khác 8081, set `VITE_BACKEND_PORT=<port>` trước khi
chạy `npm run dev`.

## Endpoints hiện có

### `POST /module1/roi`

Nhận `multipart/form-data`, field `files` (1 hoặc nhiều ảnh .jpg/.png).
Trả về mảng JSON, mỗi phần tử tương ứng 1 ảnh, đúng thứ tự đã gửi lên:

```json
[
  {
    "filename": "page_1.jpg",
    "width": 2480,
    "height": 3508,
    "rois": [{ "x": 100, "y": 200, "w": 300, "h": 80, "type": "fill_in_blank" }],
    "stats": { "dots": 120, "segments": 6, "blocks": 2, "tables": 1 }
  }
]
```

Nếu 1 ảnh lỗi (không đọc được / thuật toán lỗi), phần tử tương ứng sẽ có
dạng `{ "filename": "...", "error": "..." }` thay vì báo lỗi cả batch.

Shape này khớp 1:1 với type `PageResult` trong `src/lib/roi/module1.ts`,
nên frontend (`src/lib/roi/api.ts` → `src/routes/module-1.tsx`) chỉ cần
`fetch` và dùng thẳng, không cần transform.

### `POST /module2/align`

Nhận `multipart/form-data` với 2 field: `template` (ảnh đề mẫu, .jpg/.png)
và `student` (ảnh bài làm học sinh cùng trang). Chạy đúng pipeline
`mmlab-module2-alignment.ipynb` (cell 7 `verify_homography`, cell 8
`check_image_skew`, cell 9 `module_1_align_images` — đã đối chiếu trực tiếp
với file `.ipynb` gốc) bằng opencv-python thật (`cv2.ORB_create` +
`cv2.DescriptorMatcher` Hamming + `cv2.findHomography` RANSAC mặc định +
`cv2.warpPerspective` với `borderValue=(255,255,255)`) — xem
`backend/app/module2.py`.

```json
{
  "ok": true,
  "error": { "error_type": "HOUGH_SKEW_ERROR", "reason": "..." } | null,
  "matches": 188,
  "inliers": 75,
  "skew": 0.4,
  "width": 2480,
  "height": 3508,
  "image_base64": "<PNG base64 của ảnh đã align, kích thước = template>"
}
```

`error_type` có thể là: `FEATURE_ERROR`, `MATCH_ERROR`, `HOMOGRAPHY_ERROR`,
`GEOMETRY_WARP_ERROR`, `HOUGH_SKEW_ERROR` (giống enum `ErrorType` trong
`src/lib/roi/module2.ts`). Khi `error` khác `null`, `image_base64` vẫn được
trả về (là ảnh đã warp, chỉ là không đạt kiểm tra chất lượng) để frontend
lưu lại phục vụ debug, giống hành vi notebook gốc.

Việc crop ROI từ ảnh đã align không chạy qua backend — đó chỉ là slice mảng
pixel theo toạ độ có sẵn (không phải thuật toán CV), nên vẫn làm ở client
(`src/lib/roi/module2.ts#cropRoi`), gọi từ `src/lib/roi/api2.ts` →
`src/routes/module-2.tsx`.

### `POST /module3/ocr`

Nhận `multipart/form-data` với field `image` (1 ảnh crop .jpg/.png), `task_type`
(`short_text` | `long_text` | `code` | `table`), và `n_rows`/`n_cols` (bắt buộc
nếu `task_type=table`). Chạy pipeline 2-pass self-reflection (prompt/JSON-repair
logic port y hệt 3 notebook gốc — `qwenver15update-shorttext.ipynb`,
`ocr-longtext.ipynb`, `qwenver15update-table.ipynb`) nhưng gọi **Qwen3-VL-32B
qua API** (OpenAI-compatible chat completions, vd OpenRouter) thay vì load
model local — xem `_call_qwen_vl()` trong `backend/ocr/app/module3.py`.

```json
{
  "status": "completed" | "failed_all_samples",
  "confidence": 1.0,
  "pass1_content": { "lines": ["..."] } | null,
  "content": { "lines": ["..."] },
  "structure_warning": "Sai số hàng: kỳ vọng 3, nhận được 2" | null
}
```

Cần `LLM_API_KEY`/`LLM_MODEL_API`/`LLM_MODEL_NAME` trong `.env` (cùng file
`.env` mà `backend/pipeline.py` dùng) — không cần GPU/CUDA nữa. Kiểm tra qua
field `module3_llm_configured` ở `/health`. Nếu `.env` thiếu cấu hình,
endpoint trả về HTTP 503 kèm lý do thay vì lỗi mù mờ.

Frontend gọi qua `src/lib/ocr/api3.ts` → `src/routes/module-3.tsx`, cùng
pattern gọi thẳng backend như Module 1/2 (không qua Vite proxy).

## Việc còn lại (chưa làm trong lần này)

- Cả Module 1, 2 và 3 đã port xong sang FastAPI (opencv-python / transformers
  thật), không còn module nào gọi kiến trúc "tưởng tượng" do Lovable tự thêm
  (opencv.js port tay, hay vLLM/Ollama qua HTTP).
- Có thể xoá các file TS re-implement không còn ai gọi thuật toán từ chúng
  nữa (chỉ giữ lại phần types/notebook-JSON export nếu frontend còn dùng):
  `src/lib/roi/orb.ts`, `src/lib/roi/homography.ts`, `src/lib/roi/worker2.ts`
  (Module 2), `src/lib/roi/worker.ts`, `src/lib/roi/imageops.ts` (Module 1)
  nếu không còn ai import.
- `src/lib/ocr/ocr.functions.ts` (server function gọi vLLM/Ollama) đã bị xoá,
  thay bằng `src/lib/ocr/api3.ts` gọi thẳng `/module3/ocr`.
- Chưa port prompt "diagram" (có trong cả 3 notebook nhưng không được dùng ở
  pipeline chính, và frontend hiện không có `TaskType="diagram"`) — nếu sau
  này cần, prompt đã có sẵn trong notebook, chỉ cần thêm vào
  `backend/app/module3.py#get_ocr_prompt` và `src/lib/ocr/prompts.ts`.
- `ocr-longtext.ipynb` có 1 bug nhỏ ở Pass 1 của `run_qwen_inference()`: biến
  `prompt_type` bị gán cứng `"code"` thay vì dùng `task["type"]` (`"long_text"`).
  Bản port này **không** tái tạo bug đó — dùng đúng prompt `"long_text"` cho
  task `long_text`. Notebook đó cũng có cơ chế few-shot bằng 1 ảnh mẫu thật
  (`FEW_SHOT_EXAMPLES`/`build_messages_with_example()`) trỏ tới 1 đường dẫn
  Kaggle cụ thể — không portable nên **chưa** đưa vào bản port này.
