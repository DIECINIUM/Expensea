import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { JobStatusPanel } from './JobStatusPanel';
import type { DurableJob, JobsClient } from '../../lib/jobs-client';

const queued: DurableJob = {
  id: 'job-one',
  kind: 'financial_note_extract',
  status: 'queued',
  attempts: 0,
  max_attempts: 3,
  review_retries: 0,
  created_at: '2026-10-11T00:00:00Z',
  updated_at: '2026-10-11T00:00:00Z',
  available_at: '2026-10-11T00:00:00Z',
  completed_at: null,
  error_code: null,
  result: null,
};

function client(): JobsClient {
  return {
    list: vi.fn().mockResolvedValue([]),
    enqueue: vi.fn().mockResolvedValue(queued),
    retry: vi.fn().mockResolvedValue(queued),
    cancel: vi.fn().mockResolvedValue({ ...queued, status: 'cancelled' }),
  };
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('JobStatusPanel', () => {
  it('enqueues notes without approving proposals', async () => {
    const api = client();
    const user = userEvent.setup();
    render(<JobStatusPanel client={api} />);
    await user.type(screen.getByRole('textbox'), 'Paid 249 for music');
    await user.click(screen.getByRole('button', { name: 'Queue extraction' }));
    expect(await screen.findByText('Queued')).toBeInTheDocument();
    const submitted = vi.mocked(api.enqueue).mock.calls[0]?.[0];
    expect(submitted?.kind).toBe('financial_note_extract');
    expect(submitted?.payload.note).toBe('Paid 249 for music');
    expect(
      screen.getByText(/still requires proposal approval/),
    ).toBeInTheDocument();
  });

  it('retains request identity on a lost response', async () => {
    const api = client();
    vi.mocked(api.enqueue).mockRejectedValueOnce(new Error('network'));
    const user = userEvent.setup();
    render(<JobStatusPanel client={api} />);
    await user.type(screen.getByRole('textbox'), 'A private note');
    await user.click(screen.getByRole('button', { name: 'Queue extraction' }));
    await screen.findByRole('alert');
    await user.click(screen.getByRole('button', { name: 'Queue extraction' }));
    await screen.findByText('Queued');
    expect(vi.mocked(api.enqueue).mock.calls[0]?.[0]).toEqual(
      vi.mocked(api.enqueue).mock.calls[1]?.[0],
    );
  });

  it('polls completion and refreshes proposal data once', async () => {
    vi.useFakeTimers();
    const api = client();
    const completed = {
      ...queued,
      status: 'succeeded' as const,
      result: { proposal_id: 'proposal-one' },
    };
    vi.mocked(api.list)
      .mockResolvedValueOnce([queued])
      .mockResolvedValue([completed]);
    const onChanged = vi.fn();
    const view = render(
      <JobStatusPanel
        client={api}
        onChanged={onChanged}
        pollIntervalMs={1000}
      />,
    );
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByText('Queued')).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(screen.getByText('Ready for proposal review')).toBeInTheDocument();
    expect(screen.getByText('proposal-one')).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalledOnce();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(onChanged).toHaveBeenCalledOnce();
    const signal = vi.mocked(api.list).mock.calls[0]?.[0];
    view.unmount();
    expect(signal?.aborted).toBe(true);
  });

  it('refreshes initial succeeded jobs once despite callback identity changes', async () => {
    vi.useFakeTimers();
    const api = client();
    vi.mocked(api.list).mockResolvedValue([
      {
        ...queued,
        status: 'succeeded',
        result: { proposal_id: 'existing-proposal' },
      },
    ]);
    const firstRefresh = vi.fn();
    const nextRefresh = vi.fn();
    const view = render(
      <JobStatusPanel
        client={api}
        onChanged={firstRefresh}
        pollIntervalMs={1000}
      />,
    );
    await act(async () => {
      await Promise.resolve();
    });
    expect(firstRefresh).toHaveBeenCalledOnce();
    view.rerender(
      <JobStatusPanel
        client={api}
        onChanged={nextRefresh}
        pollIntervalMs={1000}
      />,
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(firstRefresh).toHaveBeenCalledOnce();
    expect(nextRefresh).not.toHaveBeenCalled();
    expect(api.list).toHaveBeenCalledTimes(4);
  });

  it('provides dead-letter review retry but never offers running cancellation', async () => {
    const api = client();
    vi.mocked(api.list).mockResolvedValue([
      { ...queued, status: 'dead_letter', error_code: 'JOB_TIMEOUT' },
      { ...queued, id: 'running-one', status: 'running' },
    ]);
    const user = userEvent.setup();
    render(<JobStatusPanel client={api} />);
    await screen.findByText('Needs job review');
    expect(
      screen.queryByRole('button', { name: 'Cancel job running-one' }),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Retry job job-one' }));
    await waitFor(() => expect(api.retry).toHaveBeenCalledWith('job-one'));
  });
});
