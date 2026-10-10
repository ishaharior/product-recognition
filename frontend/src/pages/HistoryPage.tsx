import { useEffect, useMemo, useState } from 'react';
import { Download } from 'lucide-react';
import { api } from '../services/api';
import ColourDistribution from '../components/ColourDistribution';
import EmptyState from '../components/EmptyState';
import Modal from '../components/Modal';
import StatusBadge from '../components/StatusBadge';
import type { Product, Scan, ScanFilters, ScanListResponse, VerificationStatus } from '../types';
import {
  STATUS_LABEL,
  formatConfidence,
  formatDateTime,
  formatWeight,
  hexForColour,
} from '../utils/format';

const LIMIT = 25;
const STATUSES: VerificationStatus[] = [
  'VERIFIED',
  'REVIEW_REQUIRED',
  'UNKNOWN_PRODUCT',
  'WEIGHT_MISMATCH',
  'COLOUR_MISMATCH',
  'SENSOR_UNAVAILABLE',
  'INSUFFICIENT_EVIDENCE',
];

function weightSourceTag(scan: Scan): { cls: string; label: string } {
  if (scan.weight_source === 'real') return { cls: 'badge badge-ok', label: 'REAL' };
  if (scan.weight_source === 'simulated') return { cls: 'badge badge-warn', label: 'SIMULATED' };
  return { cls: 'badge badge-neutral', label: '—' };
}

export default function HistoryPage() {
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [productId, setProductId] = useState('');
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<ScanListResponse | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [detail, setDetail] = useState<Scan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const filters: ScanFilters = useMemo(
    () => ({
      search: search || undefined,
      status: (status || undefined) as VerificationStatus | undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      product_id: productId || undefined,
    }),
    [search, status, dateFrom, dateTo, productId],
  );

  // Reset pagination whenever the filter set changes.
  useEffect(() => {
    setOffset(0);
  }, [filters]);

  // Debounced refetch (300 ms) on any filter/page change.
  useEffect(() => {
    let alive = true;
    setLoading(true);
    const t = window.setTimeout(() => {
      api
        .listScans({ ...filters, limit: LIMIT, offset })
        .then((res) => {
          if (!alive) return;
          setData(res);
          setError(null);
        })
        .catch((e: unknown) => {
          if (!alive) return;
          setError(e instanceof Error ? e.message : String(e));
        })
        .finally(() => {
          if (alive) setLoading(false);
        });
    }, 300);
    return () => {
      alive = false;
      window.clearTimeout(t);
    };
  }, [filters, offset]);

  useEffect(() => {
    let alive = true;
    api
      .listProducts({ limit: 200 })
      .then((res) => {
        if (alive) setProducts(res.items);
      })
      .catch(() => {
        /* product filter stays empty */
      });
    return () => {
      alive = false;
    };
  }, []);

  const total = data?.total ?? 0;
  const shown = data?.items.length ?? 0;
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + shown, total);

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Scan history</h1>
          <p className="page-sub">Search, filter and export every scan recorded by the station.</p>
        </div>
      </div>

      <div className="panel mb-16">
        <div className="row wrap">
          <label className="field" htmlFor="scan-search" style={{ marginBottom: 0, minWidth: 200 }}>
            <span>Search</span>
            <input
              id="scan-search"
              className="input"
              placeholder="Product, label, SKU…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <label className="field" htmlFor="scan-status" style={{ marginBottom: 0, minWidth: 180 }}>
            <span>Status</span>
            <select id="scan-status" className="select" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All statuses</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {STATUS_LABEL[s]}
                </option>
              ))}
            </select>
          </label>
          <label className="field" htmlFor="scan-from" style={{ marginBottom: 0 }}>
            <span>From</span>
            <input
              id="scan-from"
              className="input"
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
            />
          </label>
          <label className="field" htmlFor="scan-to" style={{ marginBottom: 0 }}>
            <span>To</span>
            <input
              id="scan-to"
              className="input"
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
            />
          </label>
          <label className="field" htmlFor="scan-product" style={{ marginBottom: 0, minWidth: 190 }}>
            <span>Product</span>
            <select
              id="scan-product"
              className="select"
              value={productId}
              onChange={(e) => setProductId(e.target.value)}
            >
              <option value="">All products</option>
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <a
            className="btn"
            href={api.scansExportUrl(filters)}
            target="_blank"
            rel="noreferrer"
            style={{ alignSelf: 'flex-end' }}
          >
            <Download size={15} aria-hidden="true" /> Export CSV
          </a>
        </div>
      </div>

      {error ? <div className="notice danger mb-16">{error}</div> : null}

      <div className="panel">
        <h2 className="panel-title">
          Scans
          <span className="hint">{loading ? 'loading…' : `${total} total`}</span>
        </h2>
        {!data && loading ? (
          <div className="empty-state">
            <span className="spinner" aria-hidden="true" />
          </div>
        ) : !data || shown === 0 ? (
          <EmptyState
            title="No scans match the current filters."
            message="Try clearing a filter or widen the date range."
          />
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Product</th>
                  <th>Detected</th>
                  <th>Colour</th>
                  <th>Weight</th>
                  <th>Status</th>
                  <th>Mode</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((scan) => {
                  const src = weightSourceTag(scan);
                  return (
                    <tr key={scan.scan_id} className="clickable" onClick={() => setDetail(scan)}>
                      <td className="nowrap">{formatDateTime(scan.timestamp)}</td>
                      <td className="nowrap">
                        {scan.product_name ?? (
                          <>
                            <span>—</span> <span className="faint">{scan.product_sku ?? ''}</span>
                          </>
                        )}
                      </td>
                      <td className="nowrap">
                        {scan.detected_label} <span className="faint">{formatConfidence(scan.confidence)}</span>
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
                        <span className={src.cls}>{src.label}</span>
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
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        <div className="row between mt-16">
          <span className="faint">
            Showing {from}–{to} of {total}
          </span>
          <div className="row">
            <button
              type="button"
              className="btn btn-sm"
              disabled={offset === 0}
              onClick={() => setOffset((o) => Math.max(0, o - LIMIT))}
            >
              Prev
            </button>
            <button
              type="button"
              className="btn btn-sm"
              disabled={offset + LIMIT >= total}
              onClick={() => setOffset((o) => o + LIMIT)}
            >
              Next
            </button>
          </div>
        </div>
      </div>

      {detail ? (
        <Modal
          title={`Scan ${detail.scan_id.slice(0, 8)}`}
          onClose={() => setDetail(null)}
          actions={
            <button type="button" className="btn" onClick={() => setDetail(null)}>
              Close
            </button>
          }
        >
          <div className="kv">
            <span className="k">Timestamp</span>
            <span className="v">{formatDateTime(detail.timestamp)}</span>
          </div>
          <div className="kv">
            <span className="k">Product</span>
            <span className="v">{detail.product_name ?? '—'}</span>
          </div>
          <div className="kv">
            <span className="k">SKU</span>
            <span className="v mono">{detail.product_sku ?? '—'}</span>
          </div>
          <div className="kv">
            <span className="k">Detected label</span>
            <span className="v">{detail.detected_label}</span>
          </div>
          <div className="kv">
            <span className="k">Confidence</span>
            <span className="v">{formatConfidence(detail.confidence)}</span>
          </div>
          <div className="kv">
            <span className="k">Colour</span>
            <span className="v">
              {detail.estimated_colour ? (
                <>
                  <span className="swatch" style={{ background: hexForColour(detail.estimated_colour) }} />
                  {detail.estimated_colour}
                </>
              ) : (
                '—'
              )}
            </span>
          </div>
          <div className="kv">
            <span className="k">Colour quality</span>
            <span className="v">{detail.colour_quality || '—'}</span>
          </div>
          <div className="mt-8 mb-8">
            <ColourDistribution distribution={detail.colour_distribution} quality={detail.colour_quality} />
          </div>
          <div className="kv">
            <span className="k">Measured weight</span>
            <span className="v">
              {formatWeight(detail.measured_weight_g)} ({detail.weight_unit}){' '}
              <span className={weightSourceTag(detail).cls}>{weightSourceTag(detail).label}</span>{' '}
              {detail.weight_stable ? (
                <span className="badge badge-ok">stable</span>
              ) : (
                <span className="badge badge-warn">unstable</span>
              )}
            </span>
          </div>
          <div className="kv">
            <span className="k">Expected weight</span>
            <span className="v">{formatWeight(detail.expected_weight_g)}</span>
          </div>
          <div className="kv">
            <span className="k">Weight delta</span>
            <span className="v">
              {detail.weight_delta_pct === null
                ? '—'
                : `${detail.weight_delta_pct >= 0 ? '+' : ''}${detail.weight_delta_pct.toFixed(1)}%`}
            </span>
          </div>
          <div className="kv">
            <span className="k">Verification</span>
            <span className="v">
              <StatusBadge status={detail.verification_status} />
            </span>
          </div>
          <div className="kv">
            <span className="k">Inference mode</span>
            <span className="v">{detail.inference_mode}</span>
          </div>
          <div className="kv">
            <span className="k">Source</span>
            <span className="v">
              {detail.source === 'demo' ? (
                <span className="badge badge-purple">demo (simulated)</span>
              ) : (
                <span className="badge badge-info">live</span>
              )}
            </span>
          </div>
          <div className="kv">
            <span className="k">Inference</span>
            <span className="v">{detail.inference_ms} ms</span>
          </div>
          <div className="kv">
            <span className="k">Scan ID</span>
            <span className="v mono">{detail.scan_id}</span>
          </div>

          {detail.verification_explanation ? (
            <p className="muted mt-16">{detail.verification_explanation}</p>
          ) : null}

          {detail.warnings.length > 0 ? (
            <div className="stack mt-8">
              {detail.warnings.map((w, i) => (
                <div className="notice warn" key={`${i}-${w}`}>
                  {w}
                </div>
              ))}
            </div>
          ) : null}
        </Modal>
      ) : null}
    </div>
  );
}
