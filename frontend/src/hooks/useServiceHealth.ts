import { useEffect, useState } from "react";

import { getOcrHealth } from "@/services/ocrApi";

export type HealthState = "checking" | "up" | "down";

export interface ServiceHealth {
  grading: HealthState;
  ocr: HealthState;
  /** null while unknown; true/false once the OCR service has answered. */
  ocrLlmConfigured: boolean | null;
}

const POLL_MS = 20000;

/** Polls both backends so the sidebar can show which services are reachable. */
export function useServiceHealth(): ServiceHealth {
  const [grading, setGrading] = useState<HealthState>("checking");
  const [ocr, setOcr] = useState<HealthState>("checking");
  const [ocrLlmConfigured, setOcrLlmConfigured] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function check() {
      try {
        const res = await fetch("/api/v1/health");
        if (!cancelled) setGrading(res.ok ? "up" : "down");
      } catch {
        if (!cancelled) setGrading("down");
      }

      try {
        const health = await getOcrHealth();
        if (!cancelled) {
          setOcr("up");
          setOcrLlmConfigured(health.module3_llm_configured);
        }
      } catch {
        if (!cancelled) {
          setOcr("down");
          setOcrLlmConfigured(null);
        }
      }
    }

    void check();
    const timer = window.setInterval(check, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  return { grading, ocr, ocrLlmConfigured };
}
