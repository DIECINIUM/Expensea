import { afterEach, describe, expect, it, vi } from 'vitest';

import { setCsrfToken } from '../auth/api';
import {
  askFinanceAgent,
  type FinanceAgentResult,
} from './finance-agent-client';

const result: FinanceAgentResult = {
  status: 'answered',
  mode: 'deterministic',
  tool: 'get_financial_summary',
  answer: 'Posted spending: INR 120.1234',
  facts: [
    {
      label: 'Posted spending',
      value: '120.1234',
      currency: 'INR',
      record_id: null,
      record_kind: null,
    },
  ],
  period_start: '2026-07-01',
  period_end: '2026-08-01',
  period_end_inclusive: false,
  previous_period_start: null,
  previous_period_end: null,
  truncated: false,
  limitations: ['Read-only. No currency conversion.'],
};

afterEach(() => {
  vi.unstubAllGlobals();
  setCsrfToken('');
  vi.unstubAllEnvs();
});

describe('finance agent REST client', () => {
  it('uses same-origin JSON and cookie credentials with exact string amounts', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(result)));
    vi.stubGlobal('fetch', fetchMock);
    setCsrfToken('session-csrf');
    const signal = new AbortController().signal;
    const actual = await askFinanceAgent(
      { question: 'summary', currency: 'INR' },
      signal,
    );
    expect(actual.facts[0]?.value).toBe('120.1234');
    expect(fetchMock).toHaveBeenCalledWith('/api/agent/questions', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': 'session-csrf',
      },
      body: '{"question":"summary","currency":"INR"}',
      signal,
    });
  });

  it('uses the configured API origin for authenticated requests', async () => {
    vi.stubEnv('VITE_GRAPHQL_URL', 'https://api.example.test/graphql');
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(result)));
    vi.stubGlobal('fetch', fetchMock);
    await askFinanceAgent({ question: 'summary' });
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      'https://api.example.test/api/agent/questions',
    );
  });

  it.each([401, 403])('requires sign-in on HTTP %s', async (status) => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('private', { status })),
    );
    await expect(askFinanceAgent({ question: 'summary' })).rejects.toThrow(
      'Please sign in again',
    );
  });

  it('does not echo malformed server data', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('private malformed text')),
    );
    await expect(askFinanceAgent({ question: 'summary' })).rejects.toThrow(
      'The finance answer was invalid',
    );
  });

  it('rejects unknown tools and oversized answers', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ...result, tool: 'execute_sql' })),
      )
      .mockResolvedValueOnce(new Response('x'.repeat(16001)));
    vi.stubGlobal('fetch', fetchMock);
    await expect(askFinanceAgent({ question: 'summary' })).rejects.toThrow(
      'invalid',
    );
    await expect(askFinanceAgent({ question: 'summary' })).rejects.toThrow(
      'safe limit',
    );
  });
});
