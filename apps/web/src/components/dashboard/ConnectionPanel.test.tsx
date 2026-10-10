import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { setCsrfToken } from '../../auth/api';
import { ConnectionPanel } from './ConnectionPanel';

const connected = {
  configured: true,
  status: 'connected',
  lastErrorCode: null,
  lastSyncedAt: null,
  scope: 'https://www.googleapis.com/auth/gmail.readonly',
};

function mockResponse(data: unknown, status = 200) {
  return {
    ok: status < 400,
    status,
    json: () => Promise.resolve(data),
  } as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
  setCsrfToken('');
});

describe('explicit Gmail connection', () => {
  it('sends CSRF credentials and reports bounded review-first sync honestly', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(mockResponse(connected))
      .mockResolvedValueOnce(
        mockResponse({
          events: 1,
          needsReview: 1,
          proposals: 0,
          extractionStatus: 'disabled',
          extractionErrorCodes: [],
        }),
      )
      .mockResolvedValueOnce(mockResponse(connected));
    vi.stubGlobal('fetch', fetcher);
    setCsrfToken('session-csrf');
    const onChanged = vi.fn(() => Promise.resolve());
    render(<ConnectionPanel onChanged={onChanged} />);
    await screen.findByText('Status: connected');
    await userEvent.click(
      screen.getByRole('button', { name: 'Sync one page' }),
    );
    expect(
      await screen.findByText(/AI extraction is disabled/),
    ).toBeInTheDocument();
    expect(fetcher.mock.calls[1]).toEqual([
      '/connections/gmail/sync',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        headers: { 'X-CSRF-Token': 'session-csrf' },
      }),
    ]);
    expect(onChanged).toHaveBeenCalledOnce();
  });

  it('does not claim provider revocation when only local disconnect succeeded', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(mockResponse(connected))
        .mockResolvedValueOnce(
          mockResponse({ disconnected: true, providerRevoked: false }),
        )
        .mockResolvedValueOnce(
          mockResponse({ ...connected, status: 'disconnected' }),
        ),
    );
    render(<ConnectionPanel />);
    await screen.findByText('Status: connected');
    await userEvent.click(
      screen.getByRole('button', { name: 'Disconnect Gmail' }),
    );
    expect(
      await screen.findByText(/Google revocation was not confirmed/),
    ).toBeInTheDocument();
  });

  it('disables unsupported actions until private server credentials are configured', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        mockResponse({
          ...connected,
          configured: false,
          status: 'disconnected',
        }),
      ),
    );
    render(<ConnectionPanel />);
    expect(
      await screen.findByRole('button', { name: 'Connect Gmail' }),
    ).toBeDisabled();
    expect(
      screen.getByRole('button', { name: 'Sync one page' }),
    ).toBeDisabled();
  });

  it('surfaces failed refresh rather than reporting success', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(mockResponse(connected))
        .mockResolvedValueOnce(
          mockResponse({ detail: { code: 'GMAIL_GRANT_REVOKED' } }, 409),
        ),
    );
    render(<ConnectionPanel />);
    await screen.findByText('Status: connected');
    await userEvent.click(
      screen.getByRole('button', { name: 'Refresh authorization' }),
    );
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'GMAIL_GRANT_REVOKED',
    );
  });

  it('aborts a pending status request when unmounted', () => {
    let signal: AbortSignal | undefined;
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string, init: RequestInit) => {
        signal = init.signal ?? undefined;
        return new Promise<Response>(() => {});
      }),
    );
    const view = render(<ConnectionPanel />);
    expect(signal?.aborted).toBe(false);
    view.unmount();
    expect(signal?.aborted).toBe(true);
  });
});
