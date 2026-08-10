# Frontend (Autograding2026)

React + TypeScript + Vite, styling bằng **CSS Modules thuần** (không Tailwind,
không component library). Toàn bộ màu/spacing/shadow lấy từ CSS custom
properties khai trong [`src/styles/global.css`](src/styles/global.css) — có sẵn
2 bảng màu sáng/tối, đổi qua nút ở cuối sidebar (lưu trong `localStorage`).

## Hai backend phía sau

`vite.config.ts` proxy tới **2 service riêng biệt**, phải chạy song song:

| Prefix | Đích | Service |
| --- | --- | --- |
| `/api` | `http://localhost:8000` | API chấm điểm (`backend/app`, bọc `pipeline.py`) |
| `/ocr` | `http://localhost:8081` | Service OCR (`backend/ocr/app`) — prefix `/ocr` bị strip trước khi forward |

Sidebar hiển thị trạng thái kết nối của cả hai (poll 20s một lần qua
`src/hooks/useServiceHealth.ts`), nên nếu quên bật một service sẽ thấy ngay
chấm đỏ thay vì lỗi mù mờ khi bấm nút.

## Chạy local

```bash
# Terminal 1 — API chấm điểm
cd backend && uvicorn app.main:app --reload --port 8000

# Terminal 2 — service OCR (cần backend/ocr/requirements.txt)
cd backend/ocr && uvicorn app.main:app --reload --port 8081

# Terminal 3 — frontend
cd frontend && npm install && npm run dev
```

## Các màn hình

| Route | Nội dung |
| --- | --- |
| `/` | Dashboard: thống kê phiên chấm, form upload (kéo-thả) input + barem, danh sách phiên gần đây |
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
  modules/ocr/       RoiDetectView, AlignView, OcrView, OcrContent
  services/          api.ts (chấm điểm), ocrApi.ts (OCR)
  types/             grading.ts, ocr.ts — khớp với schema backend trả về
```

## Lưu ý về chi phí

Cả nút **“Bắt đầu chấm”** (`/`) và **“Nhận dạng chữ viết”** (`/ocr/text`) đều gọi
LLM thật và phát sinh chi phí API. Module 1 và Module 2 chỉ chạy OpenCV nên
miễn phí, bấm thoải mái.
