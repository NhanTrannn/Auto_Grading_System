# Lỗi Hiện Tại Và Hướng Cải Tiến Cho Pipeline

Tài liệu này tổng hợp các điểm yếu quan sát được từ luồng chấm bài hiện tại trong `PIPELINE_EXECUTION_FLOW.md` và đề xuất các cải tiến ưu tiên.

## 1. Nhìn tổng quan

Pipeline hiện tại đi theo hướng phân tầng:

- `grade_sample()` điều phối mức sample.
- `route_question()` xác định loại câu hỏi.
- `grade_criterion()` chọn chiến lược chấm theo criterion.
- Các grader chuyên biệt xử lý output, expected value, table, visual.
- Phần LLM chỉ là nhánh fallback hoặc nhánh hỗ trợ diagnosis.

Đây là kiến trúc hợp lý cho bài chấm rubric-based, nhưng phần routing và fallback hiện vẫn có các rủi ro về độ ổn định, độ bao phủ và khả năng mở rộng.

## 2. Các lỗi hoặc rủi ro chính

### 2.1 Routing dựa nhiều vào heuristic cứng

`route_question()` đang ưu tiên một chuỗi rule như visual, table, program trace, fill blank, essay, mixed, fallback unknown. Cách này dễ chạy tốt với mẫu quen thuộc nhưng dễ sai khi đề bài được diễn đạt khác đi, hoặc khi một câu có nhiều dấu hiệu chồng lấn.

Hệ quả:

- Gán sai `question_type`.
- Đẩy criterion vào grader không phù hợp.
- Tăng số trường hợp phải review thủ công.

### 2.2 `grade_criterion()` có nhiều nhánh fallback về review

Trong luồng hiện tại, nếu không match rõ ràng `expected_output`, `expected_value`, `table`, `visual`, criterion sẽ rơi vào `needs_llm_or_teacher_review`.

Hệ quả:

- Tỷ lệ bỏ sót tự động hóa cao ở các câu biên.
- Khó đo chất lượng thật của LLM vì nhiều case không đi qua LLM.

### 2.3 Chấm visual chưa có đường xử lý tự động

Nhánh visual hiện chủ yếu trả về cờ cần review hoặc vision LLM.

Hệ quả:

- Các câu hình vẽ/biểu đồ/flowchart gần như chưa có pipeline chấm tự động hoàn chỉnh.
- Các đề nhiều kênh thông tin sẽ phụ thuộc mạnh vào người chấm.

### 2.4 Thiếu chuẩn hóa input trước khi chấm

Pipeline phụ thuộc mạnh vào cấu trúc `sample`, `teacher_barem`, `student_answer`, `question.text`, `part_label`. Nếu dữ liệu đầu vào lệch schema hoặc thiếu trường, kết quả sẽ dễ rơi sang warning/review.

Hệ quả:

- Khó mở rộng sang bộ dữ liệu khác.
- Dễ phát sinh lỗi ngầm khi đổi format input.

### 2.5 LLM chưa được dùng như một thành phần có kiểm soát chặt

Theo flow hiện tại, LLM chỉ xuất hiện ở mức hỗ trợ diagnosis/fallback, nhưng chưa thấy cơ chế chặt như:

- JSON schema bắt buộc.
- retry có kiểm soát.
- few-shot exemplar theo từng loại câu.
- confidence threshold để quyết định có dùng kết quả hay không.

Hệ quả:

- Khó đảm bảo output ổn định.
- Nếu gọi LLM nhiều hơn trong tương lai, rủi ro format và tính nhất quán sẽ tăng.

## 3. Các cải tiến ưu tiên

### 3.1 Chuẩn hóa schema đầu vào/đầu ra

Nên cố định schema cho `sample`, `routing`, `criterion_result`, `sample_result`.

Lợi ích:

- Giảm lỗi do thiếu field.
- Dễ validate trước và sau mỗi bước.
- Dễ viết test và benchmark.

### 3.2 Tách rõ rule-based và model-based

Nên đặt tiêu chí rõ:

- Rule-based cho câu hỏi có cấu trúc rõ như output exact, expected value, table.
- LLM cho câu mở, rubric mơ hồ, hoặc trường hợp đặc thù.

Lợi ích:

- Giảm chi phí LLM.
- Tăng độ ổn định.
- Dễ giải thích kết quả chấm.

### 3.3 Thêm confidence score cho routing

`route_question()` nên trả về confidence rõ ràng và ngưỡng hành động:

- Confidence cao: chấm tự động.
- Confidence trung bình: cho LLM hỗ trợ.
- Confidence thấp: teacher review.

Lợi ích:

- Giảm lỗi route sai.
- Có cơ sở để đo coverage của pipeline.

### 3.4 Bổ sung few-shot prompting cho nhánh LLM

Nếu LLM được dùng để chấm criterion, nên đưa vào:

- 1 đến 3 ví dụ chuẩn theo mỗi `question_type`.
- Một prompt cố định yêu cầu output JSON duy nhất.
- Retry nếu output không parse được.

Lợi ích:

- Tăng tính ổn định của output.
- Giảm hallucination và câu trả lời ngoài schema.

### 3.5 Dùng validate + retry ở mọi điểm biên

Các bước nên có validation:

- Sau routing.
- Sau grading từng criterion.
- Sau aggregate final sample.

Nếu invalid thì retry hoặc đẩy sang review.

Lợi ích:

- Giảm lỗi âm thầm.
- Dễ debug khi một criterion sai.

## 4. Cải tiến theo từng loại câu

### 4.1 Fill blank / expected output

Nên ưu tiên matching xác định trước:

- normalize text.
- token matching.
- fuzzy matching có ngưỡng.

LLM chỉ dùng khi có nhiều biến thể hợp lệ.

### 4.2 Essay / short answer

Nên dùng rubric-based scoring có cấu trúc:

- tách tiêu chí.
- gán điểm từng tiêu chí.
- LLM chỉ đóng vai trò giải thích hoặc hỗ trợ nếu rubric mơ hồ.

### 4.3 Code

Nên tách thành 2 lớp:

- chạy test/sandbox để kiểm tra đúng sai logic.
- dùng LLM để chấm style, giải thích, hoặc phản hồi bổ sung.

### 4.4 Visual

Nên có riêng Vision LLM hoặc module OCR/diagram parser nếu muốn tự động hóa thực sự.

## 5. Bộ tối ưu nên làm trước

1. Chuẩn hóa schema và validator cho input/output.
2. Thêm confidence score cho routing.
3. Thêm few-shot prompt template cho nhánh LLM.
4. Giới hạn LLM chỉ cho các case không thể rule-based.
5. Thêm log và metric để đo tỷ lệ route sai, tỷ lệ review, và độ lệch điểm so với teacher.

## 6. Kết luận ngắn

Pipeline hiện tại đã có cấu trúc tốt cho chấm rubric theo tầng, nhưng đang thiên về heuristic và review fallback nhiều hơn là tự động hóa có kiểm soát. Hướng tối ưu tốt nhất là chuẩn hóa schema, tăng độ chắc của routing, và chỉ dùng LLM ở những điểm cần suy luận ngữ nghĩa thật sự.
