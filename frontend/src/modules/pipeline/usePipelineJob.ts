import { useEffect, useState } from "react";

import { getPipelineJob, getPipelineJobResult } from "@/services/pipelineApi";
import type { GradingJobResult } from "@/types/grading";
import type { PipelineJobStatus } from "@/types/pipeline";

const POLL_INTERVAL_MS = 2000;

interface PipelineJobState {
  job: PipelineJobStatus | null;
  error: string | null;
  result: GradingJobResult | null;
  loading: boolean;
}

/**
 * Polls one pipeline job until it reaches a terminal state, then fetches the
 * graded result. Same poll-then-fetch shape as useJobStatus, but the status
 * object here carries stage/progress for the progress bar.
 */
export function usePipelineJob(jobId: string | null) {
  const [state, setState] = useState<PipelineJobState>({
    job: null,
    error: null,
    result: null,
    loading: true,
  });

  useEffect(() => {
    if (!jobId) return;

    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | null = null;
    setState({ job: null, error: null, result: null, loading: true });

    async function tick() {
      try {
        const job = await getPipelineJob(jobId as string);
        if (cancelled) return;

        if (job.status === "done") {
          if (timer) clearInterval(timer);
          const result = await getPipelineJobResult(jobId as string);
          if (!cancelled) setState({ job, error: null, result, loading: false });
        } else if (job.status === "failed") {
          if (timer) clearInterval(timer);
          setState({ job, error: job.error, result: null, loading: false });
        } else {
          setState((s) => ({ ...s, job, error: null, loading: false }));
        }
      } catch (err) {
        if (!cancelled) {
          if (timer) clearInterval(timer);
          setState((s) => ({ ...s, error: (err as Error).message, loading: false }));
        }
      }
    }

    tick();
    timer = setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
    };
  }, [jobId]);

  return state;
}
