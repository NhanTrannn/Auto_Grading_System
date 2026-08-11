/**
 * Draft state for the barem builder: the working rubric, autosaved to
 * localStorage, plus the mutation helpers the editor components call.
 *
 * Mutations are expressed as immutable updates over the whole exam so undo can
 * simply keep previous snapshots — a barem is small (tens of KB) and edited by
 * hand, so structural sharing would buy nothing over a plain clone.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { Criterion, ExamRubric, QuestionPart, RubricQuestion } from "@/types/barem";

import { deepClone } from "./factory";
import { examTotal } from "./flatten";
import { validateExam } from "./validate";

const STORAGE_KEY = "mmlab.barem.draft.v1";
const UNDO_LIMIT = 50;

function blankExam(): ExamRubric {
  return {
    ma_de: "1",
    subject: "IT001 - Nhập môn lập trình",
    total_score: 10,
    teacher_barem: [],
  };
}

function loadDraft(): ExamRubric {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return blankExam();
    const parsed = JSON.parse(raw);
    if (parsed && Array.isArray(parsed.teacher_barem)) return parsed as ExamRubric;
  } catch {
    // A corrupt draft must not brick the page — fall back to a blank rubric.
  }
  return blankExam();
}

export function useBaremDraft() {
  const [exam, setExamState] = useState<ExamRubric>(loadDraft);
  const [selectedQuestion, setSelectedQuestion] = useState<number | null>(null);
  const undoStack = useRef<ExamRubric[]>([]);
  const [undoDepth, setUndoDepth] = useState(0);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(exam));
      } catch {
        // Quota exceeded / private mode — the export button is still the real
        // save path, so a failed autosave is not worth interrupting editing.
      }
    }, 400);
    return () => window.clearTimeout(timer);
  }, [exam]);

  const setExam = useCallback((updater: (draft: ExamRubric) => ExamRubric) => {
    setExamState((current) => {
      undoStack.current = [...undoStack.current.slice(-(UNDO_LIMIT - 1)), current];
      setUndoDepth(undoStack.current.length);
      return updater(current);
    });
  }, []);

  const undo = useCallback(() => {
    setExamState((current) => {
      const previous = undoStack.current.pop();
      setUndoDepth(undoStack.current.length);
      return previous ?? current;
    });
  }, []);

  const replaceExam = useCallback(
    (next: ExamRubric) => {
      setExam(() => next);
      setSelectedQuestion(next.teacher_barem[0]?.question_number ?? null);
    },
    [setExam],
  );

  const updateMeta = useCallback(
    (patch: Partial<Pick<ExamRubric, "ma_de" | "subject" | "total_score">>) => {
      setExam((draft) => ({ ...draft, ...patch }));
    },
    [setExam],
  );

  const updateQuestion = useCallback(
    (questionNumber: number, updater: (question: RubricQuestion) => RubricQuestion) => {
      setExam((draft) => ({
        ...draft,
        teacher_barem: draft.teacher_barem.map((question) =>
          question.question_number === questionNumber ? updater(deepClone(question)) : question,
        ),
      }));
    },
    [setExam],
  );

  const addQuestion = useCallback(
    (question: RubricQuestion) => {
      setExam((draft) => ({
        ...draft,
        teacher_barem: [...draft.teacher_barem, question].sort(
          (a, b) => a.question_number - b.question_number,
        ),
      }));
      setSelectedQuestion(question.question_number);
    },
    [setExam],
  );

  const removeQuestion = useCallback(
    (questionNumber: number) => {
      setExam((draft) => ({
        ...draft,
        teacher_barem: draft.teacher_barem.filter((q) => q.question_number !== questionNumber),
      }));
      setSelectedQuestion((current) => (current === questionNumber ? null : current));
    },
    [setExam],
  );

  const duplicateQuestion = useCallback(
    (questionNumber: number) => {
      setExam((draft) => {
        const source = draft.teacher_barem.find((q) => q.question_number === questionNumber);
        if (!source) return draft;
        const nextNumber = Math.max(...draft.teacher_barem.map((q) => q.question_number)) + 1;
        const clone = deepClone(source);
        clone.question_number = nextNumber;
        clone.sample_id = `cau_${nextNumber}_001`;
        // IDs must stay unique across the whole barem — validate_barem() errors
        // on a duplicate criterion_id, and slot_ids are the join key to OCR data.
        const renameIds = (criteria: Criterion[]): Criterion[] =>
          criteria.map((criterion) => ({
            ...criterion,
            criterion_id: criterion.criterion_id.replace(
              new RegExp(`^T${questionNumber}\\b`),
              `T${nextNumber}`,
            ),
            slot_ids: criterion.slot_ids?.map((id) =>
              id.replace(`cau_${questionNumber}_001`, `cau_${nextNumber}_001`),
            ),
            sub_criteria: criterion.sub_criteria ? renameIds(criterion.sub_criteria) : undefined,
          }));
        clone.grading_rule = renameIds(clone.grading_rule);
        clone.question.parts = clone.question.parts.map((part) => ({
          ...part,
          answer_slots: part.answer_slots.map((slot) => ({
            ...slot,
            slot_id: slot.slot_id.replace(`cau_${questionNumber}_001`, `cau_${nextNumber}_001`),
          })),
        }));
        return { ...draft, teacher_barem: [...draft.teacher_barem, clone] };
      });
    },
    [setExam],
  );

  const updatePart = useCallback(
    (questionNumber: number, partIndex: number, updater: (part: QuestionPart) => QuestionPart) => {
      updateQuestion(questionNumber, (question) => ({
        ...question,
        question: {
          ...question.question,
          parts: question.question.parts.map((part, index) =>
            index === partIndex ? updater(part) : part,
          ),
        },
      }));
    },
    [updateQuestion],
  );

  /**
   * Update one criterion anywhere in the tree by id. Criteria nest arbitrarily
   * (grading_rule → sub_criteria), so every editor addresses them by id rather
   * than by a path the caller would have to keep in sync.
   */
  const updateCriterion = useCallback(
    (questionNumber: number, criterionId: string, updater: (criterion: Criterion) => Criterion) => {
      const walk = (criteria: Criterion[]): Criterion[] =>
        criteria.map((criterion) => {
          if (criterion.criterion_id === criterionId) return updater(criterion);
          if (criterion.sub_criteria?.length) {
            return { ...criterion, sub_criteria: walk(criterion.sub_criteria) };
          }
          return criterion;
        });
      updateQuestion(questionNumber, (question) => ({
        ...question,
        grading_rule: walk(question.grading_rule),
      }));
    },
    [updateQuestion],
  );

  const removeCriterion = useCallback(
    (questionNumber: number, criterionId: string) => {
      const walk = (criteria: Criterion[]): Criterion[] =>
        criteria
          .filter((criterion) => criterion.criterion_id !== criterionId)
          .map((criterion) =>
            criterion.sub_criteria?.length
              ? { ...criterion, sub_criteria: walk(criterion.sub_criteria) }
              : criterion,
          );
      updateQuestion(questionNumber, (question) => ({
        ...question,
        grading_rule: walk(question.grading_rule),
      }));
    },
    [updateQuestion],
  );

  const addCriterion = useCallback(
    (questionNumber: number, criterion: Criterion, parentId?: string) => {
      updateQuestion(questionNumber, (question) => {
        if (!parentId) {
          return { ...question, grading_rule: [...question.grading_rule, criterion] };
        }
        const walk = (criteria: Criterion[]): Criterion[] =>
          criteria.map((item) =>
            item.criterion_id === parentId
              ? { ...item, sub_criteria: [...(item.sub_criteria ?? []), criterion] }
              : item.sub_criteria?.length
                ? { ...item, sub_criteria: walk(item.sub_criteria) }
                : item,
          );
        return { ...question, grading_rule: walk(question.grading_rule) };
      });
    },
    [updateQuestion],
  );

  const reset = useCallback(() => {
    setExam(() => blankExam());
    setSelectedQuestion(null);
  }, [setExam]);

  const report = useMemo(() => validateExam(exam), [exam]);
  const computedTotal = useMemo(() => examTotal(exam.teacher_barem), [exam.teacher_barem]);

  const activeQuestion = useMemo(
    () => exam.teacher_barem.find((q) => q.question_number === selectedQuestion) ?? null,
    [exam.teacher_barem, selectedQuestion],
  );

  return {
    exam,
    report,
    computedTotal,
    activeQuestion,
    selectedQuestion,
    setSelectedQuestion,
    canUndo: undoDepth > 0,
    undo,
    replaceExam,
    updateMeta,
    updateQuestion,
    addQuestion,
    removeQuestion,
    duplicateQuestion,
    updatePart,
    updateCriterion,
    removeCriterion,
    addCriterion,
    reset,
  };
}

export type BaremDraft = ReturnType<typeof useBaremDraft>;
