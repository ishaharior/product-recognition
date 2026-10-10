import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import StatusBadge from '../components/StatusBadge';
import type { VerificationStatus } from '../types';

const TABLE: [VerificationStatus, string, string][] = [
  ['VERIFIED', 'Verified', 'badge-ok'],
  ['REVIEW_REQUIRED', 'Review required', 'badge-warn'],
  ['UNKNOWN_PRODUCT', 'Unknown product', 'badge-neutral'],
  ['WEIGHT_MISMATCH', 'Weight mismatch', 'badge-danger'],
  ['COLOUR_MISMATCH', 'Colour mismatch', 'badge-warn'],
  ['SENSOR_UNAVAILABLE', 'Sensor unavailable', 'badge-info'],
  ['INSUFFICIENT_EVIDENCE', 'Insufficient evidence', 'badge-neutral'],
];

describe('StatusBadge', () => {
  it.each(TABLE)('renders the label for %s', (status, label) => {
    render(<StatusBadge status={status} />);
    const badge = screen.getByText(label);
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass('badge');
  });

  it.each(TABLE)('applies the tone class for %s', (status, _label, tone) => {
    render(<StatusBadge status={status} />);
    expect(screen.getByText(_label)).toHaveClass(tone);
  });
});
