# OCR modules (vendored)

> Vendored from https://github.com/camtran3506/mmlab-auto-grading (`backend/`
> subfolder of that repo) on 2026-08-10, copied as a snapshot (no git history,
> no submodule/subtree link). Its `src/lib/roi`, `src/lib/ocr` frontend
> (React/TanStack) and the `qwenver15update-*.ipynb` notebooks referenced
> below were not copied — only the Python backend (`ocr_modules/module1.py` =
> ROI detection, `ocr_modules/module2.py` = template alignment,
> `ocr_modules/module3.py` = Qwen3-VL handwriting OCR) and the two notebooks it
> directly ports (module1, module2).
>
> **This is no longer a standalone service.** It arrived as its own FastAPI app
> on port 8081, with the three modules in a package named `app` — which
> collided with `backend/app` and made the OCR code impossible to import from
> the grading API. That package is now `ocr_modules/`, the vendored
> `app/main.py` is gone, and its three endpoints live in
> `backend/app/api/routes/ocr.py` under `/api/v1/ocr/*`, served by the one
> backend on port 8000. Dependencies come from `backend/requirements.txt`;
> there is no separate venv or requirements file here anymore.
>
> Two extra scripts (added separately from the vendored code, not part of the
> original repo) bridge these modules to `pipeline.py`:
> - [`ocr_main.py`](ocr_main.py) — pure OCR connector. Imports
>   `module1`/`module2`/`module3` in-process (no HTTP server needed): aligns
>   each student page to a template (module2), crops every ROI, OCRs it
>   (module3), and assembles the exact "Results" (`HS_N`-keyed) JSON
>   `pipeline.py`'s `load_input()`/`convert_results_to_samples()` expects —
>   see its module docstring for `roi_config.json`'s shape. ROI-to-question
>   mapping (`cau_key`/`task_type`) in `roi_config.json` is authored by hand —
>   module1's auto-detection only gives generic geometry, not which barem
>   question/part a region belongs to.
> - [`main.py`](main.py) — OCR-to-grading bridge. Calls `ocr_main.py`'s
>   `build_results_json()` to produce the Results JSON, then shells out to
>   `../pipeline.py` (subprocess, same interpreter) to grade it, so 1 command
>   goes from student page images all the way to `grading_results.json`/
>   `student_summary.json`.
>
> **`module3.py` was also modified from the vendored original** (also on
> 2026-08-10): the original loaded `Qwen/Qwen3-VL-8B-Instruct` locally via
> `transformers`/`bitsandbytes` (4-bit, needs GPU/CUDA). It now calls
> Qwen3-VL-32B through an OpenAI-compatible chat-completions API instead
> (`_call_qwen_vl()` in `module3.py`), reading `LLM_API_KEY`/`LLM_MODEL_API`/
> `LLM_MODEL_NAME` from the same `.env` `backend/pipeline.py` already uses —
> no GPU/CUDA/torch/transformers/bitsandbytes/qwen_vl_utils needed anymore.
> The 2-pass extraction+self-reflection prompts/JSON-repair logic are
> unchanged from the vendored version. It **has** been run against the real API
> since (2026-08-10, one handwriting crop): the call path works end to end, and
> the two things worth knowing are that pass 2 frequently returns pass 1
> unchanged, and that the model silently "corrects" what a student wrote — it
> read a required literal `'giả định sai'` as `'gia tri sai'`. Check OCR text
> against the crop on the review screen before trusting a grade.

Ba module chạy `opencv-python` y hệt logic trong các notebook gốc
(`mmlab-module1-roi-detection.ipynb`, ...), thay cho các bản port TS thủ công
trong `src/lib/roi/*.ts`.

## Cách chạy

Không có server riêng ở đây. Cài đặt và chạy đúng như backend chính:

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

- Swagger UI: http://localhost:8000/docs
- Health check: http://localhost:8000/api/v1/health — field `llm_configured`
  báo `.env` đã có đủ `LLM_API_KEY`/`LLM_MODEL_API`/`LLM_MODEL_NAME` chưa

Dùng trực tiếp bằng dòng lệnh, không qua HTTP:

```bash
cd backend/ocr
python ocr_main.py --config roi_config.json --output results.json   # chỉ OCR
python main.py --config roi_config.json --output results.json \
    --barem ../sample_parem.json --grade-output-dir ../testing/output   # OCR + chấm
```

## Module 1 khoanh cái gì — và cần ảnh cỡ nào

Module 1 chạy trên **trang đề trắng** và tìm **chỗ để học sinh làm bài**, không
phải tìm chữ. Cụ thể là hai thứ: dòng chấm `………` và bảng rỗng. Chữ in sẵn bị
cố tình bỏ qua — `filter_and_pad_tables` loại mọi bảng có mật độ chữ cao (đó là
bảng đề bài) và chỉ giữ bảng trống (bảng cho học sinh điền). Vùng được nới rộng
hơn chính dòng chấm vì học sinh viết đè lên và phía trên nó.

Toạ độ khai một lần trên đề trắng rồi dùng cho mọi học sinh: module 2 kéo từng
trang bài làm về khớp khung đề, nên cùng một toạ độ cắt trúng chỗ với tất cả,
kể cả khi đặt giấy lệch lúc scan.

**Độ phân giải là điều kiện tiên quyết, không phải chuyện tinh chỉnh tham số.**
Đo trên repo này: crop *một câu* của bài làm thật là `1795x1357`, trong khi cả
*một trang* đề mẫu (`testing/Mã đề 1 - Bản clean chưa làm/`) chỉ có `595x816` —
bản render ~72 DPI. Ở cỡ đó, dòng chấm in sẵn chỉ còn vệt 1–2px, phần lớn dẹt
nên bị bộ lọc "chấm phải vuông" loại; cả dòng còn chưa tới 4 chấm hợp lệ, dưới
mức tối thiểu để thành một chuỗi. Thông tin mất khỏi pixel, không ngưỡng nào
lấy lại được. Cùng thuật toán ấy chạy trên ảnh `1795x1357` thì khoanh chính xác
từng dòng kẻ.

Vậy nên: **xuất ảnh đề mẫu ở 200–300 DPI**. Nó không chỉ ảnh hưởng Module 1 —
module 2 căn trang bằng đặc trưng ORB (template nét hơn thì căn chuẩn hơn), và
crop đưa vào module 3 cắt theo toạ độ trên template (template mờ thì crop lệch,
chữ càng dễ đọc sai).

### Những chỗ đã sửa trong `module1.py`

Bốn ngưỡng vốn là số pixel tuyệt đối, chỉ đúng ở đúng một độ phân giải:

| | Trước | Sau |
|---|---|---|
| Padding vùng | `60/20/50/100` px cứng | bội số của `avg_h` (đơn vị sẵn có của file) |
| Lọc kích thước chấm | `≤ 10px` cứng | theo tỉ lệ chiều cao trang |
| Padding bảng | `50px` cứng | theo tỉ lệ trang |
| Khoảng cách chấm tối đa | `2.5 × avg_h` | `4.5` — đo thực tế khoảng cách ~3× |

Thêm hai bộ lọc mới ở mức đoạn: rộng ≥4% trang, và **dài/cao ≥18**. Cái thứ hai
là thứ tách được dòng chấm thật khỏi chuỗi ghép nhầm từ dấu thanh tiếng Việt —
dòng chấm in sẵn phẳng tuyệt đối và cao đúng một chấm (đo được ≥24.5), còn chuỗi
sinh từ chữ thì ngắn và cao hơn vì dấu nặng/dấu chấm nằm lệch nhau (≤12.5).
Trang nhỏ hơn `MIN_WORKING_HEIGHT` được nội suy lên trước khi dò, toạ độ chia
ngược về hệ ảnh gốc.

Đo trên ảnh độ phân giải thật, số vùng thừa giảm một nửa: `HS10` 52→26 vùng,
`HS21` 61→38, khung cũng gọn hơn (cao trung bình 7.1%→5.8% ảnh).

**Còn lỗi chưa sửa**: với `HS18_Cau_15c.jpg` và `HS19_Cau_15c.jpg`, cả bản cũ
lẫn bản mới đều gộp tất cả thành **một khung phủ ~97% ảnh**. Chưa rõ nguyên nhân.

## Endpoints hiện có

Đường dẫn đầy đủ có tiền tố `/api/v1/ocr` (vd
`POST /api/v1/ocr/module1/roi`).

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
`ocr_modules/module2.py`.

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
model local — xem `_call_qwen_vl()` trong `ocr_modules/module3.py`.

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
field `llm_configured` ở `/api/v1/health`. Nếu `.env` thiếu cấu hình,
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
  `ocr_modules/module3.py#get_ocr_prompt` và `src/lib/ocr/prompts.ts`.
- `ocr-longtext.ipynb` có 1 bug nhỏ ở Pass 1 của `run_qwen_inference()`: biến
  `prompt_type` bị gán cứng `"code"` thay vì dùng `task["type"]` (`"long_text"`).
  Bản port này **không** tái tạo bug đó — dùng đúng prompt `"long_text"` cho
  task `long_text`. Notebook đó cũng có cơ chế few-shot bằng 1 ảnh mẫu thật
  (`FEW_SHOT_EXAMPLES`/`build_messages_with_example()`) trỏ tới 1 đường dẫn
  Kaggle cụ thể — không portable nên **chưa** đưa vào bản port này.
