/**
 * Render the LaTeX in a barem text field, so the author can see the formula
 * they typed instead of its source.
 *
 * This is a proofreading aid and nothing more. `pipeline.py` never parses
 * LaTeX — `question.text` reaches the grading prompt byte-for-byte and the LLM
 * reads the notation directly — so what is rendered here has no bearing on the
 * score. What it buys is catching `\mathb{R}` or an unclosed brace *before* a
 * paid run, which nothing else in the system would report.
 *
 * A broken formula is therefore shown as an explicit error rather than hidden:
 * silently falling back to the raw source would defeat the only reason this
 * component exists. Each segment is rendered independently so one bad formula
 * doesn't blank out the rest of the question.
 */
import katex from "katex";
import "katex/dist/katex.min.css";
import { useMemo } from "react";

import { splitMath, type MathSegment } from "./mathText";
import styles from "./MathPreview.module.css";

interface MathPreviewProps {
  source: string;
}

interface RenderedSegment {
  kind: MathSegment["kind"];
  /** KaTeX output, or null when this segment is plain text / failed. */
  html: string | null;
  /** Parse error message; null when the segment rendered. */
  error: string | null;
  value: string;
}

function renderSegment(segment: MathSegment): RenderedSegment {
  if (segment.kind === "text") {
    return { kind: "text", html: null, error: null, value: segment.value };
  }
  try {
    return {
      kind: segment.kind,
      html: katex.renderToString(segment.value, {
        displayMode: segment.kind === "display",
        // Errors are the point of this component — surface them as our own
        // message rather than letting KaTeX paint the source red inline.
        throwOnError: true,
        strict: false,
      }),
      error: null,
      value: segment.value,
    };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    // KaTeX prefixes every message with "KaTeX parse error: "; the teacher
    // already knows which tool complained.
    return {
      kind: segment.kind,
      html: null,
      error: message.replace(/^KaTeX parse error:\s*/, ""),
      value: segment.value,
    };
  }
}

export default function MathPreview({ source }: MathPreviewProps) {
  const segments = useMemo(() => splitMath(source).map(renderSegment), [source]);
  const errors = segments.filter((segment) => segment.error).length;
  // The panel is shown as soon as an unescaped `$` exists, so it is normal to
  // be here with nothing parsed yet — mid-typing, or with a `$` never closed.
  const unclosed = segments.every((segment) => segment.kind === "text");

  return (
    <div className={styles.wrapper}>
      <div className={styles.head}>
        <span className={styles.title}>Xem trước công thức</span>
        {unclosed ? (
          <span className={styles.badWaiting}>Chưa đóng $</span>
        ) : errors > 0 ? (
          <span className={styles.badError}>{errors} công thức lỗi</span>
        ) : (
          <span className={styles.badOk}>Đọc được</span>
        )}
      </div>

      <div className={styles.body}>
        {segments.map((segment, index) => {
          if (segment.kind === "text") {
            return (
              <span key={index} className={styles.text}>
                {segment.value}
              </span>
            );
          }
          if (segment.error) {
            return (
              <span key={index} className={styles.broken} title={segment.error}>
                <code className={styles.brokenSource}>{segment.value}</code>
                <span className={styles.brokenMessage}>{segment.error}</span>
              </span>
            );
          }
          return (
            <span
              key={index}
              className={segment.kind === "display" ? styles.display : styles.inline}
              // KaTeX output is markup it generated from the teacher's own
              // source; there is no third-party HTML anywhere in this path.
              dangerouslySetInnerHTML={{ __html: segment.html as string }}
            />
          );
        })}
      </div>

      <p className={styles.note}>
        {unclosed
          ? "Đang có dấu $ chưa được đóng — gõ tiếp dấu $ nữa để khép công thức lại."
          : "Chỉ để bạn soát lại — hệ thống chấm không đọc LaTeX, nó gửi nguyên văn chữ bạn gõ cho LLM."}
      </p>
    </div>
  );
}
