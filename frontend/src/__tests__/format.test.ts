import { describe, expect, it } from 'vitest';
import {
  STATUS_LABEL,
  confidenceTone,
  formatConfidence,
  formatDate,
  formatDateTime,
  formatPercent,
  formatWeight,
  hexForColour,
  statusTone,
} from '../utils/format';
import type { VerificationStatus } from '../types';

describe('formatWeight', () => {
  it('renders grams with one decimal', () => {
    expect(formatWeight(355)).toBe('355.0 g');
    expect(formatWeight(0)).toBe('0.0 g');
    expect(formatWeight(999.4)).toBe('999.4 g');
  });

  it('switches to kilograms with three decimals at |g| >= 1000', () => {
    expect(formatWeight(1090)).toBe('1.090 kg');
    expect(formatWeight(1500)).toBe('1.500 kg');
    expect(formatWeight(-1090)).toBe('-1.090 kg');
  });

  it('honours an explicit kg unit', () => {
    expect(formatWeight(355, 'kg')).toBe('0.355 kg');
    expect(formatWeight(1090, 'kg')).toBe('1.090 kg');
  });

  it('renders an em dash for null/undefined', () => {
    expect(formatWeight(null)).toBe('—');
    expect(formatWeight(undefined)).toBe('—');
  });
});

describe('formatPercent / formatConfidence', () => {
  it('formats percentages with the requested precision', () => {
    expect(formatPercent(0.1234)).toBe('12.3%');
    expect(formatPercent(0.1234, 0)).toBe('12%');
    expect(formatPercent(null)).toBe('—');
  });

  it('rounds confidence to whole percents', () => {
    expect(formatConfidence(0.876)).toBe('88%');
    expect(formatConfidence(0.5)).toBe('50%');
    expect(formatConfidence(undefined)).toBe('—');
  });
});

describe('confidenceTone', () => {
  it('maps boundaries to ok / warn / danger', () => {
    expect(confidenceTone(1)).toBe('ok');
    expect(confidenceTone(0.7)).toBe('ok');
    expect(confidenceTone(0.699)).toBe('warn');
    expect(confidenceTone(0.45)).toBe('warn');
    expect(confidenceTone(0.449)).toBe('danger');
    expect(confidenceTone(0)).toBe('danger');
  });
});

describe('status labels and tones', () => {
  const table: [VerificationStatus, string, string][] = [
    ['VERIFIED', 'Verified', 'ok'],
    ['REVIEW_REQUIRED', 'Review required', 'warn'],
    ['UNKNOWN_PRODUCT', 'Unknown product', 'neutral'],
    ['WEIGHT_MISMATCH', 'Weight mismatch', 'danger'],
    ['COLOUR_MISMATCH', 'Colour mismatch', 'warn'],
    ['SENSOR_UNAVAILABLE', 'Sensor unavailable', 'info'],
    ['INSUFFICIENT_EVIDENCE', 'Insufficient evidence', 'neutral'],
  ];

  it.each(table)('%s → "%s" (%s)', (status, label, tone) => {
    expect(STATUS_LABEL[status]).toBe(label);
    expect(statusTone(status)).toBe(tone);
  });
});

describe('hexForColour', () => {
  it('resolves known colour names', () => {
    expect(hexForColour('red')).toBe('#e63946');
    expect(hexForColour('grey')).toBe('#9e9e9e');
    expect(hexForColour('unknown')).toBe('#888888');
    expect(hexForColour('RED')).toBe('#e63946');
  });

  it('falls back to the neutral unknown swatch', () => {
    expect(hexForColour('chartreuse-ish')).toBe('#888888');
    expect(hexForColour(null)).toBe('#888888');
    expect(hexForColour(undefined)).toBe('#888888');
    expect(hexForColour('')).toBe('#888888');
  });
});

describe('date helpers', () => {
  it('formats a date-only yyyy-mm-dd string', () => {
    expect(formatDate('2026-03-05T12:30:00')).toBe('2026-03-05');
    expect(formatDate(null)).toBe('—');
  });

  it('formats a readable local datetime', () => {
    const out = formatDateTime('2026-03-05T12:30:00');
    expect(out).toContain('2026');
    expect(out).not.toBe('—');
    expect(formatDateTime('not-a-date')).toBe('—');
    expect(formatDateTime(undefined)).toBe('—');
  });
});
