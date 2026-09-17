/**
 * Split barem prose into plain-text and LaTeX segments for the preview.
 *
 * Nothing in the pipeline parses LaTeX — `question.text` reaches the grading
 * prompt as the exact bytes the teacher typed, and the LLM reads the notation
 * itself. So this exists purely so the *author* can see the formula rendered
 * and catch a typo (`\mathb{R}`, an unclosed brace) that would otherwise ship
 * silently into a paid grading run.
 *
 * Written as a scanner rather than a regex because the two delimiters overlap:
 * `$$` must win over `$` wherever both could start a segment, and a regex
 * alternation gets that wrong as soon as one display block sits next to an
 * inline one.
 */

export interface MathSegment {
  kind: "text" | "inline" | "display";
  value: string;
}

/** True when a `$` at this index is escaped by an odd run of backslashes. */
function isEscaped(source: string, index: number): boolean {
  let backslashes = 0;
  for (let i = index - 1; i >= 0 && source[i] === "\\"; i -= 1) backslashes += 1;
  return backslashes % 2 === 1;
}

/**
 * Find the closing delimiter for math opened at `from`.
 *
 * Inline math stops at a blank line: an unclosed `$` in prose would otherwise
 * swallow the rest of the question and render it all as one broken formula,
 * which hides the actual mistake instead of showing it. Display math has no
 * such limit — `$$…$$` spanning several lines is the normal way to write one.
 */
function findClose(source: string, from: number, delimiter: string): number {
  const limit = delimiter === "$" ? source.indexOf("\n\n", from) : -1;
  for (let i = from; i <= source.length - delimiter.length; i += 1) {
    if (limit !== -1 && i > limit) return -1;
    if (source.startsWith(delimiter, i) && !isEscaped(source, i)) return i;
  }
  return -1;
}

/**
 * Tokenise `source`. Unmatched delimiters stay in the text verbatim — the
 * preview should show what is actually there, never quietly repair it.
 */
export function splitMath(source: string): MathSegment[] {
  const segments: MathSegment[] = [];
  let text = "";
  let i = 0;

  const flushText = () => {
    if (text) segments.push({ kind: "text", value: text });
    text = "";
  };

  while (i < source.length) {
    const isDollar = source[i] === "$" && !isEscaped(source, i);
    if (!isDollar) {
      text += source[i];
      i += 1;
      continue;
    }

    const delimiter = source.startsWith("$$", i) ? "$$" : "$";
    const close = findClose(source, i + delimiter.length, delimiter);
    if (close === -1) {
      text += source[i];
      i += 1;
      continue;
    }

    flushText();
    segments.push({
      kind: delimiter === "$$" ? "display" : "inline",
      value: source.slice(i + delimiter.length, close),
    });
    i = close + delimiter.length;
  }

  flushText();
  return segments;
}

/** Did at least one complete `$…$` / `$$…$$` pair parse out? */
export function hasMath(source: string): boolean {
  return splitMath(source).some((segment) => segment.kind !== "text");
}

/**
 * Is the author writing maths here at all — even if no pair is closed yet?
 *
 * This, not `hasMath`, decides whether the preview panel is on screen. Keying
 * visibility to a *complete* pair makes the panel blink out mid-word: typing
 * `\mathbb{R}` in front of a closing `$` passes through `…\$`, where the
 * trailing backslash reads as a LaTeX-escaped dollar and no pair matches for
 * exactly one keystroke. The panel vanishing at that moment reads as "I broke
 * it" and stops people mid-formula, which is what happened the first time this
 * shipped. An unclosed `$` keeps the panel up and says so instead.
 */
export function hasOpenMath(source: string): boolean {
  for (let i = 0; i < source.length; i += 1) {
    if (source[i] === "$" && !isEscaped(source, i)) return true;
  }
  return false;
}
