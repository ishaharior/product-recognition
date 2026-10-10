/**
 * Display formatting helpers shared by every page/component.
 */

import type { VerificationStatus } from '../types';

export type Tone = 'ok' | 'warn' | 'danger' | 'info' | 'neutral';

/** Grams → human string. Uses kg when |g| >= 1000 (or unit === 'kg'). */
export function formatWeight(g: number | null | undefined, unit: 'g' | 'kg' = 'g'): string {
  if (g === null || g === undefined || Number.isNaN(g)) return '—';
  if (unit === 'kg' || Math.abs(g) >= 1000) return `${(g / 1000).toFixed(3)} kg`;
  return `${g.toFixed(1)} g`;
}

/** 0..1 (or already-percent) value → percentage string. */
export function formatPercent(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return `${(v * 100).toFixed(digits)}%`;
}

/** Detection confidence (0..1) → rounded percentage. */
export function formatConfidence(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return `${(v * 100).toFixed(0)}%`;
}

/** Tone used for confidence meters/badges. */
export function confidenceTone(v: number): 'ok' | 'warn' | 'danger' {
  if (v >= 0.7) return 'ok';
  if (v >= 0.45) return 'warn';
  return 'danger';
}

export const STATUS_LABEL: Record<VerificationStatus, string> = {
  VERIFIED: 'Verified',
  REVIEW_REQUIRED: 'Review required',
  UNKNOWN_PRODUCT: 'Unknown product',
  WEIGHT_MISMATCH: 'Weight mismatch',
  COLOUR_MISMATCH: 'Colour mismatch',
  SENSOR_UNAVAILABLE: 'Sensor unavailable',
  INSUFFICIENT_EVIDENCE: 'Insufficient evidence',
};

export function statusTone(status: VerificationStatus): Tone {
  switch (status) {
    case 'VERIFIED':
      return 'ok';
    case 'REVIEW_REQUIRED':
      return 'warn';
    case 'WEIGHT_MISMATCH':
      return 'danger';
    case 'COLOUR_MISMATCH':
      return 'warn';
    case 'SENSOR_UNAVAILABLE':
      return 'info';
    case 'UNKNOWN_PRODUCT':
    case 'INSUFFICIENT_EVIDENCE':
      return 'neutral';
    default:
      return 'neutral';
  }
}

/** Display label for a raw status string coming from the API. */
export function labelForStatus(raw: string): string {
  return STATUS_LABEL[raw as VerificationStatus] ?? raw;
}

/** Colour names used by the backend colour analyser → display hex. */
export const COLOUR_HEX: Record<string, string> = {
  red: '#e63946',
  orange: '#f77f00',
  yellow: '#fcbf49',
  green: '#2a9d8f',
  cyan: '#43d3d9',
  blue: '#457b9d',
  purple: '#7b5ea7',
  pink: '#e891b0',
  brown: '#8d5a2b',
  black: '#1a1a1a',
  white: '#f5f5f5',
  grey: '#9e9e9e',
  unknown: '#888888',
};

/** Hex for a colour name; falls back to the neutral 'unknown' swatch. */
export function hexForColour(name: string | null | undefined): string {
  if (!name) return COLOUR_HEX.unknown;
  return COLOUR_HEX[name.toLowerCase()] ?? COLOUR_HEX.unknown;
}

/** ISO timestamp → local readable date/time. */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

/** ISO timestamp → local yyyy-mm-dd (for charts and date filters). */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const p = (n: number): string => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}
