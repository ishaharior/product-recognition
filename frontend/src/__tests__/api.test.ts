import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api } from '../services/api';

function okResponse(body: unknown): unknown {
  return { ok: true, status: 200, statusText: 'OK', json: async () => body };
}

describe('api client', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('parses JSON on a successful GET', async () => {
    fetchMock.mockResolvedValue(
      okResponse({ status: 'ok', service: 'station', version: '1.0.0', time: '2026-01-01T00:00:00Z' }),
    );

    const data = await api.health();

    expect(data.status).toBe('ok');
    expect(data.service).toBe('station');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe('/api/health');
  });

  it('throws ApiError with status and detail when the response is not ok', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 400,
      statusText: 'Bad Request',
      json: async () => ({ detail: 'boom' }),
    });

    const err = await api.demoStart().catch((e: unknown) => e);

    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 400, detail: 'boom' });
  });

  it('includes filters in the CSV export URL', () => {
    const url = api.scansExportUrl({ status: 'VERIFIED' });
    expect(url).toContain('/api/scans/export.csv');
    expect(url).toContain('status=VERIFIED');
  });

  it('POSTs to /api/demo/start for demoStart()', async () => {
    fetchMock.mockResolvedValue(
      okResponse({ ok: true, message: 'started', demo: { active: true, paused: false, tick_ms: 1500, events_total: 0, message: '' } }),
    );

    await api.demoStart();

    expect(fetchMock).toHaveBeenCalledWith('/api/demo/start', expect.objectContaining({ method: 'POST' }));
  });
});
