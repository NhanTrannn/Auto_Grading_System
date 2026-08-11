/**
 * Visual editor for a part's `table_slot` grid.
 *
 * The flat table_slot list is the only shape `_attach_table_slots()` reads, but
 * it is miserable to author by hand: every cell of the grid — headers and
 * teacher-fixed values included, not just the blanks a student fills — has to
 * be listed with a cell_id that exactly concatenates its row_id and col_id.
 * Editing it as an actual grid makes the printed/student split visible and
 * keeps the ids generated rather than typed.
 *
 * Resizing regenerates the grid and reports which cells disappeared, because
 * dropping a cell silently would leave any criterion addressing it pointing at
 * a row/column that no longer exists.
 */
import { useMemo } from "react";

import Button from "@/components/core/Button";
import type { AnswerSlot, QuestionTable, TableSlotCell } from "@/types/barem";

import { Field, NumberInput, Row, TextInput } from "./Field";
import styles from "./TableSlotEditor.module.css";

interface TableSlotEditorProps {
  table: QuestionTable;
  /** Slots of the owning part, so each cell can show whether it is addressable. */
  answerSlots: AnswerSlot[];
  /** Cells already claimed by a `table` criterion — shown as graded. */
  gradedCells: Set<string>;
  onChange: (table: QuestionTable) => void;
  onRemove: () => void;
  onSyncSlots: (table: QuestionTable) => void;
}

function gridSize(cells: TableSlotCell[]): { rows: number; cols: number } {
  let rows = 0;
  let cols = 0;
  for (const cell of cells) {
    rows = Math.max(rows, Number(cell.row_id.replace(/\D/g, "")) || 0);
    cols = Math.max(cols, Number(cell.col_id.replace(/\D/g, "")) || 0);
  }
  return { rows, cols };
}

function resize(cells: TableSlotCell[], rows: number, cols: number): TableSlotCell[] {
  const byId = new Map(cells.map((cell) => [cell.cell_id, cell]));
  const next: TableSlotCell[] = [];
  for (let r = 1; r <= rows; r += 1) {
    for (let c = 1; c <= cols; c += 1) {
      const rowId = `R${r}`;
      const colId = `C${c}`;
      const cellId = `${rowId}${colId}`;
      next.push(
        byId.get(cellId) ?? {
          cell_id: cellId,
          // New first-row cells default to printed: row 1 is a header by
          // convention in every table in the real barem.
          source: r === 1 ? "printed" : "student_text",
          row_id: rowId,
          col_id: colId,
          text: "",
        },
      );
    }
  }
  return next;
}

export default function TableSlotEditor({
  table,
  answerSlots,
  gradedCells,
  onChange,
  onRemove,
  onSyncSlots,
}: TableSlotEditorProps) {
  const { rows, cols } = useMemo(() => gridSize(table.table_slot), [table.table_slot]);
  const cellMap = useMemo(
    () => new Map(table.table_slot.map((cell) => [cell.cell_id, cell])),
    [table.table_slot],
  );
  const slotByCell = useMemo(
    () => new Map(answerSlots.filter((slot) => slot.cell_id).map((slot) => [slot.cell_id!, slot])),
    [answerSlots],
  );

  const studentCells = table.table_slot.filter((cell) => cell.source === "student_text");
  const unslottedStudentCells = studentCells.filter((cell) => !slotByCell.has(cell.cell_id));

  function updateCell(cellId: string, patch: Partial<TableSlotCell>) {
    onChange({
      ...table,
      table_slot: table.table_slot.map((cell) =>
        cell.cell_id === cellId ? { ...cell, ...patch } : cell,
      ),
    });
  }

  function applySize(nextRows: number, nextCols: number) {
    const safeRows = Math.max(1, Math.min(20, nextRows));
    const safeCols = Math.max(1, Math.min(12, nextCols));
    onChange({ ...table, table_slot: resize(table.table_slot, safeRows, safeCols) });
  }

  return (
    <div className={styles.wrapper}>
      <Row>
        <Field label="table_id">
          <TextInput value={table.table_id} onChange={(value) => onChange({ ...table, table_id: value })} mono />
        </Field>
        <Field label="Số hàng" hint="Tính cả hàng tiêu đề">
          <NumberInput value={rows} step={1} min={1} onChange={(value) => applySize(value ?? 1, cols)} />
        </Field>
        <Field label="Số cột">
          <NumberInput value={cols} step={1} min={1} onChange={(value) => applySize(rows, value ?? 1)} />
        </Field>
      </Row>

      <div className={styles.gridScroll}>
        <table className={styles.grid}>
          <thead>
            <tr>
              <th className={styles.corner} />
              {Array.from({ length: cols }, (_, c) => (
                <th key={c} className={styles.colHead}>
                  C{c + 1}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: rows }, (_, r) => (
              <tr key={r}>
                <th className={styles.rowHead}>R{r + 1}</th>
                {Array.from({ length: cols }, (_, c) => {
                  const cellId = `R${r + 1}C${c + 1}`;
                  const cell = cellMap.get(cellId);
                  if (!cell) return <td key={cellId} className={styles.cell} />;
                  const isPrinted = cell.source === "printed";
                  const graded = gradedCells.has(cellId);
                  const slot = slotByCell.get(cellId);
                  return (
                    <td
                      key={cellId}
                      className={`${styles.cell} ${isPrinted ? styles.printed : styles.student}`}
                    >
                      <div className={styles.cellHead}>
                        <button
                          type="button"
                          className={styles.sourceToggle}
                          title={
                            isPrinted
                              ? "Ô in sẵn trên đề — nội dung lấy từ 'text' bên dưới"
                              : "Ô sinh viên điền — nội dung lấy từ bài làm khi chấm"
                          }
                          onClick={() =>
                            updateCell(cellId, {
                              source: isPrinted ? "student_text" : "printed",
                              text: isPrinted ? "" : cell.text,
                            })
                          }
                        >
                          {isPrinted ? "in sẵn" : "SV điền"}
                        </button>
                        {graded && (
                          <span className={styles.gradedDot} title="Đã có tiêu chí chấm ô này" />
                        )}
                      </div>
                      {isPrinted ? (
                        <input
                          className={styles.cellInput}
                          value={cell.text}
                          placeholder="Nội dung in sẵn"
                          onChange={(event) => updateCell(cellId, { text: event.target.value })}
                        />
                      ) : (
                        <div className={styles.slotTag} title={slot ? slot.slot_id : "Chưa có answer_slot"}>
                          {slot ? slot.slot_id.split("_").slice(-1)[0] : "—"}
                        </div>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className={styles.footer}>
        <div className={styles.legend}>
          <span>
            <i className={styles.swatchPrinted} /> in sẵn (header, giá trị đề cho)
          </span>
          <span>
            <i className={styles.swatchStudent} /> sinh viên điền
          </span>
          <span>
            <i className={styles.swatchGraded} /> đã có tiêu chí chấm
          </span>
        </div>
        <div className={styles.footerActions}>
          {unslottedStudentCells.length > 0 && (
            <Button size="sm" variant="secondary" onClick={() => onSyncSlots(table)}>
              Tạo answer_slot cho {unslottedStudentCells.length} ô còn thiếu
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={onRemove}>
            Xoá bảng
          </Button>
        </div>
      </div>
    </div>
  );
}
