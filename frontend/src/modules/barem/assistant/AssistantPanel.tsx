/**
 * Chat drawer beside the barem builder: the teacher uploads the exam and
 * talks; the assistant answers with a proposal the teacher accepts question
 * by question. Nothing is applied without a click, and an applied proposal
 * is a single "Hoàn tác" step (see BaremBuilderPage's onApply).
 *
 * Kept mounted while closed (hidden), so the conversation and the uploaded
 * document survive toggling the drawer.
 */
import { useEffect, useRef, useState } from "react";

import Button from "@/components/core/Button";
import type { ExamRubric, ValidationIssue } from "@/types/barem";

import { chatAssistant, extractDocument, type ChatTurn, type ExtractedDocument } from "./assistantApi";
import { describeProposal, type AssistantReply, type ProposedChange } from "./fromDraft";
import styles from "./AssistantPanel.module.css";

interface Message {
  role: "user" | "assistant";
  text: string;
  reply?: AssistantReply;
  changes?: ProposedChange[];
  applied?: string;
}

interface AssistantPanelProps {
  open: boolean;
  exam: ExamRubric;
  errors: ValidationIssue[];
  onClose: () => void;
  /** Apply the chosen changes; returns a one-line summary for the chat. */
  onApply: (reply: AssistantReply, selected: Set<string>) => string;
}

const DRAFT_PROMPT =
  "Dựng nháp barem cho toàn bộ đề trong file. Lấy điểm từng câu theo đề. Câu nào đề không có đáp án thì vẫn dựng và ghi chú để tôi kiểm tra.";

/** What the model is told it said last time: its reply plus what it proposed. */
function historyText(message: Message): string {
  if (message.role === "user" || !message.changes?.length) return message.text;
  const list = message.changes.map((c) => c.label).join(", ");
  return `${message.text}\n(Đã đề xuất: ${list}${message.applied ? ` — giáo viên ${message.applied}` : ""})`;
}

function ProposalCard({
  message,
  onApply,
}: {
  message: Message;
  onApply: (selected: Set<string>) => void;
}) {
  const changes = message.changes ?? [];
  const applicable = changes.filter((c) => c.kind !== "locked");
  const [selected, setSelected] = useState<Set<string>>(() => new Set(applicable.map((c) => c.key)));

  if (changes.length === 0) return null;
  const toggle = (key: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  return (
    <div className={styles.proposal}>
      <ul className={styles.changeList}>
        {changes.map((change) => (
          <li key={change.key} className={styles[`change_${change.kind}`]}>
            <label>
              <input
                type="checkbox"
                disabled={change.kind === "locked" || Boolean(message.applied)}
                checked={change.kind !== "locked" && selected.has(change.key)}
                onChange={() => toggle(change.key)}
              />
              <span className={styles.changeLabel}>{change.label}</span>
              {change.detail && <span className={styles.changeDetail}>{change.detail}</span>}
            </label>
          </li>
        ))}
      </ul>
      {message.applied ? (
        <p className={styles.applied}>✓ {message.applied}</p>
      ) : (
        applicable.length > 0 && (
          <Button size="sm" disabled={selected.size === 0} onClick={() => onApply(selected)}>
            Áp dụng {selected.size} thay đổi
          </Button>
        )
      )}
    </div>
  );
}

export default function AssistantPanel({ open, exam, errors, onClose, onApply }: AssistantPanelProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [doc, setDoc] = useState<ExtractedDocument | null>(null);
  const [reading, setReading] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const listEnd = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  async function handleFile(file: File) {
    setReading(true);
    setError(null);
    try {
      setDoc(await extractDocument(file));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setReading(false);
    }
  }

  async function send(text: string) {
    const content = text.trim();
    if (!content || busy) return;
    const conversation: Message[] = [...messages, { role: "user", text: content }];
    setMessages(conversation);
    setInput("");
    setBusy(true);
    setError(null);
    try {
      const turns: ChatTurn[] = conversation.map((m) => ({ role: m.role, content: historyText(m) }));
      const reply = await chatAssistant(turns, exam, doc?.text ?? null);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: reply.reply || "Đây là đề xuất của tôi.",
          reply,
          changes: describeProposal(exam, reply),
        },
      ]);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function apply(index: number, selected: Set<string>) {
    const message = messages[index];
    if (!message.reply) return;
    const summary = onApply(message.reply, selected);
    setMessages((prev) => prev.map((m, i) => (i === index ? { ...m, applied: summary } : m)));
  }

  const fixPrompt =
    "Barem đang có các lỗi kiểm tra sau, hãy sửa những câu liên quan:\n" +
    errors
      .slice(0, 15)
      .map((issue) => `- ${issue.questionNumber !== undefined ? `Câu ${issue.questionNumber}: ` : ""}${issue.message}`)
      .join("\n");

  return (
    <aside className={styles.panel} hidden={!open} aria-label="Trợ lý soạn barem">
      <header className={styles.head}>
        <div>
          <h2 className={styles.title}>Trợ lý soạn barem</h2>
          <p className={styles.subtitle}>Tải đề, nói đáp án và cách cho điểm — trợ lý soạn, bạn duyệt.</p>
        </div>
        <button type="button" className={styles.close} onClick={onClose} aria-label="Đóng">
          ✕
        </button>
      </header>

      <div className={styles.docBar}>
        <input
          ref={fileInput}
          type="file"
          accept=".pdf,.docx"
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void handleFile(file);
            e.target.value = "";
          }}
        />
        {doc ? (
          <>
            <span className={styles.docName}>
              📄 {doc.filename} · {doc.chars.toLocaleString("vi-VN")} ký tự
            </span>
            <button type="button" className={styles.link} onClick={() => setDoc(null)}>
              Bỏ file
            </button>
          </>
        ) : (
          <Button size="sm" variant="secondary" loading={reading} onClick={() => fileInput.current?.click()}>
            Tải đề (Word / PDF)
          </Button>
        )}
      </div>

      <div className={styles.messages}>
        {messages.length === 0 && (
          <div className={styles.welcome}>
            <p>Bạn có thể:</p>
            <ul>
              <li>Tải file đề rồi bấm <strong>“Tạo nháp từ đề”</strong>.</li>
              <li>Nói đáp án bằng lời, ví dụ: <em>“Câu 3 đáp án 3529, sai một chữ số cho 0.25 điểm”</em>.</li>
              <li>Nhờ sửa: <em>“Câu 5 chấp nhận cả cách dùng while”</em>, <em>“Xoá câu 7”</em>.</li>
            </ul>
            <p className={styles.hint}>
              Câu có bảng hoặc đáp án theo STT học sinh trợ lý chưa soạn được — bạn soạn tay. Mỗi tin nhắn là một
              lượt gọi AI.
            </p>
          </div>
        )}

        {messages.map((message, index) => (
          <div key={index} className={message.role === "user" ? styles.userMsg : styles.botMsg}>
            <p className={styles.msgText}>{message.text}</p>
            {message.reply && message.reply.confidence_notes.length > 0 && (
              <ul className={styles.notes}>
                {message.reply.confidence_notes.map((note, i) => (
                  <li key={i}>{note}</li>
                ))}
              </ul>
            )}
            {message.changes && (
              <ProposalCard message={message} onApply={(selected) => apply(index, selected)} />
            )}
          </div>
        ))}

        {busy && <p className={styles.thinking}>Trợ lý đang soạn… (đề dài có thể mất 1–2 phút)</p>}
        {error && <p className={styles.error}>{error}</p>}
        <div ref={listEnd} />
      </div>

      <div className={styles.quick}>
        <Button size="sm" variant="secondary" disabled={busy || !doc} onClick={() => send(DRAFT_PROMPT)}>
          Tạo nháp từ đề
        </Button>
        {errors.length > 0 && (
          <Button size="sm" variant="secondary" disabled={busy} onClick={() => send(fixPrompt)}>
            Sửa {errors.length} lỗi kiểm tra
          </Button>
        )}
      </div>

      <form
        className={styles.composer}
        onSubmit={(e) => {
          e.preventDefault();
          void send(input);
        }}
      >
        <textarea
          className={styles.input}
          value={input}
          rows={3}
          placeholder="Nhập yêu cầu… (Enter để gửi, Shift+Enter xuống dòng)"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send(input);
            }
          }}
        />
        <Button type="submit" size="sm" disabled={busy || !input.trim()}>
          Gửi
        </Button>
      </form>
    </aside>
  );
}
