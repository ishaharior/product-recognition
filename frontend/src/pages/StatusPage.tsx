import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { ApiError, api } from '../services/api';
import { useStatus } from '../hooks/useStatus';
import DemoControls from '../components/DemoControls';
import type { HealthResponse, InferenceMode } from '../types';
import { formatWeight } from '../utils/format';

interface ActionResult {
  kind: 'info' | 'danger';
  text: string;
}

function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.detail;
  if (e instanceof Error) return e.message;
  return String(e);
}

function modeBadge(mode: InferenceMode): { cls: string; label: string } {
  if (mode === 'baseline') return { cls: 'badge badge-info', label: 'Baseline' };
  if (mode === 'custom') return { cls: 'badge badge-purple', label: 'Custom' };
  return { cls: 'badge badge-warn', label: 'Demo' };
}

export default function StatusPage() {
  const { status, error, refresh } = useStatus(4000);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [actionResult, setActionResult] = useState<ActionResult | null>(null);

  const [showCalibrate, setShowCalibrate] = useState(false);
  const [calRef, setCalRef] = useState('100');
  const [calSamples, setCalSamples] = useState('10');
  const [calResult, setCalResult] = useState<ActionResult | null>(null);

  const loadHealth = (): void => {
    api
      .health()
      .then(setHealth)
      .catch(() => setHealth(null));
  };

  useEffect(() => {
    loadHealth();
  }, []);

  const runAction = async (fn: () => Promise<ActionResult | void>): Promise<void> => {
    setRefreshing(true);
    try {
      const result = await fn();
      if (result) setActionResult(result);
    } catch (e: unknown) {
      setActionResult({ kind: 'danger', text: errorMessage(e) });
    } finally {
      setRefreshing(false);
      refresh();
      loadHealth();
    }
  };

  const doTare = (): Promise<ActionResult | void> =>
    runAction(async () => {
      const r = await api.sensorTare();
      return { kind: r.ok ? 'info' : 'danger', text: r.message } satisfies ActionResult;
    });

  const doCalibrate = (e: FormEvent): void => {
    e.preventDefault();
    const reference = Number(calRef);
    if (!Number.isFinite(reference) || reference <= 0) {
      setCalResult({ kind: 'danger', text: 'Enter a positive reference weight in grams.' });
      return;
    }
    void runAction(async () => {
      try {
        const r = await api.sensorCalibrate(reference, Number(calSamples));
        setCalResult(
          r.ok
            ? { kind: 'info', text: `Calibration factor: ${r.calibration_factor}` }
            : { kind: 'danger', text: r.message },
        );
      } catch (err: unknown) {
        setCalResult({ kind: 'danger', text: errorMessage(err) });
      }
    });
  };

  const inference = status?.inference;
  const sensor = status?.sensor;
  const dataset = status?.dataset;
  const mode = inference ? modeBadge(inference.mode) : null;
  const classes = inference?.classes ?? [];

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Model &amp; hardware status</h1>
          <p className="page-sub">Detector, weight sensor, camera, dataset and demo runtime at a glance.</p>
        </div>
        <div className="page-actions">
          <button
            type="button"
            className="btn"
            disabled={refreshing}
            onClick={() => {
              refresh();
              loadHealth();
            }}
          >
            {refreshing ? 'Working…' : 'Refresh'}
          </button>
        </div>
      </div>

      {error ? <div className="notice danger mb-16">Status unreachable: {error}</div> : null}
      {actionResult ? <div className={`notice ${actionResult.kind} mb-16`}>{actionResult.text}</div> : null}

      <div className="grid grid-2">
        <div className="panel">
          <h2 className="panel-title">Model</h2>
          {!inference ? (
            <div className="faint">Loading…</div>
          ) : (
            <>
              <div className="kv">
                <span className="k">Mode</span>
                <span className="v">
                  <span className={mode?.cls}>{mode?.label}</span>
                </span>
              </div>
              <div className="kv">
                <span className="k">Model name</span>
                <span className="v">{inference.model_name || '—'}</span>
              </div>
              <div className="kv">
                <span className="k">Classes</span>
                <span className="v">{inference.class_count}</span>
              </div>
              <div className="row wrap mt-8">
                {classes.slice(0, 12).map((c) => (
                  <span className="tag" key={c}>
                    {c}
                  </span>
                ))}
                {classes.length > 12 ? <span className="faint">…</span> : null}
              </div>
              <div className="kv mt-8">
                <span className="k">Weights</span>
                <span className="v">
                  <span className="mono truncate">{inference.weights_path || '—'}</span>{' '}
                  {inference.weights_present ? (
                    <span className="badge badge-ok">present</span>
                  ) : (
                    <span className="badge badge-danger">missing</span>
                  )}
                </span>
              </div>
              <div className="kv">
                <span className="k">Available</span>
                <span className="v">
                  {inference.available ? (
                    <span className="badge badge-ok">available</span>
                  ) : (
                    <span className="badge badge-danger">unavailable</span>
                  )}
                </span>
              </div>
              {inference.message ? <div className="notice info mt-8">{inference.message}</div> : null}
              {inference.is_generic_detector && inference.mode === 'baseline' ? (
                <div className="notice warn mt-8">
                  Baseline mode = generic COCO object detection (person, bottle, cup…), not exact SKU recognition.
                  Train a custom model for product-level identity — see docs/MODEL_TRAINING.md.
                </div>
              ) : null}
            </>
          )}
        </div>

        <div className="panel">
          <h2 className="panel-title">Sensor</h2>
          {!sensor ? (
            <div className="faint">Loading…</div>
          ) : (
            <>
              <div className="row mb-8">
                {sensor.backend === 'serial' ? (
                  <span className="badge badge-info">Serial HX711</span>
                ) : sensor.backend === 'mock' ? (
                  <span className="badge badge-warn">Mock (simulated)</span>
                ) : (
                  <span className="badge badge-neutral">Disabled</span>
                )}
              </div>
              <div className="kv">
                <span className="k">Connected</span>
                <span className="v">
                  {sensor.connected ? (
                    <span className="badge badge-ok">yes</span>
                  ) : (
                    <span className="badge badge-danger">no</span>
                  )}
                </span>
              </div>
              <div className="kv">
                <span className="k">Calibrated</span>
                <span className="v">
                  {sensor.calibrated ? (
                    <span className="badge badge-ok">yes</span>
                  ) : (
                    <span className="badge badge-warn">no</span>
                  )}
                </span>
              </div>
              <div className="kv">
                <span className="k">Simulated</span>
                <span className="v">
                  {sensor.simulated ? (
                    <span className="badge badge-warn">SIMULATED</span>
                  ) : (
                    <span className="badge badge-neutral">no</span>
                  )}
                </span>
              </div>
              <div className="kv">
                <span className="k">Port</span>
                <span className="v mono">{sensor.port ?? '—'}</span>
              </div>
              <div className="kv">
                <span className="k">Last reading</span>
                <span className="v">
                  {formatWeight(sensor.last_reading_g)}{' '}
                  {sensor.simulated ? <span className="tag">SIMULATED</span> : null}
                </span>
              </div>
              <div className="kv">
                <span className="k">Stable</span>
                <span className="v">
                  {sensor.stable ? (
                    <span className="badge badge-ok">stable</span>
                  ) : (
                    <span className="badge badge-warn">unstable</span>
                  )}
                </span>
              </div>
              <div className="kv">
                <span className="k">Message</span>
                <span className="v faint">{sensor.message || '—'}</span>
              </div>

              <div className="row wrap mt-8">
                <button type="button" className="btn btn-sm" disabled={refreshing} onClick={() => void doTare()}>
                  Tare
                </button>
                <button
                  type="button"
                  className="btn btn-sm"
                  disabled={refreshing}
                  onClick={() => setShowCalibrate((v) => !v)}
                >
                  Calibrate
                </button>
              </div>

              {showCalibrate ? (
                <form className="mt-8" onSubmit={doCalibrate}>
                  <div className="form-row">
                    <div className="field">
                      <label htmlFor="cal-weight">Reference weight (g)</label>
                      <input
                        id="cal-weight"
                        className="input"
                        inputMode="decimal"
                        value={calRef}
                        onChange={(e) => setCalRef(e.target.value)}
                      />
                    </div>
                    <div className="field">
                      <label htmlFor="cal-samples">Samples</label>
                      <select
                        id="cal-samples"
                        className="select"
                        value={calSamples}
                        onChange={(e) => setCalSamples(e.target.value)}
                      >
                        <option value="5">5</option>
                        <option value="10">10</option>
                        <option value="20">20</option>
                      </select>
                    </div>
                  </div>
                  <button type="submit" className="btn btn-sm btn-primary" disabled={refreshing}>
                    Confirm
                  </button>
                </form>
              ) : null}
              {calResult ? <div className={`notice ${calResult.kind} mt-8`}>{calResult.text}</div> : null}
              <div className="faint mt-8">Calibration: place a known reference weight after taring.</div>
            </>
          )}
        </div>

        <div className="panel">
          <h2 className="panel-title">Camera</h2>
          <p className="muted">
            Browser-side camera (not accessed until you press Start on the Live Scanner).
          </p>
          <div className="notice info mt-8">
            Camera access requires a secure context: localhost is allowed over http; any other origin must be served
            over https.
          </div>
        </div>

        <div className="panel">
          <h2 className="panel-title">Dataset</h2>
          {!dataset ? (
            <div className="faint">Loading…</div>
          ) : (
            <>
              <div className="kv">
                <span className="k">Config</span>
                <span className="v mono truncate">{dataset.config_path}</span>
              </div>
              <div className="kv">
                <span className="k">Config exists</span>
                <span className="v">
                  {dataset.config_exists ? (
                    <span className="badge badge-ok">yes</span>
                  ) : (
                    <span className="badge badge-neutral">no</span>
                  )}
                </span>
              </div>
              <div className="kv">
                <span className="k">Prepared datasets</span>
                <span className="v">
                  {dataset.prepared_datasets.length > 0 ? (
                    <span className="row wrap" style={{ justifyContent: 'flex-end' }}>
                      {dataset.prepared_datasets.map((d) => (
                        <span className="tag" key={d}>
                          {d}
                        </span>
                      ))}
                    </span>
                  ) : (
                    'none'
                  )}
                </span>
              </div>
              <div className="kv">
                <span className="k">Message</span>
                <span className="v faint">{dataset.message || '—'}</span>
              </div>
              <div className="faint mt-8">
                See docs/DATASETS.md — <a href="#/about">About page</a> summarises the citations.
              </div>
            </>
          )}
        </div>

        <div className="panel">
          <h2 className="panel-title">Demo</h2>
          {!status ? (
            <div className="faint">Loading…</div>
          ) : (
            <>
              <div className="row wrap mb-8">
                {status.demo.active ? (
                  status.demo.paused ? (
                    <span className="badge badge-warn">active · paused</span>
                  ) : (
                    <span className="badge badge-warn">active · running</span>
                  )
                ) : (
                  <span className="badge badge-neutral">inactive</span>
                )}
                <span className="tag">{status.demo.events_total} events</span>
                <span className="tag">tick {status.demo.tick_ms} ms</span>
              </div>
              <p className="faint">{status.demo.message}</p>
              <div className="mt-8">
                <DemoControls demo={status.demo} onChange={refresh} />
              </div>
            </>
          )}
        </div>

        <div className="panel">
          <h2 className="panel-title">Connection</h2>
          {health ? (
            <>
              <div className="kv">
                <span className="k">Service</span>
                <span className="v">{health.service}</span>
              </div>
              <div className="kv">
                <span className="k">Version</span>
                <span className="v mono">{health.version}</span>
              </div>
              <div className="kv">
                <span className="k">Time</span>
                <span className="v">{new Date(health.time).toLocaleString()}</span>
              </div>
              <div className="kv">
                <span className="k">Health</span>
                <span className="v">
                  {health.status === 'ok' ? (
                    <span className="badge badge-ok">ok</span>
                  ) : (
                    <span className="badge badge-warn">degraded</span>
                  )}
                </span>
              </div>
            </>
          ) : (
            <div className="notice danger">Backend health endpoint unreachable — is it running on localhost:8000?</div>
          )}
        </div>
      </div>

      <div className="panel mt-16">
        <h2 className="panel-title">Troubleshooting</h2>
        <ul className="prose">
          <li>
            <strong>Camera permission denied</strong> — allow the camera for this site in your browser settings, then
            press Retry on the Live Scanner page.
          </li>
          <li>
            <strong>No detections in baseline mode</strong> — the baseline model is a generic COCO detector; point the
            camera at everyday objects (bottle, apple, person, cup, cell phone…).
          </li>
          <li>
            <strong>COM port busy</strong> — close serial monitors / Arduino IDE plotter before starting the backend so
            the HX711 port can be opened.
          </li>
          <li>
            <strong>CORS errors</strong> — the backend <code>CORS_ORIGINS</code> setting must include the frontend
            origin (for Vite dev that is http://localhost:5173).
          </li>
          <li>
            <strong>Custom weights missing</strong> — set <code>CUSTOM_WEIGHTS</code> to a trained YOLO weights file
            (or stay in baseline/demo mode).
          </li>
        </ul>
      </div>
    </div>
  );
}
