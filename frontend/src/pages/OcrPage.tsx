import { useNavigate, useParams } from "react-router-dom";

import Badge from "@/components/core/Badge";
import { IconLayers, IconScan, IconText } from "@/components/core/Icon";
import PageHeader from "@/components/core/PageHeader";
import Tabs, { type TabItem } from "@/components/core/Tabs";
import { useServiceHealth } from "@/hooks/useServiceHealth";
import AlignView from "@/modules/ocr/AlignView";
import OcrView from "@/modules/ocr/OcrView";
import RoiDetectView from "@/modules/ocr/RoiDetectView";

type ModuleId = "roi" | "align" | "text";

const TABS: TabItem<ModuleId>[] = [
  {
    id: "roi",
    label: "Module 1 · Phát hiện vùng",
    hint: "OpenCV — tìm ROI trên trang",
    icon: <IconScan size={16} />,
  },
  {
    id: "align",
    label: "Module 2 · Căn chỉnh ảnh",
    hint: "ORB + RANSAC homography",
    icon: <IconLayers size={16} />,
  },
  {
    id: "text",
    label: "Module 3 · Nhận dạng chữ",
    hint: "Qwen3-VL, 2 lượt self-reflection",
    icon: <IconText size={16} />,
  },
];

const DESCRIPTION: Record<ModuleId, string> = {
  roi: "Chạy bộ phát hiện vùng trả lời của Module 1 trên ảnh đề/bài làm và xem trực tiếp các ROI được khoanh trên ảnh — dùng để dựng roi_config.json cho bridge.py.",
  align: "Đưa ảnh bài làm của học sinh về đúng khung của ảnh đề mẫu, để toạ độ ROI dùng chung được cho mọi bài.",
  text: "Nhận dạng chữ viết tay trên một vùng đã cắt, trả về JSON dùng thẳng cho pipeline chấm điểm.",
};

function isModuleId(value: string | undefined): value is ModuleId {
  return value === "roi" || value === "align" || value === "text";
}

export default function OcrPage() {
  const navigate = useNavigate();
  const { moduleId } = useParams<{ moduleId: string }>();
  const active: ModuleId = isModuleId(moduleId) ? moduleId : "roi";
  const health = useServiceHealth();

  return (
    <>
      <PageHeader
        eyebrow={
          <>
            <IconScan size={13} />
            Pipeline OCR
          </>
        }
        title="Xử lý ảnh bài làm"
        description={DESCRIPTION[active]}
        actions={
          health.ocr === "down" ? (
            <Badge tone="danger">Chưa chạy service OCR (cổng 8081)</Badge>
          ) : health.ocr === "up" && health.ocrLlmConfigured === false ? (
            <Badge tone="warning">Module 3 chưa cấu hình LLM</Badge>
          ) : null
        }
      />

      <div style={{ marginBottom: "var(--space-5)" }}>
        <Tabs items={TABS} active={active} onChange={(id) => navigate(`/ocr/${id}`)} />
      </div>

      {active === "roi" && <RoiDetectView />}
      {active === "align" && <AlignView />}
      {active === "text" && <OcrView />}
    </>
  );
}
