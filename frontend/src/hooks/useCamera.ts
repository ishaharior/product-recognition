import { useCallback, useEffect, useRef, useState } from 'react';
import type { RefObject } from 'react';

export type CameraState = 'idle' | 'starting' | 'active' | 'denied' | 'missing' | 'error';

export interface UseCameraResult {
  videoRef: RefObject<HTMLVideoElement>;
  state: CameraState;
  error: string | null;
  start: () => Promise<void>;
  stop: () => void;
}

const CONSTRAINTS: MediaStreamConstraints = {
  video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'environment' },
  audio: false,
};

/** Browser camera capture with explicit permission/error states. */
export function useCamera(): UseCameraResult {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [state, setState] = useState<CameraState>('idle');
  const [error, setError] = useState<string | null>(null);

  const releaseStream = useCallback(() => {
    const stream = streamRef.current;
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    const video = videoRef.current;
    if (video) video.srcObject = null;
  }, []);

  const attach = useCallback(async (): Promise<void> => {
    const video = videoRef.current;
    const stream = streamRef.current;
    if (!video || !stream || video.srcObject === stream) return;
    video.srcObject = stream;
    video.muted = true;
    video.playsInline = true;
    try {
      await video.play();
    } catch {
      /* autoplay may be blocked until a user gesture; controls already require one */
    }
  }, []);

  const stop = useCallback((): void => {
    releaseStream();
    setState('idle');
    setError(null);
  }, [releaseStream]);

  const start = useCallback(async (): Promise<void> => {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setState('error');
      setError('Camera API is unavailable in this browser or context.');
      return;
    }
    setState('starting');
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia(CONSTRAINTS);
      streamRef.current = stream;
      await attach();
      // If the <video> is not mounted yet it attaches via the effect below.
      setState('active');
    } catch (e: unknown) {
      releaseStream();
      const name = typeof e === 'object' && e !== null && 'name' in e ? String((e as { name: unknown }).name) : '';
      const message = typeof e === 'object' && e !== null && 'message' in e ? String((e as { message: unknown }).message) : '';
      if (name === 'NotAllowedError' || name === 'SecurityError') {
        setState('denied');
        setError(
          'Camera permission denied. Allow camera access for this site in your browser settings, then retry. Note: localhost is a secure context — any other origin must be served over https.',
        );
      } else if (name === 'NotFoundError' || name === 'OverconstrainedError' || name === 'DevicesNotFoundError') {
        setState('missing');
        setError('No camera device found. Connect a camera and retry.');
      } else {
        setState('error');
        setError(message || 'Could not start the camera.');
      }
    }
  }, [attach, releaseStream]);

  // Attach the stream once the <video> element mounts (it only renders when active).
  useEffect(() => {
    if (state === 'active' && streamRef.current && videoRef.current && !videoRef.current.srcObject) {
      void attach();
    }
  }, [state, attach]);

  // Auto-stop on unmount.
  useEffect(() => {
    return () => {
      const stream = streamRef.current;
      if (stream) stream.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    };
  }, []);

  return { videoRef, state, error, start, stop };
}

export default useCamera;
