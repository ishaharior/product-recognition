import { useEffect, useRef, useState } from 'react';
import { Camera, Square } from 'lucide-react';
import { useStatus } from '../hooks/useStatus';
import { useCamera } from '../hooks/useCamera';
import { useScannerSocket } from '../hooks/useScannerSocket';
import ColourDistribution from '../components/ColourDistribution';
import ConfidenceMeter from '../components/ConfidenceMeter';
import DemoControls from '../components/DemoControls';
import EmptyState from '../components/EmptyState';
import StatusBadge from '../components/StatusBadge';
import type { InferenceMode, VerificationStatus, WSDetectionMessage } from '../types';
import { formatWeight, hexForColour } from '../utils/format';

function modeLabel(mode: InferenceMode | undefined): string {
  if (mode === 'demo') return 'DEMO';
  if (mode === 'custom') return 'Custom';
  if (mode === 'baseline') return 'Baseline';
  return '—';
}

function verificationColour(v: VerificationStatus): string {
  if (v === 'VERIFIED') return '#2fbf71';
  if (v === 'WEIGHT_MISMATCH' || v === 'UNKNOWN_PRODUCT') return '#ef5f6b';
  return '#f2b036';
}

export default function LiveScannerPage() {
  const { status, refresh } = useStatus();
  const camera = useCamera();
  const demoActive = status?.demo.active ?? false;

  // Deviation note: the socket also stays open while demo mode runs so the
  // backend's demo broadcast (annotated synthetic frames) can be rendered.
  const socket = useScannerSocket(demoActive || (camera.state === 'active' && !demoActive));

  const [message, setMessage] = useState<WSDetectionMessage | null>(null);
  const [showBoxes, setShowBoxes] = useState(true);
  const [frameSize, setFrameSize] = useState<{ w: number; h: number } | null>(null);
  const [stageSize, setStageSize] = useState<{ w: number; h: number } | null>(null);

  const stageRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const primary = message?.primary ?? null;
  const mode = message?.mode ?? status?.inference.mode;

  // Latest detection (the socket keeps every message in `last`).
  useEffect(() => {
    const last = socket.last;
    if (!last) return;
    if (last.type === 'detection' || last.type === 'demo') setMessage(last);
  }, [socket.last]);

  // Never show stale frames from the previous mode.
  useEffect(() => {
    setMessage(null);
  }, [demoActive]);

  // Track the stage box so overlays can be remapped on resize.
  useEffect(() => {
    const el = stageRef.current;
    if (!el) return;
    const measure = (): void => {
      const rect = el.getBoundingClientRect();
      setStageSize({ w: rect.width, h: rect.height });
    };
    measure();
    if (typeof ResizeObserver !== 'undefined') {
      const ro = new ResizeObserver(measure);
      ro.observe(el);
      return () => ro.disconnect();
    }
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, []);

  // Draw bounding boxes mapped from the SENT frame coords onto the displayed video.
  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx || !stageSize) return;

    const dpr = window.devicePixelRatio || 1;
    const { w, h } = stageSize;
    canvas.width = Math.max(1, Math.round(w * dpr));
    canvas.height = Math.max(1, Math.round(h * dpr));
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    if (!showBoxes || camera.state !== 'active') return;
    const boxes = message?.boxes;
    if (!boxes || boxes.length === 0 || !frameSize || frameSize.w <= 0 || frameSize.h <= 0) return;

    // object-fit: contain → letterboxed content rect inside the stage.
    const scale = Math.min(w / frameSize.w, h / frameSize.h);
    const offsetX = (w - frameSize.w * scale) / 2;
    const offsetY = (h - frameSize.h * scale) / 2;

    ctx.lineWidth = 2;
    ctx.font = '600 12px "Segoe UI", system-ui, sans-serif';
    ctx.textBaseline = 'middle';

    for (const box of boxes) {
      const x = offsetX + box.x1 * scale;
      const y = offsetY + box.y1 * scale;
      const bw = Math.max(2, (box.x2 - box.x1) * scale);
      const bh = Math.max(2, (box.y2 - box.y1) * scale);
      ctx.strokeStyle = box.is_product ? '#35c3a5' : '#4f8cff';
      ctx.strokeRect(x, y, bw, bh);

      const label = `${box.label} ${Math.round(box.confidence * 100)}%`;
      const tw = ctx.measureText(label).width;
      const labelY = Math.max(0, y - 20);
      ctx.fillStyle = 'rgba(5, 8, 18, 0.78)';
      ctx.fillRect(x, labelY, tw + 12, 18);
      ctx.fillStyle = '#ffffff';
      ctx.fillText(label, x + 6, labelY + 9);
    }

    const primaryBox = message?.primary;
    if (primaryBox?.verification) {
      const x = offsetX + primaryBox.x1 * scale;
      const y = offsetY + primaryBox.y1 * scale;
      const bw = Math.max(2, (primaryBox.x2 - primaryBox.x1) * scale);
      const bh = Math.max(2, (primaryBox.y2 - primaryBox.y1) * scale);
      ctx.lineWidth = 3;
      ctx.strokeStyle = verificationColour(primaryBox.verification);
      ctx.strokeRect(x, y, bw, bh);
      ctx.lineWidth = 2;
    }
  }, [message, showBoxes, frameSize, stageSize, camera.state]);

  // Frame loop: grab the video at the backend's fps limit and stream JPEG frames.
  useEffect(() => {
    if (camera.state !== 'active' || demoActive || socket.connection !== 'open') return;
    const video = camera.videoRef.current;
    if (!video) return;

    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const interval = Math.max(50, 1000 / Math.max(1, socket.fpsLimit));
    const id = window.setInterval(() => {
      const v = camera.videoRef.current;
      if (!v || !v.videoWidth || v.videoHeight === 0 || v.paused || v.readyState < 2) return;
      const scale = Math.min(640 / v.videoWidth, 640 / v.videoHeight, 1);
      const w = Math.max(1, Math.round(v.videoWidth * scale));
      const h = Math.max(1, Math.round(v.videoHeight * scale));
      if (canvas.width !== w) canvas.width = w;
      if (canvas.height !== h) canvas.height = h;
      ctx.drawImage(v, 0, 0, w, h);
      const dataUrl = canvas.toDataURL('image/jpeg', 0.7);
      const base64 = dataUrl.replace(/^data:image\/jpeg;base64,/, '');
      setFrameSize((prev) => (prev && prev.w === w && prev.h === h ? prev : { w, h }));
      socket.sendFrame(base64);
    }, interval);

    return () => window.clearInterval(id);
  }, [camera.state, camera.videoRef, demoActive, socket.connection, socket.fpsLimit, socket.sendFrame]);

  const stopCamera = (): void => {
    camera.stop();
    setMessage(null);
    setFrameSize(null);
  };

  const connectionLost =
    camera.state === 'active' && (socket.connection === 'error' || socket.connection === 'closed');

  const measuredWeight = primary?.weight_g ?? null;
  const expectedWeight = primary?.expected_weight_g ?? null;
  const deltaPct =
    measuredWeight !== null && expectedWeight !== null && expectedWeight !== 0
      ? ((measuredWeight - expectedWeight) / expectedWeight) * 100
      : null;
  const deltaColour =
    deltaPct === null
      ? undefined
      : Math.abs(deltaPct) > 10
        ? '#ff9ba4'
        : Math.abs(deltaPct) > 5
          ? '#ffd88a'
          : undefined;

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Live Scanner</h1>
          <p className="page-sub">
            Browser camera → backend inference → multimodal verification (vision + colour + weight).
          </p>
        </div>
      </div>

      {demoActive ? <div className="demo-banner">DEMO MODE — SIMULATED DATA</div> : null}

      <div className="scanner-grid">
        <div className="panel">
          <h2 className="panel-title">
            Camera stage
            <span className="hint">{demoActive ? 'simulated feed' : 'live feed'}</span>
          </h2>

          <div className="camera-stage" ref={stageRef}>
            <div className="stage-hud">
              <span className={`hud-chip${socket.connection === 'open' ? ' ok' : ''}`}>
                {socket.connection === 'open' ? 'WS connected' : `WS ${socket.connection}`}
              </span>
              {typeof message?.fps === 'number' ? <span className="hud-chip">{message.fps} fps</span> : null}
              {typeof message?.inference_ms === 'number' ? (
                <span className="hud-chip">{message.inference_ms} ms</span>
              ) : null}
              <span className="hud-chip">{modeLabel(mode)}</span>
              <span className="hud-chip">{camera.state === 'active' ? 'camera on' : 'camera off'}</span>
              {demoActive ? (
                <>
                  <span className="hud-chip live">DEMO</span>
                  <span className="hud-chip">SIMULATED DATA</span>
                </>
              ) : null}
            </div>

            {demoActive ? (
              message?.annotated ? (
                <img
                  className="feed"
                  src={`data:image/jpeg;base64,${message.annotated}`}
                  alt="Annotated demo detection frame (simulated data)"
                />
              ) : (
                <div className="camera-placeholder">
                  <div className="big">
                    <Camera size={40} aria-hidden="true" />
                  </div>
                  <div>Waiting for the first demo frame…</div>
                  <div className="faint">Synthetic detections stream in while demo mode runs.</div>
                </div>
              )
            ) : camera.state === 'active' ? (
              <>
                <video ref={camera.videoRef} autoPlay playsInline muted />
                <canvas className="overlay" ref={canvasRef} />
              </>
            ) : (
              <div className="camera-placeholder">
                <div className="big">
                  <Camera size={40} aria-hidden="true" />
                </div>
                <div>Camera is off</div>
                <div className="faint">Start the camera to capture frames, or run demo mode for simulated data.</div>
              </div>
            )}
          </div>

          {connectionLost ? <div className="notice warn mt-8">Connection lost — retrying…</div> : null}

          {camera.state === 'denied' ? (
            <div className="notice danger mt-8">
              <div>{camera.error}</div>
              <div className="mt-8">
                Fix: open your browser’s site settings for this page and allow the camera, then press retry.
                localhost is a secure context — any other origin must be served over https.
              </div>
              <button type="button" className="btn btn-sm btn-primary mt-8" onClick={() => void camera.start()}>
                Retry
              </button>
            </div>
          ) : null}
          {camera.state === 'missing' ? (
            <div className="notice warn mt-8">
              {camera.error}
              <div className="mt-8">
                <button type="button" className="btn btn-sm" onClick={() => void camera.start()}>
                  Retry
                </button>
              </div>
            </div>
          ) : null}
          {camera.state === 'error' && camera.error ? (
            <div className="notice danger mt-8">{camera.error}</div>
          ) : null}

          <div className="row wrap mt-16">
            {camera.state === 'active' ? (
              <button type="button" className="btn btn-danger" onClick={stopCamera}>
                <Square size={15} aria-hidden="true" /> Stop camera
              </button>
            ) : camera.state === 'starting' ? (
              <button type="button" className="btn btn-primary" disabled>
                <span className="spinner" aria-hidden="true" /> Starting camera…
              </button>
            ) : (
              <button type="button" className="btn btn-primary" onClick={() => void camera.start()}>
                <Camera size={15} aria-hidden="true" /> Start camera
              </button>
            )}

            {status ? <DemoControls demo={status.demo} onChange={refresh} /> : null}

            <label className="row" htmlFor="show-boxes">
              <input
                id="show-boxes"
                type="checkbox"
                checked={showBoxes}
                onChange={(e) => setShowBoxes(e.target.checked)}
              />
              Show bounding boxes
            </label>
          </div>
        </div>

        <div className="stack">
          <div className="panel">
            <h2 className="panel-title">Detection</h2>
            {!message || !primary ? (
              <EmptyState
                title="No detection yet"
                message="Start the camera or demo mode… detections appear here."
              />
            ) : (
              <div>
                <div className="row between mb-8">
                  <strong>{primary.product_name || primary.label}</strong>
                  {primary.verification ? <StatusBadge status={primary.verification} /> : null}
                </div>
                {primary.product_name ? <span className="tag mb-8">{primary.label}</span> : null}
                <div className="mt-8">
                  <ConfidenceMeter value={primary.confidence} />
                </div>
                {primary.explanation ? <p className="muted mt-8">{primary.explanation}</p> : null}
                <div className="mt-8">
                  <div className="kv">
                    <span className="k">Scan ID</span>
                    <span className="v mono truncate">{message.scan_id ?? '—'}</span>
                  </div>
                  <div className="kv">
                    <span className="k">Mode</span>
                    <span className="v">{modeLabel(message.mode ?? mode)}</span>
                  </div>
                  <div className="kv">
                    <span className="k">Inference</span>
                    <span className="v">{typeof message.inference_ms === 'number' ? `${message.inference_ms} ms` : '—'}</span>
                  </div>
                  <div className="kv">
                    <span className="k">Boxes</span>
                    <span className="v">{message.boxes?.length ?? 0}</span>
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="panel">
            <h2 className="panel-title">Colour</h2>
            {primary ? (
              <>
                <ColourDistribution distribution={primary.colour_distribution} quality={primary.colour_quality} />
                <div className="mt-8">
                  <div className="kv">
                    <span className="k">Estimated colour</span>
                    <span className="v">
                      <span className="swatch" style={{ background: hexForColour(primary.colour) }} />
                      {primary.colour ?? '—'}
                    </span>
                  </div>
                  <div className="kv">
                    <span className="k">Quality</span>
                    <span className="v">{primary.colour_quality || '—'}</span>
                  </div>
                </div>
              </>
            ) : (
              <div className="faint">No colour data yet.</div>
            )}
          </div>

          <div className="panel">
            <h2 className="panel-title">Weight</h2>
            {primary ? (
              <>
                <div className="kv">
                  <span className="k">Measured</span>
                  <span className="v">
                    {formatWeight(primary.weight_g)}{' '}
                    {primary.weight_source === 'real' ? (
                      <span className="badge badge-ok">REAL SENSOR</span>
                    ) : primary.weight_source === 'simulated' ? (
                      <span className="badge badge-warn">SIMULATED</span>
                    ) : (
                      <span className="badge badge-neutral">—</span>
                    )}
                  </span>
                </div>
                <div className="kv">
                  <span className="k">Expected</span>
                  <span className="v">{formatWeight(primary.expected_weight_g)}</span>
                </div>
                <div className="kv">
                  <span className="k">Stability</span>
                  <span className="v">
                    {primary.weight_stable ? (
                      <span className="badge badge-ok">stable</span>
                    ) : (
                      <span className="badge badge-warn">not stable</span>
                    )}
                  </span>
                </div>
                <div className="kv">
                  <span className="k">Delta</span>
                  <span className="v" style={deltaColour ? { color: deltaColour } : undefined}>
                    {deltaPct === null
                      ? '—'
                      : `${deltaPct >= 0 ? '+' : ''}${deltaPct.toFixed(1)}%`}
                  </span>
                </div>
              </>
            ) : (
              <div className="faint">No weight reading yet.</div>
            )}
          </div>

          {message?.warnings && message.warnings.length > 0 ? (
            <div className="panel">
              <h2 className="panel-title">Warnings</h2>
              <div className="stack">
                {message.warnings.map((w, i) => (
                  <div className="notice warn" key={`${i}-${w}`}>
                    {w}
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {socket.error ? <div className="notice warn">{socket.error}</div> : null}
        </div>
      </div>
    </div>
  );
}
