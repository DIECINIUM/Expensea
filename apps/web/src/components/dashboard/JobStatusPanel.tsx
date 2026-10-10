import { useEffect, useRef, useState, type FormEvent } from 'react';

import { Card } from './Card';
import {
  createJobsClient,
  JobsApiError,
  type DurableJob,
  type EnqueueNote,
  type JobsClient,
} from '../../lib/jobs-client';

const defaultClient = createJobsClient();
const statusLabels = {
  queued: 'Queued',
  running: 'Extracting',
  retry_wait: 'Waiting to retry',
  succeeded: 'Ready for proposal review',
  dead_letter: 'Needs job review',
  cancelled: 'Cancelled',
};

interface JobStatusPanelProps {
  client?: JobsClient;
  onChanged?: () => void | Promise<void>;
  pollIntervalMs?: number;
}

export function JobStatusPanel({
  client = defaultClient,
  onChanged,
  pollIntervalMs = 3000,
}: JobStatusPanelProps) {
  const [jobs, setJobs] = useState<DurableJob[]>([]);
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pendingCommand = useRef<EnqueueNote | null>(null);
  const reviewed = useRef(new Set<string>());
  const callback = useRef(onChanged);
  useEffect(() => {
    callback.current = onChanged;
  }, [onChanged]);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let failures = 0;
    async function poll() {
      try {
        const next = await client.list(controller.signal);
        if (controller.signal.aborted) return;
        setJobs(next);
        failures = 0;
        const completed = next.filter((job) => job.status === 'succeeded');
        if (completed.some((job) => !reviewed.current.has(job.id))) {
          await callback.current?.();
        }
        reviewed.current = new Set(completed.map((job) => job.id));
      } catch (cause) {
        if (controller.signal.aborted) return;
        failures = Math.min(failures + 1, 4);
        setError(
          cause instanceof JobsApiError
            ? cause.message
            : 'Job status is temporarily unavailable.',
        );
      } finally {
        if (!controller.signal.aborted) {
          timer = setTimeout(
            () => void poll(),
            Math.min(Math.max(pollIntervalMs, 1000) * 2 ** failures, 30000),
          );
        }
      }
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [client, pollIntervalMs]);

  function upsert(job: DurableJob) {
    setJobs((previous) =>
      [job, ...previous.filter((item) => item.id !== job.id)].slice(0, 20),
    );
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!note.trim() || busy) return;
    setBusy(true);
    setError(null);
    // Preserve this identity after a lost HTTP response; edit the note to start a new request.
    pendingCommand.current ??= {
      kind: 'financial_note_extract',
      idempotency_key: crypto.randomUUID(),
      payload: {
        note,
        source_timestamp: new Date().toISOString(),
        labels: [],
      },
    };
    try {
      upsert(await client.enqueue(pendingCommand.current));
      pendingCommand.current = null;
      setNote('');
    } catch (cause) {
      setError(
        cause instanceof JobsApiError
          ? cause.message
          : 'Enqueue failed. Retry the unchanged note safely.',
      );
    } finally {
      setBusy(false);
    }
  }

  async function action(job: DurableJob, kind: 'retry' | 'cancel') {
    setBusy(true);
    setError(null);
    try {
      upsert(await client[kind](job.id));
    } catch (cause) {
      setError(
        cause instanceof JobsApiError
          ? cause.message
          : 'The job action could not be completed.',
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="p-5">
      <h2 className="text-lg font-semibold text-slate-900">
        Background extraction
      </h2>
      <p className="mt-1 text-sm text-slate-600">
        Notes are saved before processing. Completed extraction still requires
        proposal approval.
      </p>
      <form onSubmit={(event) => void submit(event)} className="mt-4 space-y-3">
        <label className="block text-sm font-medium text-slate-700">
          Financial note for background extraction
          <textarea
            value={note}
            maxLength={8000}
            disabled={busy}
            onChange={(event) => {
              setNote(event.target.value);
              pendingCommand.current = null;
            }}
            className="mt-1 block w-full rounded-lg border border-slate-300 p-2"
          />
        </label>
        <button
          type="submit"
          disabled={busy || !note.trim()}
          className="rounded-lg bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
        >
          {busy ? 'Saving…' : 'Queue extraction'}
        </button>
      </form>
      {error && (
        <p role="alert" className="mt-3 text-sm text-rose-700">
          {error}
        </p>
      )}
      <ul aria-label="Background jobs" className="mt-4 space-y-3">
        {jobs.map((job) => (
          <li
            key={job.id}
            className="rounded-lg border border-slate-200 p-3 text-sm"
          >
            <p className="font-medium">{statusLabels[job.status]}</p>
            <p className="text-slate-600">
              Attempt {job.attempts} of {job.max_attempts}
            </p>
            {job.result && (
              <p>
                Proposal ID: <code>{job.result.proposal_id}</code>
              </p>
            )}
            {job.error_code && <p>Reason: {job.error_code}</p>}
            {job.status === 'dead_letter' && job.review_retries < 3 && (
              <button
                disabled={busy}
                onClick={() => void action(job, 'retry')}
                className="mt-2 underline"
                aria-label={`Retry job ${job.id}`}
              >
                Retry after review
              </button>
            )}
            {(job.status === 'queued' || job.status === 'retry_wait') && (
              <button
                disabled={busy}
                onClick={() => void action(job, 'cancel')}
                className="mt-2 underline"
                aria-label={`Cancel job ${job.id}`}
              >
                Cancel
              </button>
            )}
          </li>
        ))}
      </ul>
      {jobs.length === 0 && (
        <p className="mt-3 text-sm text-slate-500">No recent jobs.</p>
      )}
    </Card>
  );
}
