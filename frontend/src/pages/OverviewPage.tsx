import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, BadgeCheck, Package, ScanLine } from 'lucide-react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { api } from '../services/api';
import { useStatus } from '../hooks/useStatus';
import EmptyState from '../components/EmptyState';
import StatCard from '../components/StatCard';
import StatusBadge from '../components/StatusBadge';
import type { MetricsResponse, Scan } from '../types';
import { formatDateTime, formatPercent, formatWeight, hexForColour, labelForStatus } from '../utils/format';

const AXIS_STROKE = '#6c77a0';
const GRID_STROKE = '#263156';
const TOOLTIP_STYLE = {
  contentStyle: { background: '#151d3a', border: `1px solid ${GRID_STROKE}`, borderRadius: 8, fontSize: 12 },
  labelStyle: { color: '#9aa5c9' },
  itemStyle: { color: '#e8ecf8' },
};

export default function OverviewPage() {
  const { status } = useStatus();
  const navigate = useNavigate();
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [recent, setRecent] = useState<Scan[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = (): void => {
      Promise.all([api.metrics(), api.listScans({ limit: 8 })])
        .then(([m, scans]) => {
          if (!alive) return;
          setMetrics(m);
          setRecent(scans.items);
          setError(null);
        })
        .catch((e: unknown) => {
          if (!alive) return;
          setError(e instanceof Error ? e.message : String(e));
        });
    };
    load();
    const id = window.setInterval(load, 10000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);

  const total = metrics?.total_scans ?? 0;
  const verifiedPct = total > 0 && metrics ? formatPercent(metrics.verified_count / total, 0) : null;

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Overview</h1>
          <p className="page-sub">Station activity at a glance — scans, verifications and recent events.</p>
        </div>
      </div>

      {status?.demo.active ? <div className="demo-banner">DEMO MODE — SIMULATED DATA</div> : null}

      <div className="grid grid-4 mb-16">
        <StatCard label="Total scans" value={metrics ? total : '—'} icon={<ScanLine size={15} aria-hidden="true" />} />
        <StatCard
          label="Unique products"
          value={metrics ? metrics.unique_products : '—'}
          icon={<Package size={15} aria-hidden="true" />}
        />
        <StatCard
          label="Verified"
          value={metrics ? metrics.verified_count : '—'}
          hint={verifiedPct ? `${verifiedPct} of scans` : undefined}
          icon={<BadgeCheck size={15} aria-hidden="true" />}
        />
        <StatCard
          label="Needs attention"
          value={metrics ? metrics.review_count + metrics.mismatch_count : '—'}
          hint={metrics ? `${metrics.review_count} to review · ${metrics.mismatch_count} mismatched` : undefined}
          icon={<AlertTriangle size={15} aria-hidden="true" />}
        />
      </div>

      <div className="row wrap mb-16">
        {status ? (
          <>
            {status.inference.mode === 'baseline' ? (
              <span className="badge badge-info">Baseline COCO detector (generic objects)</span>
            ) : status.inference.mode === 'custom' ? (
              <span className="badge badge-purple">Custom product model</span>
            ) : (
              <span className="badge badge-warn">Demo</span>
            )}
            {status.sensor.backend === 'serial' && status.sensor.connected ? (
              <span className="badge badge-ok">Sensor: connected (REAL)</span>
            ) : status.sensor.backend === 'mock' ? (
              <span className="badge badge-warn">Sensor: mock (SIMULATED)</span>
            ) : (
              <span className="badge badge-neutral">Sensor: disabled</span>
            )}
          </>
        ) : (
          <span className="badge badge-neutral">Loading station status…</span>
        )}
      </div>

      {error ? <div className="notice danger mb-16">{error}</div> : null}

      <div className="grid grid-2 mb-16">
        <div className="panel">
          <h2 className="panel-title">Scans over time</h2>
          {metrics && metrics.scans_over_time.length > 0 ? (
            <div style={{ width: '100%', height: 240 }}>
              <ResponsiveContainer height={240} width="100%">
                <AreaChart data={metrics.scans_over_time} margin={{ top: 6, right: 8, left: -18, bottom: 0 }}>
                  <defs>
                    <linearGradient id="scansFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#4f8cff" stopOpacity={0.55} />
                      <stop offset="100%" stopColor="#35c3a5" stopOpacity={0.08} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke={GRID_STROKE} strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="date" stroke={AXIS_STROKE} tick={{ fontSize: 11 }} tickLine={false} />
                  <YAxis stroke={AXIS_STROKE} tick={{ fontSize: 11 }} tickLine={false} allowDecimals={false} />
                  <Tooltip {...TOOLTIP_STYLE} cursor={{ stroke: AXIS_STROKE }} />
                  <Area type="monotone" dataKey="count" stroke="#4f8cff" strokeWidth={2} fill="url(#scansFill)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyState title="No scans yet" message="Scans will appear here once the station records activity." />
          )}
        </div>

        <div className="panel">
          <h2 className="panel-title">Top products</h2>
          {metrics && metrics.top_products.length > 0 ? (
            <div style={{ width: '100%', height: 240 }}>
              <ResponsiveContainer height={240} width="100%">
                <BarChart data={metrics.top_products} margin={{ top: 6, right: 8, left: -18, bottom: 0 }}>
                  <CartesianGrid stroke={GRID_STROKE} strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="name" stroke={AXIS_STROKE} tick={{ fontSize: 11 }} tickLine={false} interval={0} />
                  <YAxis stroke={AXIS_STROKE} tick={{ fontSize: 11 }} tickLine={false} allowDecimals={false} />
                  <Tooltip {...TOOLTIP_STYLE} cursor={{ fill: 'rgba(79,140,255,0.08)' }} />
                  <Bar dataKey="count" fill="#35c3a5" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyState title="No product activity yet" message="Detected products will be ranked here." />
          )}
          {metrics && metrics.by_status.length > 0 ? (
            <div className="stack mt-8">
              {metrics.by_status.map((row) => (
                <div className="row between" key={row.status}>
                  <span className="muted">{labelForStatus(row.status)}</span>
                  <span className="mono">{row.count}</span>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      </div>

      <div className="panel">
        <h2 className="panel-title">Recent activity</h2>
        {recent.length === 0 ? (
          <EmptyState title="No recent scans" message="Start the camera or demo mode to generate activity." />
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Product / Detected</th>
                  <th>Colour</th>
                  <th>Weight</th>
                  <th>Status</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((scan) => (
                  <tr
                    key={scan.scan_id}
                    className="clickable"
                    onClick={() => navigate('/history')}
                  >
                    <td className="nowrap">{formatDateTime(scan.timestamp)}</td>
                    <td>
                      {scan.product_name || (
                        <>
                          {scan.detected_label} <span className="faint">({formatPercent(scan.confidence, 0)})</span>
                        </>
                      )}
                    </td>
                    <td className="nowrap">
                      {scan.estimated_colour ? (
                        <>
                          <span className="swatch" style={{ background: hexForColour(scan.estimated_colour) }} />
                          {scan.estimated_colour}
                        </>
                      ) : (
                        <span className="faint">—</span>
                      )}
                    </td>
                    <td className="nowrap">
                      {formatWeight(scan.measured_weight_g)}{' '}
                      {scan.weight_source === 'simulated' ? (
                        <span className="tag">SIMULATED</span>
                      ) : scan.weight_source === 'real' ? (
                        <span className="badge badge-ok">REAL</span>
                      ) : null}
                    </td>
                    <td>
                      <StatusBadge status={scan.verification_status} />
                    </td>
                    <td>
                      {scan.source === 'demo' ? (
                        <span className="badge badge-purple">demo</span>
                      ) : (
                        <span className="tag">{scan.inference_mode}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
