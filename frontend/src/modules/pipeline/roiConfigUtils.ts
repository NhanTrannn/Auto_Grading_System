import type { RoiConfigEntry, RoiTaskType } from "@/types/pipeline";

const REQUIRED_FIELDS: (keyof RoiConfigEntry)[] = ["cau_key", "x", "y", "w", "h", "task_type"];

const VALID_TASK_TYPES: RoiTaskType[] = ["short_text", "long_text", "code", "table", "diagram"];

export const TASK_TYPE_LABEL: Record<RoiTaskType, string> = {
  short_text: "Chữ ngắn",
  long_text: "Đoạn dài",
  code: "Mã C++",
  table: "Bảng",
  diagram: "Hình vẽ",
};

/**
 * Same rules as `_validate_rois` in backend/app/api/routes/pipeline.py, run
 * client-side so a bad region list is caught while it can still be fixed in
 * the editor rather than as a 400 on submit.
 */
export function validateRois(rois: RoiConfigEntry[], pageCount: number): string[] {
  const issues: string[] = [];
  if (rois.length === 0) {
    issues.push("Chưa khai vùng trả lời nào.");
    return issues;
  }

  const seen = new Set<string>();
  rois.forEach((roi, index) => {
    const label = `Vùng ${index + 1} (${roi.cau_key || "chưa gán"})`;

    const missing = REQUIRED_FIELDS.filter(
      (f) => roi[f] === undefined || roi[f] === null || roi[f] === "",
    );
    if (missing.length) issues.push(`${label} thiếu: ${missing.join(", ")}`);

    if (roi.task_type && !VALID_TASK_TYPES.includes(roi.task_type)) {
      issues.push(`${label} có task_type không hợp lệ: '${roi.task_type}'`);
    }
    if (roi.task_type === "table" && (!roi.n_rows || !roi.n_cols)) {
      issues.push(`${label} là bảng nên bắt buộc có số hàng và số cột.`);
    }

    const page = roi.page ?? 1;
    if (page < 1 || page > pageCount) {
      issues.push(`${label} trỏ tới trang ${page} nhưng đề mẫu chỉ có ${pageCount} trang.`);
    }

    if (roi.cau_key) {
      if (seen.has(roi.cau_key)) issues.push(`${label} trùng cau_key với một vùng trước đó.`);
      seen.add(roi.cau_key);
    }
  });

  return issues;
}

export function countByTaskType(rois: RoiConfigEntry[]): Record<string, number> {
  const counts: Record<string, number> = {};
  rois.forEach((roi) => {
    counts[roi.task_type] = (counts[roi.task_type] ?? 0) + 1;
  });
  return counts;
}

/**
 * How many OCR calls the run will make: every non-diagram region of every
 * student (diagram crops are saved as images, never sent to module3).
 * Module 3 itself runs two passes per call, so the real request count is
 * double this.
 */
export function estimateOcrCalls(rois: RoiConfigEntry[], studentCount: number): number {
  return rois.filter((roi) => roi.task_type !== "diagram").length * studentCount;
}

/** Accept a hand-written roi_config.json file's `rois` array. */
export function parseRoiConfigFile(text: string): RoiConfigEntry[] {
  const parsed = JSON.parse(text);
  const rois = Array.isArray(parsed) ? parsed : parsed?.rois;
  if (!Array.isArray(rois)) {
    throw new Error("File không có mảng 'rois'.");
  }
  return rois as RoiConfigEntry[];
}
