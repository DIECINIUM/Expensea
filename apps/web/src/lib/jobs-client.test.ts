import { afterEach, describe, expect, it, vi } from 'vitest';

import { createJobsClient, JobsApiError } from './jobs-client';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe('jobs REST client', () => {
  it('includes authentication, cookies and abort signal without GraphQL coupling', async () => {
    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([]),
    });
    vi.stubGlobal('fetch', fetch);
    const controller = new AbortController();
    await createJobsClient('https://api.example.test/').list(controller.signal);
    expect(fetch).toHaveBeenCalledWith(
      'https://api.example.test/api/jobs?limit=20',
      expect.objectContaining({
        credentials: 'include',
        signal: controller.signal,
        headers: {},
      }),
    );
  });

  it('never exposes raw server errors or notes', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 429,
        json: () => Promise.resolve({ detail: 'private note text' }),
      }),
    );
    await expect(createJobsClient().list()).rejects.toThrow(
      'The queue is full.',
    );
    await expect(createJobsClient().list()).rejects.toBeInstanceOf(
      JobsApiError,
    );
  });

  it('obtains a session-bound CSRF token before cookie-authenticated mutations', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ csrfToken: 'csrf-token' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ id: 'job-one' }),
      });
    vi.stubGlobal('fetch', fetch);
    await createJobsClient().retry('job-one');
    expect(fetch).toHaveBeenNthCalledWith(
      1,
      '/auth/me',
      expect.objectContaining({
        credentials: 'include',
      }),
    );
    expect(fetch).toHaveBeenNthCalledWith(
      2,
      '/api/jobs/job-one/retry',
      expect.objectContaining({
        headers: { 'X-CSRF-Token': 'csrf-token' },
        method: 'POST',
      }),
    );
  });

  it('uses the configured absolute GraphQL origin for jobs and auth sessions', async () => {
    vi.stubEnv('VITE_GRAPHQL_URL', 'https://api.example.test/graphql');
    vi.stubEnv('VITE_API_URL', 'https://wrong-origin.example.test');
    const fetch = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve([]) })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ csrfToken: 'origin-csrf' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ id: 'job-one' }),
      });
    vi.stubGlobal('fetch', fetch);
    const client = createJobsClient();
    await client.list();
    await client.retry('job-one');
    expect(fetch).toHaveBeenNthCalledWith(
      1,
      'https://api.example.test/api/jobs?limit=20',
      expect.objectContaining({ credentials: 'include' }),
    );
    expect(fetch).toHaveBeenNthCalledWith(
      2,
      'https://api.example.test/auth/me',
      expect.objectContaining({ credentials: 'include' }),
    );
    expect(fetch).toHaveBeenNthCalledWith(
      3,
      'https://api.example.test/api/jobs/job-one/retry',
      expect.objectContaining({
        credentials: 'include',
        headers: { 'X-CSRF-Token': 'origin-csrf' },
      }),
    );
  });
});
