import { useCallback, useEffect, useRef, useState } from 'react';

import { apiRequest } from '../../auth/api';

interface ConnectionStatus {
  configured: boolean;
  status: 'connected' | 'disconnected' | 'error' | 'revoked';
  lastErrorCode: string | null;
  lastSyncedAt: string | null;
  scope: string;
}

export function ConnectionPanel({
  onChanged,
}: {
  onChanged?: () => Promise<void>;
}) {
  const [connection, setConnection] = useState<ConnectionStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const lifecycle = useRef<AbortController | null>(null);
  const mounted = useRef(false);
  const reload = useCallback(async () => {
    try {
      const result = await apiRequest<ConnectionStatus>(
        '/connections/gmail/status',
        'GET',
        lifecycle.current?.signal,
      );
      if (mounted.current) setConnection(result);
    } catch {
      if (mounted.current) setError('Could not load Gmail connection status.');
    }
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    lifecycle.current = controller;
    mounted.current = true;
    void apiRequest<ConnectionStatus>(
      '/connections/gmail/status',
      'GET',
      controller.signal,
    )
      .then((result) => {
        if (!controller.signal.aborted) setConnection(result);
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError('Could not load Gmail connection status.');
      });
    return () => {
      mounted.current = false;
      controller.abort();
    };
  }, []);

  async function action(kind: 'connect' | 'sync' | 'refresh' | 'disconnect') {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      if (kind === 'connect') {
        const result = await apiRequest<{ authorizationUrl: string }>(
          '/connections/gmail/connect',
          'POST',
          lifecycle.current?.signal,
        );
        if (!mounted.current) return;
        const url = new URL(result.authorizationUrl);
        if (url.origin !== 'https://accounts.google.com')
          throw new Error('Invalid provider');
        window.location.assign(url.toString());
      } else if (kind === 'sync') {
        const result = await apiRequest<{
          events: number;
          needsReview: number;
          proposals: number;
          extractionStatus: string;
          extractionErrorCodes: string[];
        }>('/connections/gmail/sync', 'POST', lifecycle.current?.signal);
        if (!mounted.current) return;
        setNotice(
          `Fetched ${result.events} minimized events; ${result.needsReview} need review. ` +
            (result.extractionStatus === 'disabled'
              ? 'AI extraction is disabled; no proposals were generated.'
              : `${result.proposals} review proposals.` +
                (result.extractionErrorCodes.length
                  ? ` Extraction errors: ${result.extractionErrorCodes.join(', ')}.`
                  : '')),
        );
      } else if (kind === 'disconnect') {
        const result = await apiRequest<{ providerRevoked: boolean }>(
          '/connections/gmail/disconnect',
          'POST',
          lifecycle.current?.signal,
        );
        if (!mounted.current) return;
        setNotice(
          result.providerRevoked
            ? 'Disconnected and revoked at Google.'
            : 'Disconnected locally. Google revocation was not confirmed; remove access in your Google account.',
        );
      } else {
        await apiRequest(
          '/connections/gmail/refresh',
          'POST',
          lifecycle.current?.signal,
        );
        if (!mounted.current) return;
        setNotice('Read-only authorization refreshed.');
      }
      await reload();
      if (mounted.current && kind === 'sync' && onChanged) await onChanged();
    } catch (failure) {
      if (mounted.current)
        setError(
          failure instanceof Error
            ? failure.message
            : 'Connection action failed.',
        );
    } finally {
      if (mounted.current) setBusy(false);
    }
  }

  return (
    <section
      aria-labelledby="connections-heading"
      className="rounded-2xl border p-5"
    >
      <h2 id="connections-heading" className="text-lg font-semibold">
        Gmail connection
      </h2>
      <p>
        Separate account consent, read-only access, one bounded
        financial-message page per sync. No email sending or automatic ledger
        approval.
      </p>
      {connection ? (
        <>
          <p role="status">Status: {connection.status}</p>
          {!connection.configured && (
            <p>Gmail OAuth is not configured on this server.</p>
          )}
          {connection.lastSyncedAt && (
            <p>Last sync: {connection.lastSyncedAt}</p>
          )}
          {connection.lastErrorCode && (
            <p>Last error: {connection.lastErrorCode}</p>
          )}
          <div className="flex flex-wrap gap-3">
            <button
              disabled={busy || !connection.configured}
              onClick={() => void action('connect')}
            >
              {connection.status === 'disconnected'
                ? 'Connect Gmail'
                : 'Reconnect Gmail'}
            </button>
            <button
              disabled={
                busy || !['connected', 'error'].includes(connection.status)
              }
              onClick={() => void action('sync')}
            >
              Sync one page
            </button>
            <button
              disabled={
                busy || !['connected', 'error'].includes(connection.status)
              }
              onClick={() => void action('refresh')}
            >
              Refresh authorization
            </button>
            <button
              disabled={busy || connection.status === 'disconnected'}
              onClick={() => void action('disconnect')}
            >
              Disconnect Gmail
            </button>
          </div>
        </>
      ) : (
        <p role="status">Loading connection…</p>
      )}
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
    </section>
  );
}
