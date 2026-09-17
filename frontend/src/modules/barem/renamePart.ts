/**
 * Rename a part, carrying its slot ids and every reference to them along.
 *
 * Renaming the label is not a cosmetic change. `convert_results_to_samples`
 * builds the *student data's* slot ids from the barem's part_label —
 * `cau_{n}_001_{part_label}`, plus `_S{i}` when the part has several slots — so
 * the moment the label changes, the ids the grader will actually see change
 * too. A `slot_id` still written the old way then matches nothing.
 *
 * That failure is quiet rather than loud: `get_student_evidence_for_slot` falls
 * back to filtering by `part_label`, which looks harmless until the part has
 * more than one slot, because the fallback hands every criterion the *whole
 * part's* text. Sub-criteria meant for separate blanks all end up grading the
 * same merged answer.
 *
 * Only ids following the `{sample_id}_{label}` convention are rewritten. A
 * hand-written id that does not follow it is left alone — renaming that would
 * be guessing at the author's intent.
 *
 * Split out of the editor component so the string surgery can be tested against
 * a real barem without rendering anything.
 */
import type { Criterion, RubricQuestion } from "@/types/barem";

export function renamePartLabel(
  question: RubricQuestion,
  index: number,
  nextLabel: string,
): RubricQuestion {
  const parts = question.question.parts;
  const target = parts[index];
  if (!target || target.part_label === nextLabel) return question;

  const oldLabel = target.part_label;

  // Rewrite the label where it sits in the id — as the last segment, or the one
  // before an `_S{n}` suffix — rather than assuming the id starts with
  // `sample_id`. It often does not: `sample_parem.json` has câu 15 declaring
  // `sample_id: "cau_15"` while its slots read `cau_15_001_b_S1`, because the
  // `_001` comes from convert_results_to_samples' own formula. Matching on the
  // suffix works under either spelling.
  const suffix = new RegExp(`(^|_)${oldLabel.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(_S\\d+)?$`);
  const renameId = (id: string): string =>
    suffix.test(id) ? id.replace(suffix, (_m, lead: string, tail = "") => `${lead}${nextLabel}${tail}`) : id;

  // The part owns its slots, so which ids actually changed is known exactly —
  // references are rewritten by lookup instead of by re-running the pattern,
  // which keeps an unrelated criterion pointing at another part's slot safe
  // even if that id happens to end the same way.
  const renamed = new Map<string, string>();
  for (const slot of target.answer_slots) {
    const next = renameId(slot.slot_id);
    if (next !== slot.slot_id) renamed.set(slot.slot_id, next);
  }
  const rename = (id: string): string => renamed.get(id) ?? id;

  const retarget = (criteria: Criterion[]): Criterion[] =>
    criteria.map((criterion) => {
      const next: Criterion = { ...criterion };
      if (next.part_label === oldLabel) next.part_label = nextLabel;
      if (next.sub_label === oldLabel) next.sub_label = nextLabel;
      if (next.slot_ids) next.slot_ids = next.slot_ids.map(rename);
      if (next.condition_source?.type === "self_reported") {
        next.condition_source = {
          ...next.condition_source,
          slot_ids: next.condition_source.slot_ids.map(rename),
        };
      }
      if (next.sub_criteria) next.sub_criteria = retarget(next.sub_criteria);
      return next;
    });

  return {
    ...question,
    question: {
      ...question.question,
      parts: parts.map((part, i) =>
        i === index
          ? {
              ...part,
              part_label: nextLabel,
              answer_slots: part.answer_slots.map((slot) => ({ ...slot, slot_id: rename(slot.slot_id) })),
            }
          : part,
      ),
    },
    grading_rule: retarget(question.grading_rule),
  };
}
