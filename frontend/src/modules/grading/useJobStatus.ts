import { useEffect, useState } from "react";

import { getGradingJob, getGradingJobResult } from "@/services/api";
import type { GradingJobResult, JobStatus } from "@/types/grading";

const POLL_INTERVAL_MS = 2000;

interface JobStatusState {
  status: JobStatus | null;
  error: string | null;
  result: GradingJobResult | null;
  loading: boolean;
}

/** Tracks one job by ID — works for a job just created (still pending) and
 * for an older job loaded from history (may already be done/failed). Polls
 * while pending/running, fetches the full result once done, stops on
 * done/failed. */
export function useJobStatus(jobId: string | null) {
  const [state, setState] = useState<JobStatusState>({
    status: null,
    error: null,
    result: null,
    loading: true,
  });

  useEffect(() => {
    if (!jobId) return;

    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | null = null;
    setState({ status: null, error: null, result: null, loading: true });

    async function tick() {
      try {
        const job = await getGradingJob(jobId as string);
        if (cancelled) return;

        if (job.status === "done") {
          if (timer) clearInterval(timer);
          const result = await getGradingJobResult(jobId as string);
          if (!cancelled) setState({ status: job.status, error: null, result, loading: false });
        } else if (job.status === "failed") {
          if (timer) clearInterval(timer);
          setState({ status: job.status, error: job.error, result: null, loading: false });
        } else {
          setState((s) => ({ ...s, status: job.status, error: null, loading: false }));
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
