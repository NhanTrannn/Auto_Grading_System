import { useEffect, useRef, useState } from "react";

import Button from "@/components/core/Button";
import { IconChevronRight } from "@/components/core/Icon";
import { getPipelineJobLog } from "@/services/pipelineApi";

import styles from "./LiveLogPanel.module.css";

interface LiveLogPanelProps {
  jobId: string;
  /** Keep polling while the run is active; one final read happens either way. */
  active: boolean;
}

const POLL_MS = 2000;

export default function LiveLogPanel({ jobId, active }: LiveLogPanelProps) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [follow, setFollow] = useState(true);
  const offsetRef = useRef(0);
  const bodyRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    offsetRef.current = 0;
    setText("");
  }, [jobId]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;

    async function tick() {
      try {
        const chunk = await getPipelineJobLog(jobId, offsetRef.current);
        if (cancelled || !chunk.text) {
          if (!cancelled) offsetRef.current = chunk.next_offset;
          return;
        }
        // A restarted/truncated log resets the offset server-side; replace
        // rather than append so the panel doesn't show a duplicated run.
        setText((current) => (chunk.next_offset < offsetRef.current ? chunk.text : current + chunk.text));
        offsetRef.current = chunk.next_offset;
      } catch {
        // The log file may not exist yet — keep polling quietly.
      }
    }

    void tick();
    if (!active) return;
    const timer = window.setInterval(tick, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [jobId, open, active]);

  useEffect(() => {
    if (follow && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [text, follow]);

  return (
    <section className={styles.panel}>
      <header className={styles.header}>
        <button type="button" className={styles.toggle} onClick={() => setOpen((v) => !v)}>
          <span className={`${styles.chevron} ${open ? styles.chevronOpen : ""}`}>
            <IconChevronRight size={14} />
          </span>
          Nhật ký chạy
          {active && open && <span className={styles.liveDot} />}
        </button>
        {open && (
          <div className={styles.actions}>
            <label className={styles.followLabel}>
              <input
                type="checkbox"
                checked={follow}
                onChange={(e) => setFollow(e.target.checked)}
              />
              Tự cuộn
            </label>
            <Button variant="ghost" size="sm" onClick={() => navigator.clipboard?.writeText(text)}>
              Sao chép
            </Button>
          </div>
        )}
      </header>

      {open && (
        <pre ref={bodyRef} className={styles.body}>
          {text || "Chưa có nhật ký."}
        </pre>
      )}
    </section>
  );
}
