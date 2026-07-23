import { CircleAlert, LoaderCircle, Server, Wifi } from 'lucide-react';

import type { FoundationStatus } from '../../graphql/foundation-status';

interface ApiFoundationStatusProps {
  readonly status: FoundationStatus;
}

export function ApiFoundationStatus({ status }: ApiFoundationStatusProps) {
  if (status.kind === 'loading') {
    return (
      <div
        className="m-3 rounded-2xl border border-white/15 bg-white/[0.06] p-4"
        role="status"
        aria-live="polite"
      >
        <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-white">
          <LoaderCircle
            className="text-leaf-200 size-4 animate-spin"
            aria-hidden="true"
          />
          Checking API
        </div>
        <p className="text-[11px] leading-4 text-white/70">
          Verifying the GraphQL foundation…
        </p>
      </div>
    );
  }

  if (status.kind === 'offline') {
    return (
      <div
        className="m-3 rounded-2xl border border-amber-200/30 bg-amber-300/[0.08] p-4"
        role="alert"
      >
        <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-white">
          <CircleAlert className="size-4 text-amber-200" aria-hidden="true" />
          API unavailable
        </div>
        <p className="text-[11px] leading-4 text-white/70">
          Demo data remains visible while the backend is offline.
        </p>
        <button
          type="button"
          onClick={status.retry}
          className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-white/10 px-2.5 py-1.5 text-[11px] font-semibold text-white hover:bg-white/15"
        >
          <Wifi className="size-3.5" aria-hidden="true" />
          Retry connection
        </button>
      </div>
    );
  }

  return (
    <div
      className="m-3 rounded-2xl border border-white/15 bg-white/[0.06] p-4"
      role="status"
      aria-live="polite"
    >
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-white">
        <span className="relative flex size-2" aria-hidden="true">
          <span className="bg-leaf-200 absolute inline-flex size-full animate-ping rounded-full opacity-50" />
          <span className="bg-leaf-200 relative inline-flex size-2 rounded-full" />
        </span>
        API foundation online
      </div>
      <div className="flex items-start gap-2 text-[11px] leading-4 text-white/70">
        <Server className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
        <span>
          <span className="block text-white/85">{status.name}</span>
          <span className="block">
            v{status.version} · {status.environment}
          </span>
        </span>
      </div>
    </div>
  );
}
