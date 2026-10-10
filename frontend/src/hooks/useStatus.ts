import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../services/api';
import type { StatusResponse } from '../types';

export interface UseStatusResult {
  status: StatusResponse | null;
  error: string | null;
  refresh: () => void;
}

/** Polls GET /api/status on an interval; never throws unhandled. */
export function useStatus(pollMs = 5000): UseStatusResult {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const aliveRef = useRef(true);

  const refresh = useCallback(() => {
    api
      .status()
      .then((data) => {
        if (!aliveRef.current) return;
        setStatus(data);
        setError(null);
      })
      .catch((e: unknown) => {
        if (!aliveRef.current) return;
        setError(e instanceof Error ? e.message : String(e));
      });
  }, []);

  useEffect(() => {
    aliveRef.current = true;
    refresh();
    const id = window.setInterval(refresh, pollMs);
    return () => {
      aliveRef.current = false;
      window.clearInterval(id);
    };
  }, [refresh, pollMs]);

  return { status, error, refresh };
}

export default useStatus;
