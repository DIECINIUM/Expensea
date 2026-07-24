import { GitMerge, RotateCcw, Scale, ShieldCheck } from 'lucide-react';
import { useState } from 'react';
import { useMutation } from '@apollo/client/react';

import { Card } from './Card';
import {
  KEEP_RECONCILIATION_CASE_SEPARATE_MUTATION,
  MERGE_RECONCILIATION_CASE_MUTATION,
  UNMERGE_RECONCILIATION_CASE_MUTATION,
  type KeepReconciliationCaseSeparateMutationData,
  type MergeReconciliationCaseMutationData,
  type ReconciliationCaseData,
  type ReviewReconciliationCaseResult,
  type ReviewReconciliationCaseMutationVariables,
  type UnmergeReconciliationCaseMutationData,
} from '../../graphql/reconciliation';
import { formatMoney } from '../../lib/ledger-formatters';
import { mutationProblem, readableEnum } from '../../lib/management-values';

type ReviewAction = 'merge' | 'keep-separate' | 'unmerge';

interface Feedback {
  readonly confirmation: string | null;
  readonly error: string | null;
}

interface ReconciliationPanelProps {
  readonly cases: readonly ReconciliationCaseData[];
  readonly onChanged: () => Promise<void>;
}

const sourceLabels: Record<ReconciliationCaseData['source'], string> = {
  MANUAL_NOTE: 'Financial note',
  CSV_IMPORT: 'CSV import',
  MOCK_RECEIPT: 'Receipt',
  GMAIL: 'Gmail',
  GOOGLE_KEEP_TAKEOUT: 'Google Keep',
};

function scoreLabel(score: string): string {
  const value = Number(score);
  return Number.isFinite(value)
    ? `${Math.round(value * 100)}% match`
    : 'Match score unavailable';
}

function occurrenceLabel(value: string | null): string {
  if (value === null) {
    return 'Time unavailable';
  }
  const instant = new Date(value);
  if (Number.isNaN(instant.getTime())) {
    return 'Time unavailable';
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(instant);
}

function actionLabel(action: ReviewAction): string {
  if (action === 'merge') {
    return 'Merge';
  }
  if (action === 'keep-separate') {
    return 'Keep separate';
  }
  return 'Undo merge';
}

export function ReconciliationPanel({
  cases,
  onChanged,
}: ReconciliationPanelProps) {
  const actionableCases = cases.filter(
    (item) => item.status === 'PENDING' || item.canUnmerge,
  );
  const pendingCount = actionableCases.filter(
    (item) => item.status === 'PENDING',
  ).length;
  const [feedback, setFeedback] = useState<Feedback>({
    confirmation: null,
    error: null,
  });
  const [reviewing, setReviewing] = useState<{
    readonly id: string;
    readonly action: ReviewAction;
  } | null>(null);
  const [mergeCase] = useMutation<
    MergeReconciliationCaseMutationData,
    ReviewReconciliationCaseMutationVariables
  >(MERGE_RECONCILIATION_CASE_MUTATION);
  const [keepSeparate] = useMutation<
    KeepReconciliationCaseSeparateMutationData,
    ReviewReconciliationCaseMutationVariables
  >(KEEP_RECONCILIATION_CASE_SEPARATE_MUTATION);
  const [unmergeCase] = useMutation<
    UnmergeReconciliationCaseMutationData,
    ReviewReconciliationCaseMutationVariables
  >(UNMERGE_RECONCILIATION_CASE_MUTATION);

  const reviewCase = async (caseId: string, action: ReviewAction) => {
    setFeedback({ confirmation: null, error: null });
    setReviewing({ id: caseId, action });
    try {
      let result: ReviewReconciliationCaseResult | undefined;
      if (action === 'merge') {
        const response = await mergeCase({ variables: { id: caseId } });
        result = response.data?.mergeReconciliationCase;
      } else if (action === 'keep-separate') {
        const response = await keepSeparate({ variables: { id: caseId } });
        result = response.data?.keepReconciliationCaseSeparate;
      } else {
        const response = await unmergeCase({ variables: { id: caseId } });
        result = response.data?.unmergeReconciliationCase;
      }
      const problem = mutationProblem(result);
      if (problem) {
        setFeedback({ confirmation: null, error: problem });
        return;
      }
      if (result?.__typename !== 'ReviewReconciliationCaseSuccess') {
        setFeedback({
          confirmation: null,
          error: 'The API did not confirm the reconciliation decision.',
        });
        return;
      }

      try {
        await onChanged();
        setFeedback({
          confirmation:
            action === 'merge'
              ? 'Sources merged into one ledger transaction.'
              : action === 'keep-separate'
                ? 'A separate ledger transaction was created.'
                : 'The source was restored as a separate transaction.',
          error: null,
        });
      } catch {
        setFeedback({
          confirmation: null,
          error:
            'The decision was saved, but the dashboard could not refresh. Retry the dashboard query.',
        });
      }
    } catch {
      setFeedback({
        confirmation: null,
        error:
          'The reconciliation decision could not be saved. Check the API connection and try again.',
      });
    } finally {
      setReviewing(null);
    }
  };

  return (
    <Card id="duplicate-review" className="mt-4 overflow-hidden">
      <div className="border-b border-slate-100 bg-gradient-to-r from-amber-50 to-white p-5 sm:p-6">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
          <div className="flex gap-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-amber-100 text-amber-700">
              <Scale className="size-5" aria-hidden="true" />
            </span>
            <div>
              <p className="text-[10px] font-semibold tracking-[0.12em] text-amber-700 uppercase">
                Explainable reconciliation
              </p>
              <h2 className="mt-1 text-base font-semibold text-slate-900">
                Duplicate review
              </h2>
              <p className="mt-1 max-w-2xl text-xs leading-5 text-slate-600">
                Compare matching sources before they change the ledger. Every
                decision is recorded, and merged sources can be restored without
                deleting evidence.
              </p>
            </div>
          </div>
          <span className="w-fit rounded-full border border-amber-200 bg-white px-3 py-1 text-[10px] font-semibold text-amber-800">
            {pendingCount} awaiting decision
          </span>
        </div>
      </div>

      <div className="p-5 sm:p-6">
        {feedback.confirmation && (
          <p
            className="bg-leaf-50 text-leaf-700 mb-4 rounded-lg px-3 py-2 text-[10px] leading-4"
            role="status"
          >
            {feedback.confirmation}
          </p>
        )}
        {feedback.error && (
          <p
            className="mb-4 rounded-lg bg-amber-50 px-3 py-2 text-[10px] leading-4 text-amber-900"
            role="alert"
          >
            {feedback.error}
          </p>
        )}

        {actionableCases.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-6 text-center">
            <ShieldCheck
              className="text-leaf-600 mx-auto size-5"
              aria-hidden="true"
            />
            <p className="mt-2 text-xs font-semibold text-slate-700">
              No duplicate decisions need attention
            </p>
            <p className="mt-1 text-[10px] leading-4 text-slate-500">
              New sources are scored deterministically as they enter the ledger.
            </p>
          </div>
        ) : (
          <ul
            className="grid list-none grid-cols-1 gap-4 p-0 xl:grid-cols-2"
            aria-label="Reconciliation cases"
          >
            {actionableCases.map((item) => {
              const isPending = item.status === 'PENDING';
              return (
                <li
                  key={item.id}
                  className="rounded-2xl border border-slate-200 p-4"
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <p className="text-[10px] font-semibold tracking-[0.1em] text-slate-500 uppercase">
                        {sourceLabels[item.source]} ·{' '}
                        {readableEnum(item.eventKind)}
                      </p>
                      <h3 className="mt-1 text-sm font-semibold text-slate-900">
                        {item.description}
                      </h3>
                      <p className="mt-1 text-xs font-semibold text-slate-700">
                        {formatMoney(item.amount, item.currency)}
                      </p>
                      <p className="mt-0.5 text-[10px] text-slate-500">
                        Source time · {occurrenceLabel(item.occurredAt)}
                      </p>
                    </div>
                    <span
                      className={`rounded-full px-2.5 py-1 text-[9px] font-semibold ${
                        isPending
                          ? 'bg-amber-100 text-amber-800'
                          : 'bg-blue-50 text-blue-700'
                      }`}
                    >
                      {isPending ? scoreLabel(item.score) : 'Merged'}
                    </span>
                  </div>

                  <div className="mt-3 rounded-xl bg-slate-50 p-3">
                    <p className="text-[9px] font-semibold tracking-[0.1em] text-slate-500 uppercase">
                      Candidate ledger transaction
                    </p>
                    <p className="mt-1 text-[11px] font-semibold text-slate-800">
                      {item.candidateDescription ??
                        'Candidate description unavailable'}
                    </p>
                    {item.candidateMerchantName && (
                      <p className="mt-0.5 text-[10px] text-slate-500">
                        {item.candidateMerchantName}
                      </p>
                    )}
                    <p className="mt-0.5 text-[10px] text-slate-500">
                      Candidate time ·{' '}
                      {occurrenceLabel(item.candidateOccurredAt)}
                    </p>
                  </div>

                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {item.reasons.slice(0, 4).map((reason) => (
                      <span
                        key={reason}
                        className="rounded-full border border-slate-200 px-2 py-1 text-[9px] font-medium text-slate-600"
                      >
                        {readableEnum(reason)}
                      </span>
                    ))}
                  </div>

                  <div className="mt-4 flex flex-wrap gap-2">
                    {isPending ? (
                      <>
                        <button
                          type="button"
                          disabled={reviewing !== null}
                          onClick={() => {
                            void reviewCase(item.id, 'merge');
                          }}
                          className="bg-ink-900 hover:bg-ink-800 inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-[10px] font-semibold text-white disabled:cursor-wait disabled:opacity-60"
                          aria-label={`Merge ${item.description}`}
                        >
                          <GitMerge className="size-3.5" aria-hidden="true" />
                          {reviewing?.id === item.id &&
                          reviewing.action === 'merge'
                            ? 'Merging…'
                            : actionLabel('merge')}
                        </button>
                        <button
                          type="button"
                          disabled={reviewing !== null}
                          onClick={() => {
                            void reviewCase(item.id, 'keep-separate');
                          }}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 px-3 py-2 text-[10px] font-semibold text-slate-700 hover:bg-slate-50 disabled:cursor-wait disabled:opacity-60"
                          aria-label={`Keep ${item.description} separate`}
                        >
                          <Scale className="size-3.5" aria-hidden="true" />
                          {reviewing?.id === item.id &&
                          reviewing.action === 'keep-separate'
                            ? 'Saving…'
                            : actionLabel('keep-separate')}
                        </button>
                      </>
                    ) : (
                      <button
                        type="button"
                        disabled={reviewing !== null}
                        onClick={() => {
                          void reviewCase(item.id, 'unmerge');
                        }}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-[10px] font-semibold text-blue-700 hover:bg-blue-100 disabled:cursor-wait disabled:opacity-60"
                        aria-label={`Undo merge for ${item.description}`}
                      >
                        <RotateCcw className="size-3.5" aria-hidden="true" />
                        {reviewing?.id === item.id &&
                        reviewing.action === 'unmerge'
                          ? 'Restoring…'
                          : actionLabel('unmerge')}
                      </button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </Card>
  );
}
