/** Types mirroring backend/ocr/app/main.py's response shapes. */

export type OcrTaskType = "short_text" | "long_text" | "code" | "table";

export interface Roi {
  x: number;
  y: number;
  w: number;
  h: number;
  type: string;
}

export interface RoiPageStats {
  dots?: number;
  segments?: number;
  blocks?: number;
  tables?: number;
  [key: string]: number | undefined;
}

export interface RoiPageResult {
  filename: string;
  width?: number;
  height?: number;
  rois?: Roi[];
  stats?: RoiPageStats;
  /** Present instead of the fields above when this one page failed. */
  error?: string;
}

export type AlignErrorType =
  | "FEATURE_ERROR"
  | "MATCH_ERROR"
  | "HOMOGRAPHY_ERROR"
  | "GEOMETRY_WARP_ERROR"
  | "HOUGH_SKEW_ERROR";

export interface AlignResult {
  ok: boolean;
  error: { error_type: AlignErrorType; reason: string } | null;
  matches: number;
  inliers: number;
  skew: number;
  width: number;
  height: number;
  image_base64: string | null;
}

export interface OcrResult {
  status: "completed" | "failed_all_samples";
  confidence: number;
  pass1_content: unknown;
  content: unknown;
  structure_warning: string | null;
}

export interface OcrHealth {
  status: string;
  module3_llm_configured: boolean;
}
