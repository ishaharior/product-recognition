import { confidenceTone, formatConfidence } from '../utils/format';

export default function ConfidenceMeter({ value }: { value: number }) {
  const clamped = Math.max(0, Math.min(1, Number.isNaN(value) ? 0 : value));
  const tone = confidenceTone(clamped);
  const meterClass = tone === 'ok' ? 'meter' : `meter ${tone}`;
  return (
    <div>
      <div className="row between mb-8">
        <span className="muted">Confidence</span>
        <span className="mono">{formatConfidence(clamped)}</span>
      </div>
      <div className={meterClass}>
        <span style={{ width: `${(clamped * 100).toFixed(1)}%` }} />
      </div>
    </div>
  );
}
