import type { JobStatus } from "./grading";
import type { OcrTaskType } from "./ocr";

/** `task_type` accepted by roi_config.json — module3's four, plus "diagram". */
export type RoiTaskType = OcrTaskType | "diagram";

export interface RoiConfigEntry {
  cau_key: string;
  /** 1-based page of the exam this region sits on. Absent means page 1. */
  page?: number;
  x: number;
  y: number;
  w: number;
  h: number;
  task_type: RoiTaskType;
  n_rows?: number;
  n_cols?: number;
}

export interface RoiConfig {
  ma_de?: string;
  rois?: RoiConfigEntry[];
}

/* ── Upload inventory ─────────────────────────────────────────────────── */

export interface TemplatePage {
  page: number;
  filename: string;
}

export interface UploadStudent {
  hs_key: string;
  folder: string;
  page_count: number;
}

export interface UploadMaDe {
  ma_de: string;
  student_count: number;
  students: UploadStudent[];
}

export interface UploadInventory {
  upload_id: string;
  template_pages: TemplatePage[];
  ma_de_list: UploadMaDe[];
}

/* ── Jobs ─────────────────────────────────────────────────────────────── */

/** "ocr" while OCR'ing pages, "grading" while pipeline.py runs, "done" after. */
export type PipelineStage = "ocr" | "grading" | "done";

export interface PipelineJobCreated {
  job_id: string;
  status: JobStatus;
  student_count: number;
  roi_count: number;
  student_map: Record<string, string>;
}

export interface PipelineJobStatus {
  job_id: string;
  status: JobStatus;
  stage: PipelineStage | null;
  progress_done: number;
  progress_total: number;
  progress_message: string | null;
  student_count: number;
  roi_count: number;
  ma_de: string | null;
  barem_name: string | null;
  error: string | null;
  created_at: string;
}

export interface JobLog {
  text: string;
  next_offset: number;
  size: number;
}

/* ── OCR result (intermediate Results-format JSON) ────────────────────── */

export interface OcrCauEntry {
  status: string;
  type?: string;
  image_path?: string;
  content?: { lines?: string[]; table_extracted?: Record<string, unknown>[]; error?: string };
}

/** `{ma_de, HS_1: {Cau_01: {...}}, ...}` as produced by ocr_main.py. */
export type OcrResultsFile = Record<string, string | Record<string, OcrCauEntry>>;
