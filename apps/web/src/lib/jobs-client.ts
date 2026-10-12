import { apiUrl } from '../auth/api';

export type JobStatus =
  | 'queued'
  | 'running'
  | 'retry_wait'
  | 'succeeded'
  | 'dead_letter'
  | 'cancelled';

export interface DurableJob {
  id: string;
  kind: string;
  status: JobStatus;
  attempts: number;
  max_attempts: number;
  review_retries: number;
  created_at: string;
  updated_at: string;
  available_at: string;
  completed_at: string | null;
  error_code: string | null;
  result: { proposal_id: string } | null;
}

export interface EnqueueNote {
  kind: 'financial_note_extract';
  idempotency_key: string;
  payload: { note: string; source_timestamp: string; labels: string[] };
}

export interface JobsClient {
  list: (signal?: AbortSignal) => Promise<DurableJob[]>;
  enqueue: (command: EnqueueNote, signal?: AbortSignal) => Promise<DurableJob>;
  retry: (id: string) => Promise<DurableJob>;
  cancel: (id: string) => Promise<DurableJob>;
}

export class JobsApiError extends Error {
  constructor(public readonly status: number) {
    super(
      status === 429
        ? 'The queue is full. Try again shortly.'
        : status === 401 || status === 403
          ? 'Sign in to view your jobs.'
          : status === 409
            ? 'This job cannot perform that action. Refresh its status.'
            : 'The job request could not be completed.',
    );
  }
}

export function createJobsClient(
  baseUrl?: string,
  getCsrfToken?: () => string | null | Promise<string | null>,
): JobsClient {
  const base = baseUrl?.replace(/\/$/, '');
  const endpoint = (path: string) =>
    base === undefined ? apiUrl(path) : `${base}${path}`;
  const root = endpoint('/api/jobs');
  async function request<T>(
    suffix: string,
    method: 'GET' | 'POST',
    body?: EnqueueNote,
    signal?: AbortSignal,
  ): Promise<T> {
    let csrf: string | null = null;
    if (method === 'POST') {
      if (getCsrfToken) {
        csrf = await getCsrfToken();
      } else {
        const session = await fetch(endpoint('/auth/me'), {
          credentials: 'include',
          ...(signal ? { signal } : {}),
        });
        if (!session.ok) throw new JobsApiError(session.status);
        const identity = (await session.json()) as { csrfToken?: string };
        csrf = identity.csrfToken ?? null;
      }
    }
    const response = await fetch(`${root}${suffix}`, {
      method,
      credentials: 'include',
      headers: {
        ...(body ? { 'Content-Type': 'application/json' } : {}),
        ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
      ...(signal ? { signal } : {}),
    });
    if (!response.ok) throw new JobsApiError(response.status);
    return (await response.json()) as T;
  }
  return {
    list: (signal) =>
      request<DurableJob[]>('?limit=20', 'GET', undefined, signal),
    enqueue: (command, signal) =>
      request<DurableJob>('', 'POST', command, signal),
    retry: (id) =>
      request<DurableJob>(`/${encodeURIComponent(id)}/retry`, 'POST'),
    cancel: (id) =>
      request<DurableJob>(`/${encodeURIComponent(id)}/cancel`, 'POST'),
  };
}
