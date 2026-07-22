# Auto Grading System

Pipeline chấm điểm tự động bài thi/bài tập tự luận tiếng Việt, kết hợp **rubric (barem) có cấu trúc**, **so khớp heuristic** và **LLM (Chain-of-Thought + self-consistency voting)** để chấm điểm từng tiêu chí (criterion) trong bài làm của học sinh.

## Mục lục

- [Tổng quan](#tổng-quan)
- [Kiến trúc chấm điểm](#kiến-trúc-chấm-điểm)
- [Cấu trúc thư mục](#cấu-trúc-thư-mục)
- [Cài đặt](#cài-đặt)
- [Cấu hình](#cấu-hình)
- [Định dạng dữ liệu đầu vào](#định-dạng-dữ-liệu-đầu-vào)
- [Cách chạy](#cách-chạy)
- [Kết quả đầu ra](#kết-quả-đầu-ra)
- [Công cụ hỗ trợ](#công-cụ-hỗ-trợ)

## Tổng quan

Hệ thống nhận vào:
1. **Barem** (`sample_parem.json`) — rubric chấm điểm dạng cây, mỗi câu hỏi có các `criterion` con với điểm số, loại chấm (fill-in-blank, expected-value, table, visual...).
2. **Bài làm học sinh** (OCR hoặc dữ liệu đã trích xuất) — text, token, bảng, ảnh vẽ tay theo từng `part_label`.

Từ đó sinh ra điểm chi tiết theo từng tiêu chí, kèm giải thích (reasoning) của LLM, phục vụ việc review lại của giáo viên.

## Kiến trúc chấm điểm

Pipeline hỗ trợ nhiều "hệ thống" chấm điểm khác nhau, có thể so sánh chất lượng với nhau (xem [tool/compare_systems.py](tool/compare_systems.py)):

| Hệ thống | Mô tả |
|---|---|
| **Heuristic** | So khớp câu trả lời bằng rule-based (regex, normalize text, similarity, so khớp bảng/giá trị số) — không gọi LLM, nhanh và rẻ. |
| **Hybrid** | Kết hợp heuristic cho phần dễ chấm + LLM cho phần cần suy luận. |
| **Pure LLM (Chain-of-Thought)** | LLM tự suy luận (THINK) trước khi ra quyết định (DECIDE) qua 2 lần gọi tách biệt; có **self-consistency voting** (gọi lại N lần độc lập, lấy kết quả đa số) để giảm sai số do model nhỏ/flaky. |
| **Advisory (System 4: LLM + Heuristic Advisory)** | LLM chấm chính, heuristic đóng vai trò "cố vấn" cung cấp gợi ý/route câu hỏi, dùng cho batch chấm thật (`run_batch`). |

Các cơ chế chính trong [pipeline.py](pipeline.py):
- `flatten_criteria` — làm phẳng cây barem (`grading_rule` / `sub_questions` / `sub_criteria`) thành danh sách tiêu chí phẳng để chấm tuần tự, hỗ trợ nhóm `all_or_nothing`.
- `apply_question_routing` / `compute_routing_confidence` — định tuyến câu hỏi vào đúng chế độ chấm (fill-in-blank, expected-value, table, visual...).
- `grade_criterion` / `grade_criterion_advised` — chấm từng tiêu chí, chọn chế độ chấm phù hợp (`infer_criterion_grading_mode`).
- `call_llm_cot` / `_cot_single_pass` / `_vote_majority` — gọi LLM theo chế độ Chain-of-Thought với voting.
- `grade_sample_advised` / `run_batch` — chấm toàn bộ batch mẫu, xuất kết quả + log token/latency.
- `convert_results_to_samples` — tự nhận diện và convert định dạng "Results" (dữ liệu OCR thô) sang định dạng sample chuẩn của pipeline.

## Cấu trúc thư mục

```
.
├── pipeline.py              # Pipeline chấm điểm chính (CLI entry point)
├── sample_parem.json         # Barem/rubric mẫu
├── extract_token_cost.py     # Trích xuất chi phí token từ log/kết quả
├── input/                    # Dữ liệu đầu vào (ground truth, bài làm học sinh)
├── output/                   # Kết quả chấm điểm, log token/latency (sinh ra khi chạy)
├── docs/                     # Tài liệu thiết kế, báo cáo, hướng dẫn prompt
│   ├── PIPELINE_EXECUTION_FLOW.md
│   ├── LLM_PROMPT_FLOW*.md
│   ├── PROMPTING_TECHNIQUES_AND_METHODS.md
│   └── grading_audit_report.md
├── structure/                # Đặc tả cấu trúc dữ liệu input/barem (structure_input.txt, structure_parem.txt)
├── scripts/                  # Script tiện ích (convert_results_to_samples.py)
├── tool/                     # Công cụ debug/so sánh (compare_systems.py, report.py, Print_barem_dict.py)
├── Diagram/                  # Ảnh minh họa câu hỏi có hình vẽ (dùng cho chấm visual)
└── .env                      # Biến môi trường (API key) — KHÔNG commit, xem .env.example
```

## Cài đặt

Yêu cầu Python 3.9+.

```bash
pip install requests python-dotenv pandas
```

## Cấu hình

Tạo file `.env` ở thư mục gốc dựa trên `.env.example`:

```
LLM_API_KEY=your_api_key_here
LLM_MODEL_NAME=qwen/qwen3-vl-32b-instruct
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL_API=https://openrouter.ai/api/v1/chat/completions
```

Pipeline hiện đang gọi model qua [OpenRouter](https://openrouter.ai). Có thể đổi sang provider/model khác miễn tương thích chuẩn OpenAI chat-completions.

Các tham số chấm điểm khác (bật/tắt Chain-of-Thought, số lần self-consistency voting, ngưỡng review giáo viên...) cấu hình trong dict `CFG` ở đầu [pipeline.py](pipeline.py):

```python
CFG = {
    "use_llm": True,
    "teacher_review_threshold": 0.65,
    "use_chain_of_thought": True,
    "cot_max_tokens_think": 600,
    "cot_max_tokens_decide": 500,
    "cot_self_consistency_n": 3,
    ...
}
```

## Định dạng dữ liệu đầu vào

Mỗi sample chấm điểm theo cấu trúc (xem đầy đủ tại [structure/structure_input.txt](structure/structure_input.txt)):

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

Cấu trúc barem chi tiết xem tại [structure/structure_parem.txt](structure/structure_parem.txt).

Pipeline tự nhận diện nếu input ở định dạng "Results" thô (OCR export) và tự convert sang định dạng sample chuẩn (`detect_results_format` + `convert_results_to_samples`), lưu bản convert ra `*.converted.json` để kiểm tra.

## Cách chạy

Chạy smoke test (không cần dữ liệu ngoài, kiểm tra nhanh logic chấm điểm):

```bash
python pipeline.py --test
```

Chấm điểm một bộ input với barem tương ứng:

```bash
python pipeline.py --input input/test_input_perfect.json --barem sample_parem.json --output-dir output
```

Tham số CLI:

| Tham số | Mặc định | Mô tả |
|---|---|---|
| `--input`, `-i` | `input/test_input_perfect.json` | File dữ liệu bài làm học sinh |
| `--barem`, `-b` | `sample_parem.json` | File rubric/barem |
| `--output-dir`, `-o` | `output` | Thư mục ghi kết quả |
| `--test` | — | Chạy smoke test thay vì chấm batch |

## Kết quả đầu ra

Ghi vào `output/`:
- `grading_results.json` — điểm chi tiết theo từng tiêu chí + reasoning của LLM cho từng sample.
- `token_usage.csv`, `prompt_tokens.csv`, `completion_tokens.csv` — thống kê token đã dùng.
- `latency.csv` — thời gian gọi LLM theo từng sample/criterion.
- `llm_reasoning.csv`, `llm_reasoning_per_cau.csv` — giải thích chấm điểm của LLM, phục vụ giáo viên review lại.
- `cost_summary.txt` — tổng chi phí ước tính (dùng cùng [extract_token_cost.py](extract_token_cost.py)).

## Công cụ hỗ trợ

- [tool/compare_systems.py](tool/compare_systems.py) — so sánh kết quả giữa các hệ thống chấm (Heuristic/Hybrid/Pure LLM/Advisory).
- [tool/report.py](tool/report.py) — sinh báo cáo tổng hợp từ kết quả chấm.
- [tool/Print_barem_dict.py](tool/Print_barem_dict.py) — in cấu trúc barem đã load để debug.
- [scripts/convert_results_to_samples.py](scripts/convert_results_to_samples.py) — convert độc lập định dạng Results sang sample (không qua pipeline).
- [extract_token_cost.py](extract_token_cost.py) — trích xuất và tổng hợp chi phí token từ log chạy pipeline.

Tài liệu thiết kế chi tiết hơn về luồng prompt, kỹ thuật prompting, và audit chất lượng chấm điểm: xem thư mục [docs/](docs/).
