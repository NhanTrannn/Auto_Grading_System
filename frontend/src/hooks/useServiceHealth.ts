import { useEffect, useState } from "react";

export type HealthState = "checking" | "up" | "down";

export interface ServiceHealth {
  api: HealthState;
  /** null while unknown; true/false once the backend has answered. */
  llmConfigured: boolean | null;
}

const POLL_MS = 20000;

/**
 * Polls the backend so the sidebar can show whether it is reachable.
 *
 * One request, one status: OCR used to be a second service on its own port,
 * so this polled two endpoints and reported them separately.
 */
export function useServiceHealth(): ServiceHealth {
  const [api, setApi] = useState<HealthState>("checking");
  const [llmConfigured, setLlmConfigured] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function check() {
      try {
        const res = await fetch("/api/v1/health");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = await res.json();
        if (!cancelled) {
          setApi("up");
          setLlmConfigured(body?.llm_configured ?? null);
        }
      } catch {
        if (!cancelled) {
          setApi("down");
          setLlmConfigured(null);
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

  return { api, llmConfigured };
}
