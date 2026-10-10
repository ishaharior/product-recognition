/**
 * Typed API client for the Smart Product Station backend.
 * All calls go through `VITE_API_BASE` (defaults to same-origin `/api`).
 */

import type {
  CalibrateResponse,
  DemoControlResponse,
  HealthResponse,
  MetricsResponse,
  Product,
  ProductListResponse,
  ProductPayload,
  Scan,
  ScanFilters,
  ScanListResponse,
  SensorReadingResponse,
  SensorStatus,
  StatusResponse,
  TareResponse,
} from '../types';

const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api';

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (typeof body?.detail === 'string') detail = body.detail;
      else if (Array.isArray(body?.detail)) detail = body.detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join('; ');
    } catch {
      /* keep default detail */
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    search.set(key, String(value));
  }
  const str = search.toString();
  return str ? `?${str}` : '';
}

export const api = {
  // health / status
  health: () => request<HealthResponse>('/health'),
  status: () => request<StatusResponse>('/status'),

  // products
  listProducts: (params: { search?: string; category?: string; active_only?: boolean; limit?: number; offset?: number } = {}) =>
    request<ProductListResponse>(`/products${qs(params as Record<string, string | number | boolean | undefined>)}`),
  getProduct: (id: string) => request<Product>(`/products/${encodeURIComponent(id)}`),
  createProduct: (payload: ProductPayload) =>
    request<Product>('/products', { method: 'POST', body: JSON.stringify(payload) }),
  updateProduct: (id: string, payload: Partial<ProductPayload>) =>
    request<Product>(`/products/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(payload) }),
  deleteProduct: (id: string) => request<void>(`/products/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  // scans
  listScans: (filters: ScanFilters = {}) =>
    request<ScanListResponse>(`/scans${qs(filters as Record<string, string | number | undefined>)}`),
  getScan: (id: string) => request<Scan>(`/scans/${encodeURIComponent(id)}`),
  scansExportUrl: (filters: ScanFilters = {}) =>
    `${API_BASE}/scans/export.csv${qs(filters as Record<string, string | number | undefined>)}`,

  // metrics
  metrics: () => request<MetricsResponse>('/metrics'),

  // demo controls
  demoStart: () => request<DemoControlResponse>('/demo/start', { method: 'POST' }),
  demoStop: () => request<DemoControlResponse>('/demo/stop', { method: 'POST' }),
  demoPause: () => request<DemoControlResponse>('/demo/pause', { method: 'POST' }),
  demoResume: () => request<DemoControlResponse>('/demo/resume', { method: 'POST' }),
  demoReset: () => request<DemoControlResponse>('/demo/reset', { method: 'POST' }),

  // sensor
  sensorStatus: () => request<SensorStatus>('/sensor/status'),
  sensorReading: () => request<SensorReadingResponse>('/sensor/reading'),
  sensorTare: () => request<TareResponse>('/sensor/tare', { method: 'POST' }),
  sensorCalibrate: (reference_weight_g: number, samples = 10) =>
    request<CalibrateResponse>('/sensor/calibrate', {
      method: 'POST',
      body: JSON.stringify({ reference_weight_g, samples }),
    }),
};

/** Resolve the backend origin for WebSocket URLs (dev: Vite proxy not used for WS). */
export function wsUrl(): string {
  const explicit = import.meta.env.VITE_WS_URL as string | undefined;
  if (explicit) return explicit;
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = import.meta.env.DEV ? 'localhost:8000' : window.location.host;
  return `${proto}//${host}/ws/scan`;
}
