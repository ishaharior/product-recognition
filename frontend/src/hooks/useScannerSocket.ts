import { useCallback, useEffect, useRef, useState } from 'react';
import { wsUrl } from '../services/api';
import type { WSDetectionMessage } from '../types';

export type ConnectionState = 'idle' | 'connecting' | 'open' | 'closed' | 'error';

export interface UseScannerSocketResult {
  connection: ConnectionState;
  error: string | null;
  last: WSDetectionMessage | null;
  sendFrame: (base64Jpeg: string) => void;
  fpsLimit: number;
}

const DEFAULT_FPS_LIMIT = 5;
const MAX_BACKOFF_MS = 10000;

/**
 * Scanner WebSocket lifecycle: opens while `enabled`, reconnects with backoff
 * (1s → 2s → 4s → … capped at 10s) and exposes the latest server message.
 */
export function useScannerSocket(enabled: boolean): UseScannerSocketResult {
  const [connection, setConnection] = useState<ConnectionState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [last, setLast] = useState<WSDetectionMessage | null>(null);
  const [fpsLimit, setFpsLimit] = useState(DEFAULT_FPS_LIMIT);

  const wsRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<number | null>(null);
  const attemptRef = useRef(0);
  const enabledRef = useRef(enabled);
  const connectRef = useRef<() => void>(() => undefined);

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const detach = useCallback(() => {
    const ws = wsRef.current;
    wsRef.current = null;
    if (!ws) return;
    ws.onopen = null;
    ws.onmessage = null;
    ws.onerror = null;
    ws.onclose = null;
    if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
      try {
        ws.close(1000);
      } catch {
        /* already closing */
      }
    }
  }, []);

  const scheduleReconnect = useCallback(() => {
    if (!enabledRef.current) return;
    clearTimer();
    const delay = Math.min(1000 * 2 ** attemptRef.current, MAX_BACKOFF_MS);
    attemptRef.current += 1;
    timerRef.current = window.setTimeout(() => connectRef.current(), delay);
  }, [clearTimer]);

  const connect = useCallback(() => {
    if (!enabledRef.current) return;
    clearTimer();
    detach();
    setConnection('connecting');

    let ws: WebSocket;
    try {
      ws = new WebSocket(wsUrl());
    } catch (e: unknown) {
      setConnection('error');
      setError(e instanceof Error ? e.message : 'Could not open the scanner WebSocket.');
      scheduleReconnect();
      return;
    }
    wsRef.current = ws;

    ws.onopen = () => {
      if (!enabledRef.current) {
        try {
          ws.close(1000);
        } catch {
          /* noop */
        }
        return;
      }
      attemptRef.current = 0;
      setConnection('open');
      setError(null);
    };

    ws.onmessage = (ev: MessageEvent) => {
      let msg: WSDetectionMessage;
      try {
        msg = JSON.parse(String(ev.data)) as WSDetectionMessage;
      } catch {
        return; // ignore malformed frames
      }
      if (msg.type === 'ready' && typeof msg.fps_limit === 'number') {
        setFpsLimit(msg.fps_limit);
      }
      if (msg.type === 'error') {
        setError(msg.message || 'Backend reported an error.');
      } else if (msg.type === 'ready' || msg.type === 'detection') {
        setError(null);
      }
      setLast(msg);
    };

    ws.onerror = () => {
      if (enabledRef.current) {
        setConnection('error');
        setError('WebSocket connection error.');
      }
    };

    ws.onclose = () => {
      if (wsRef.current === ws) wsRef.current = null;
      if (!enabledRef.current) return;
      setConnection('closed');
      scheduleReconnect();
    };
  }, [clearTimer, detach, scheduleReconnect]);

  connectRef.current = connect;

  useEffect(() => {
    enabledRef.current = enabled;
    if (enabled) {
      attemptRef.current = 0;
      connect();
    } else {
      clearTimer();
      detach();
      attemptRef.current = 0;
      setConnection('idle');
      setLast(null);
      setError(null);
    }
    return () => {
      enabledRef.current = false;
      clearTimer();
      detach();
    };
  }, [enabled, connect, clearTimer, detach]);

  const sendFrame = useCallback((base64Jpeg: string) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: 'frame', image: base64Jpeg, include_annotated: true }));
  }, []);

  return { connection, error, last, sendFrame, fpsLimit };
}

export default useScannerSocket;
