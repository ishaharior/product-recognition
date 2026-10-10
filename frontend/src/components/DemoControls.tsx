import { useState } from 'react';
import { Pause, Play, RotateCcw, Square } from 'lucide-react';
import { api } from '../services/api';
import type { DemoStatus } from '../types';

interface DemoControlsProps {
  demo: DemoStatus;
  onChange: () => void;
}

export default function DemoControls({ demo, onChange }: DemoControlsProps) {
  const [busy, setBusy] = useState(false);

  const run = async (fn: () => Promise<unknown>): Promise<void> => {
    setBusy(true);
    try {
      await fn();
    } catch {
      /* parent refresh surfaces backend state */
    } finally {
      setBusy(false);
      onChange();
    }
  };

  return (
    <div className="row wrap">
      {!demo.active ? (
        <button type="button" className="btn btn-sm btn-success" disabled={busy} onClick={() => run(api.demoStart)}>
          <Play size={14} aria-hidden="true" /> Start demo
        </button>
      ) : (
        <>
          {demo.paused ? (
            <button type="button" className="btn btn-sm" disabled={busy} onClick={() => run(api.demoResume)}>
              <Play size={14} aria-hidden="true" /> Resume
            </button>
          ) : (
            <button type="button" className="btn btn-sm" disabled={busy} onClick={() => run(api.demoPause)}>
              <Pause size={14} aria-hidden="true" /> Pause
            </button>
          )}
          <button type="button" className="btn btn-sm" disabled={busy} onClick={() => run(api.demoReset)}>
            <RotateCcw size={14} aria-hidden="true" /> Reset
          </button>
          <button type="button" className="btn btn-sm btn-danger" disabled={busy} onClick={() => run(api.demoStop)}>
            <Square size={14} aria-hidden="true" /> Stop
          </button>
        </>
      )}
      <span className="tag">{demo.events_total} events</span>
    </div>
  );
}
