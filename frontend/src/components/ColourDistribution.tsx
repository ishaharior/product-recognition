import { formatPercent, hexForColour } from '../utils/format';

interface ColourDistributionProps {
  distribution: Record<string, number>;
  quality?: string;
}

function qualityBadge(quality: string): { cls: string; label: string } {
  const q = quality.trim().toLowerCase();
  if (q === 'good') return { cls: 'badge badge-ok', label: 'Reliable' };
  if (q === 'fair') return { cls: 'badge badge-warn', label: 'Fair' };
  if (q === 'poor') return { cls: 'badge badge-danger', label: 'Poor' };
  return { cls: 'badge badge-neutral', label: quality };
}

export default function ColourDistribution({ distribution, quality }: ColourDistributionProps) {
  const entries = Object.entries(distribution ?? {}).filter(([, v]) => v > 0);

  if (entries.length === 0) {
    return <div className="faint">No colour data</div>;
  }

  const total = entries.reduce((sum, [, v]) => sum + v, 0);
  const badge = quality ? qualityBadge(quality) : null;

  return (
    <div>
      {badge ? (
        <div className="mb-8">
          <span className={badge.cls}>{badge.label}</span>
        </div>
      ) : null}
      <div className="colour-bar">
        {entries.map(([name, v]) => (
          <span
            key={name}
            style={{ width: `${((v / total) * 100).toFixed(2)}%`, background: hexForColour(name) }}
            title={`${name} ${formatPercent(v / total)}`}
          />
        ))}
      </div>
      <div className="colour-legend">
        {entries.map(([name, v]) => (
          <span key={name}>
            <span className="dot" style={{ background: hexForColour(name) }} />
            {name} {formatPercent(v / total, 0)}
          </span>
        ))}
      </div>
    </div>
  );
}
