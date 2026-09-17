/**
 * Textarea behaviour for fields that hold source code.
 *
 * `question.text` carries the whole C++ listing of a question and
 * `sample_solution` a reference implementation, so the two things a code editor
 * gives you for free are exactly the two missing here: the box grows with the
 * text instead of leaving you to drag its corner, and Tab indents instead of
 * jumping to the next field.
 */
import type { KeyboardEvent } from "react";

/** Matches the 4-space indentation the existing barem listings are written in. */
export const INDENT = "    ";

/** Fit the box to its content, so a 30-line listing needs no dragging. */
export function autoGrow(element: HTMLTextAreaElement | null): void {
  if (!element) return;
  element.style.height = "auto";
  element.style.height = `${element.scrollHeight}px`;
}

/**
 * Replace the current selection, keeping the browser's own undo history.
 *
 * Assigning to `.value` wipes the undo stack, which is a nasty thing to do to
 * someone typing a long code listing. `execCommand("insertText")` is formally
 * deprecated but remains the only way to edit a textarea as if the user had
 * typed it; the direct write is a fallback for engines that refuse it.
 */
function replaceSelection(element: HTMLTextAreaElement, text: string, onChange: (value: string) => void): void {
  element.focus();
  const inserted = document.execCommand("insertText", false, text);
  if (!inserted) {
    const { selectionStart, selectionEnd, value } = element;
    element.value = value.slice(0, selectionStart) + text + value.slice(selectionEnd);
    element.selectionStart = element.selectionEnd = selectionStart + text.length;
  }
  onChange(element.value);
}

function lineBounds(value: string, from: number, to: number): [number, number] {
  const start = value.lastIndexOf("\n", from - 1) + 1;
  const nextBreak = value.indexOf("\n", to);
  return [start, nextBreak === -1 ? value.length : nextBreak];
}

export interface BlockIndent {
  /** Range of the original text to replace. */
  from: number;
  to: number;
  /** What to put there. */
  text: string;
}

/**
 * Indent or outdent every line the selection touches.
 *
 * Split out as a pure function purely so the index arithmetic can be tested
 * without a DOM — an off-by-one here silently eats a character of someone's
 * code listing.
 */
export function computeBlockIndent(
  value: string,
  selectionStart: number,
  selectionEnd: number,
  outdent: boolean,
): BlockIndent {
  const [from, to] = lineBounds(value, selectionStart, selectionEnd);
  const text = value
    .slice(from, to)
    .split("\n")
    .map((line) => {
      if (!outdent) return INDENT + line;
      const match = line.match(/^[ \t]{1,4}/);
      return match ? line.slice(match[0].length) : line;
    })
    .join("\n");
  return { from, to, text };
}

/**
 * Tab indents, Shift+Tab outdents, over one line or a whole selected block.
 *
 * Escape blurs the field first: swallowing Tab traps keyboard users inside the
 * textarea, and an explicit way out is the accepted way to keep both.
 */
export function handleCodeKeyDown(
  event: KeyboardEvent<HTMLTextAreaElement>,
  onChange: (value: string) => void,
): void {
  const element = event.currentTarget;

  if (event.key === "Escape") {
    element.blur();
    return;
  }
  if (event.key !== "Tab" || event.ctrlKey || event.altKey || event.metaKey) return;

  event.preventDefault();
  const { selectionStart, selectionEnd, value } = element;
  const multiLine = value.slice(selectionStart, selectionEnd).includes("\n");

  if (!multiLine && !event.shiftKey) {
    replaceSelection(element, INDENT, onChange);
    return;
  }

  // Whole-block indent/outdent: rewrite every touched line, then restore a
  // selection that still covers the same lines.
  const { from, to, text } = computeBlockIndent(value, selectionStart, selectionEnd, event.shiftKey);
  element.setSelectionRange(from, to);
  replaceSelection(element, text, onChange);
  element.setSelectionRange(from, from + text.length);
}
