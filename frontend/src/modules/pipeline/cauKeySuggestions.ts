import type { ExamRubric } from "@/types/barem";
import type { RoiTaskType } from "@/types/pipeline";

export interface CauKeySuggestion {
  cau_key: string;
  label: string;
  /** Best guess from the criteria's question_type, only a default. */
  task_type: RoiTaskType;
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

/** "a" → "a"; "main"/"main_S2" → "" (the number becomes a `_N` suffix instead). */
function partLetter(partLabel: string): string {
  return /^[a-z]$/i.test(partLabel) ? partLabel.toLowerCase() : "";
}

/** "main_S2" → 2, so the slot lands on `Cau_08_2`. */
function mainSlotIndex(partLabel: string): number | null {
  const match = /^main[_-]?s?(\d+)$/i.exec(partLabel);
  return match ? Number(match[1]) : null;
}

function guessTaskType(questionTypes: Set<string>): RoiTaskType {
  if (questionTypes.has("visual")) return "diagram";
  if (questionTypes.has("table")) return "table";
  if (questionTypes.has("logical")) return "code";
  return "short_text";
}

/**
 * Derive the `cau_key`s a barem expects, following the
 * `Cau_XX` / `Cau_XXa` / `Cau_XXa_N` convention that
 * `convert_results_to_samples()` parses with
 * `Cau_(\d+)([a-z]?)(?:_(\d+))?`.
 *
 * These are suggestions for the ROI editor's picker, not a contract — the
 * field stays free-text because a barem can name parts in ways this doesn't
 * anticipate.
 */
export function suggestCauKeys(exam: ExamRubric | null): CauKeySuggestion[] {
  if (!exam) return [];
  const out: CauKeySuggestion[] = [];

  exam.teacher_barem.forEach((question) => {
    const number = pad2(question.question_number);

    question.question.parts.forEach((part) => {
      // question_type lives on the criteria, matched to a part by part_label.
      const types = new Set(
        question.grading_rule
          .filter((c) => !c.part_label || c.part_label === part.part_label)
          .map((c) => c.question_type)
          .filter((t): t is string => Boolean(t)),
      );
      const taskType = guessTaskType(types);

      const letter = partLetter(part.part_label);
      const slotIndex = mainSlotIndex(part.part_label);
      const base = `Cau_${number}${letter}`;
      const slotCount = part.answer_slots.length;

      if (slotIndex !== null) {
        out.push({
          cau_key: `${base}_${slotIndex}`,
          label: `Câu ${question.question_number} · ${part.part_label}`,
          task_type: taskType,
        });
        return;
      }

      if (slotCount > 1) {
        for (let i = 1; i <= slotCount; i += 1) {
          out.push({
            cau_key: `${base}_${i}`,
            label: `Câu ${question.question_number}${letter} · ô ${i}`,
            task_type: taskType,
          });
        }
        return;
      }

      out.push({
        cau_key: base,
        label: `Câu ${question.question_number}${letter ? ` phần ${letter}` : ""}`,
        task_type: taskType,
      });
    });
  });

  // A part with no answer_slots can collide with a sibling; keep the first.
  const seen = new Set<string>();
  return out.filter((s) => (seen.has(s.cau_key) ? false : (seen.add(s.cau_key), true)));
}
