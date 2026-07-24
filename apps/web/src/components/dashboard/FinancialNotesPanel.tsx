import {
  BrainCircuit,
  Check,
  FileJson,
  Inbox,
  Mail,
  Sparkles,
  X,
} from 'lucide-react';
import { type ChangeEvent, type FormEvent, useState } from 'react';
import { useMutation } from '@apollo/client/react';

import { Card } from './Card';
import {
  APPROVE_FINANCIAL_PROPOSAL_MUTATION,
  IMPORT_GOOGLE_KEEP_NOTE_MUTATION,
  REJECT_FINANCIAL_PROPOSAL_MUTATION,
  SUBMIT_FINANCIAL_NOTE_MUTATION,
  type ApproveFinancialProposalMutationData,
  type FinancialEventProposalData,
  type ImportGoogleKeepNoteMutationData,
  type ImportGoogleKeepNoteMutationVariables,
  type RejectFinancialProposalMutationData,
  type ReviewFinancialProposalMutationVariables,
  type SubmitFinancialNoteMutationData,
  type SubmitFinancialNoteMutationVariables,
} from '../../graphql/financial-proposals';
import { formatMoney } from '../../lib/ledger-formatters';
import { mutationProblem, readableEnum } from '../../lib/management-values';

const KEEP_DOCUMENT_LIMIT_BYTES = 65_536;

interface Feedback {
  readonly confirmation: string | null;
  readonly error: string | null;
}

interface FinancialNotesPanelProps {
  readonly proposals: readonly FinancialEventProposalData[];
  readonly onChanged: () => Promise<void>;
}

function sourceLabel(source: FinancialEventProposalData['source']): string {
  const labels: Record<FinancialEventProposalData['source'], string> = {
    MANUAL_NOTE: 'Quick note',
    CSV_IMPORT: 'CSV import',
    MOCK_RECEIPT: 'Receipt fixture',
    GMAIL: 'Gmail',
    GOOGLE_KEEP_TAKEOUT: 'Google Keep',
  };
  return labels[source];
}

function amountLabel(proposal: FinancialEventProposalData): string {
  if (proposal.amount === null || proposal.currency === null) {
    return 'Amount not identified';
  }
  return formatMoney(proposal.amount, proposal.currency);
}

function confidenceLabel(confidence: string): string {
  const percentage = Number(confidence) * 100;
  return Number.isFinite(percentage)
    ? `${Math.round(percentage)}% confidence`
    : 'Confidence unavailable';
}

function parseLabels(value: string): string[] {
  const seen = new Set<string>();
  return value
    .split(',')
    .map((label) => label.trim())
    .filter((label) => {
      const key = label.toLocaleLowerCase();
      if (!label || seen.has(key)) {
        return false;
      }
      seen.add(key);
      return true;
    })
    .slice(0, 11);
}

function reviewedMessage(action: 'approve' | 'reject'): string {
  return action === 'approve'
    ? 'Proposal approved and ledger data refreshed.'
    : 'Proposal rejected and removed from the review queue.';
}

export function FinancialNotesPanel({
  proposals,
  onChanged,
}: FinancialNotesPanelProps) {
  const [note, setNote] = useState('');
  const [labels, setLabels] = useState('');
  const [noteFeedback, setNoteFeedback] = useState<Feedback>({
    confirmation: null,
    error: null,
  });
  const [keepFeedback, setKeepFeedback] = useState<Feedback>({
    confirmation: null,
    error: null,
  });
  const [reviewFeedback, setReviewFeedback] = useState<Feedback>({
    confirmation: null,
    error: null,
  });
  const [isImporting, setIsImporting] = useState(false);
  const [reviewing, setReviewing] = useState<{
    readonly id: string;
    readonly action: 'approve' | 'reject';
  } | null>(null);
  const [submitNote, { loading: isSubmitting }] = useMutation<
    SubmitFinancialNoteMutationData,
    SubmitFinancialNoteMutationVariables
  >(SUBMIT_FINANCIAL_NOTE_MUTATION);
  const [importKeepNote] = useMutation<
    ImportGoogleKeepNoteMutationData,
    ImportGoogleKeepNoteMutationVariables
  >(IMPORT_GOOGLE_KEEP_NOTE_MUTATION);
  const [approveProposal] = useMutation<
    ApproveFinancialProposalMutationData,
    ReviewFinancialProposalMutationVariables
  >(APPROVE_FINANCIAL_PROPOSAL_MUTATION);
  const [rejectProposal] = useMutation<
    RejectFinancialProposalMutationData,
    ReviewFinancialProposalMutationVariables
  >(REJECT_FINANCIAL_PROPOSAL_MUTATION);

  const refreshAfterMutation = async (
    confirmation: string,
    setFeedback: (feedback: Feedback) => void,
  ) => {
    try {
      await onChanged();
      setFeedback({ confirmation, error: null });
    } catch {
      setFeedback({
        confirmation: null,
        error:
          'The change was saved, but the dashboard could not refresh. Retry the dashboard query.',
      });
    }
  };

  const submitFinancialNote = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalizedNote = note.trim();
    setNoteFeedback({ confirmation: null, error: null });
    if (normalizedNote.length < 2) {
      setNoteFeedback({
        confirmation: null,
        error: 'Enter at least two characters for the financial note.',
      });
      return;
    }

    try {
      const response = await submitNote({
        variables: {
          input: {
            note: normalizedNote,
            sourceTimestamp: new Date().toISOString(),
            clientRequestId: globalThis.crypto.randomUUID(),
            labels: parseLabels(labels),
          },
        },
      });
      const result = response.data?.submitFinancialNote;
      const problem = mutationProblem(result);
      if (problem) {
        setNoteFeedback({ confirmation: null, error: problem });
        return;
      }
      if (result?.__typename !== 'SubmitFinancialNoteSuccess') {
        setNoteFeedback({
          confirmation: null,
          error: 'The API did not confirm the extracted proposal.',
        });
        return;
      }

      setNote('');
      setLabels('');
      await refreshAfterMutation(
        'Note extracted into a proposal. Review it before posting.',
        setNoteFeedback,
      );
    } catch {
      setNoteFeedback({
        confirmation: null,
        error:
          'The note could not be extracted. Check the API and configured AI provider, then try again.',
      });
    }
  };

  const importGoogleKeepNote = async (event: ChangeEvent<HTMLInputElement>) => {
    const input = event.currentTarget;
    const file = input.files?.[0];
    if (!file) {
      return;
    }
    setKeepFeedback({ confirmation: null, error: null });
    if (file.size > KEEP_DOCUMENT_LIMIT_BYTES) {
      setKeepFeedback({
        confirmation: null,
        error: 'Choose a Google Keep JSON note no larger than 64 KiB.',
      });
      input.value = '';
      return;
    }

    setIsImporting(true);
    try {
      const response = await importKeepNote({
        variables: {
          input: {
            filename: file.name,
            content: await file.text(),
          },
        },
      });
      const result = response.data?.importGoogleKeepNote;
      const problem = mutationProblem(result);
      if (problem) {
        setKeepFeedback({ confirmation: null, error: problem });
        return;
      }
      if (result?.__typename !== 'ImportGoogleKeepNoteSuccess') {
        setKeepFeedback({
          confirmation: null,
          error: 'The API did not confirm the Google Keep import.',
        });
        return;
      }
      if (result.ignored) {
        setKeepFeedback({
          confirmation:
            'The selected note was empty or trashed, so no proposal was created.',
          error: null,
        });
        return;
      }
      await refreshAfterMutation(
        'Google Keep note imported into the review queue.',
        setKeepFeedback,
      );
    } catch {
      setKeepFeedback({
        confirmation: null,
        error:
          'The Google Keep note could not be imported. Check the file, API, and AI provider.',
      });
    } finally {
      setIsImporting(false);
      input.value = '';
    }
  };

  const reviewProposal = async (
    proposalId: string,
    action: 'approve' | 'reject',
  ) => {
    setReviewFeedback({ confirmation: null, error: null });
    setReviewing({ id: proposalId, action });
    try {
      if (action === 'approve') {
        const response = await approveProposal({
          variables: { id: proposalId },
        });
        const result = response.data?.approveFinancialProposal;
        const problem = mutationProblem(result);
        if (problem) {
          setReviewFeedback({ confirmation: null, error: problem });
          return;
        }
        if (result?.__typename !== 'ReviewFinancialProposalSuccess') {
          setReviewFeedback({
            confirmation: null,
            error: 'The API did not confirm proposal approval.',
          });
          return;
        }
      } else {
        const response = await rejectProposal({
          variables: { id: proposalId },
        });
        const result = response.data?.rejectFinancialProposal;
        const problem = mutationProblem(result);
        if (problem) {
          setReviewFeedback({ confirmation: null, error: problem });
          return;
        }
        if (result?.__typename !== 'ReviewFinancialProposalSuccess') {
          setReviewFeedback({
            confirmation: null,
            error: 'The API did not confirm proposal rejection.',
          });
          return;
        }
      }
      await refreshAfterMutation(reviewedMessage(action), setReviewFeedback);
    } catch {
      setReviewFeedback({
        confirmation: null,
        error:
          'The proposal could not be reviewed. Check the API connection and try again.',
      });
    } finally {
      setReviewing(null);
    }
  };

  return (
    <Card id="ai-inbox" className="overflow-hidden">
      <div className="border-b border-slate-100 bg-gradient-to-r from-violet-50 to-white p-5 sm:p-6">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
          <div className="flex gap-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-violet-100 text-violet-700">
              <BrainCircuit className="size-5" aria-hidden="true" />
            </span>
            <div>
              <p className="text-[10px] font-semibold tracking-[0.12em] text-violet-700 uppercase">
                Review-first AI
              </p>
              <h2 className="mt-1 text-base font-semibold text-slate-900">
                Financial notes inbox
              </h2>
              <p className="mt-1 max-w-2xl text-xs leading-5 text-slate-600">
                AI extracts structured facts and review reasons. Nothing reaches
                your ledger until you approve the proposal.
              </p>
            </div>
          </div>
          <span className="w-fit rounded-full border border-violet-200 bg-white px-3 py-1 text-[10px] font-semibold text-violet-700">
            {proposals.length} awaiting review
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 p-5 sm:p-6 xl:grid-cols-2">
        <form
          className="rounded-2xl border border-slate-200 p-4"
          onSubmit={(event) => {
            void submitFinancialNote(event);
          }}
        >
          <div className="flex items-center gap-2">
            <Sparkles className="size-4 text-violet-600" aria-hidden="true" />
            <h3 className="text-sm font-semibold text-slate-800">
              Extract a quick note
            </h3>
          </div>
          <label
            htmlFor="financial-note"
            className="mt-4 block text-[11px] font-semibold text-slate-700"
          >
            Informal expense or money note
          </label>
          <textarea
            id="financial-note"
            value={note}
            maxLength={8_000}
            rows={4}
            placeholder="Paid ₹450 for an airport cab today"
            onChange={(event) => {
              setNote(event.target.value);
              setNoteFeedback({ confirmation: null, error: null });
            }}
            className="mt-1 w-full resize-y rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-xs leading-5 placeholder:text-slate-400"
          />
          <label
            htmlFor="financial-note-labels"
            className="mt-3 block text-[11px] font-semibold text-slate-700"
          >
            Labels{' '}
            <span className="font-normal text-slate-500">(optional)</span>
          </label>
          <input
            id="financial-note-labels"
            value={labels}
            placeholder="Travel, work"
            onChange={(event) => {
              setLabels(event.target.value);
              setNoteFeedback({ confirmation: null, error: null });
            }}
            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-xs placeholder:text-slate-400"
          />
          <button
            type="submit"
            disabled={isSubmitting}
            className="bg-ink-900 hover:bg-ink-800 mt-3 inline-flex items-center gap-2 rounded-xl px-4 py-2.5 text-[11px] font-semibold text-white disabled:cursor-wait disabled:opacity-70"
          >
            <Sparkles className="size-3.5" aria-hidden="true" />
            {isSubmitting ? 'Extracting…' : 'Create review proposal'}
          </button>
          {noteFeedback.confirmation && (
            <p
              className="bg-leaf-50 text-leaf-700 mt-3 rounded-lg px-3 py-2 text-[10px] leading-4"
              role="status"
            >
              {noteFeedback.confirmation}
            </p>
          )}
          {noteFeedback.error && (
            <p
              className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-[10px] leading-4 text-amber-900"
              role="alert"
            >
              {noteFeedback.error}
            </p>
          )}
        </form>

        <div className="space-y-3">
          <div className="rounded-2xl border border-slate-200 p-4">
            <div className="flex items-start gap-3">
              <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-blue-50 text-blue-700">
                <FileJson className="size-4" aria-hidden="true" />
              </span>
              <div className="min-w-0 flex-1">
                <h3 className="text-sm font-semibold text-slate-800">
                  Google Keep Takeout
                </h3>
                <p className="mt-1 text-[11px] leading-4 text-slate-600">
                  Select one exported note JSON file. Attachments are ignored;
                  note text and labels enter the same review queue.
                </p>
                <label className="mt-3 inline-flex cursor-pointer items-center rounded-xl border border-slate-300 px-3 py-2 text-[11px] font-semibold text-slate-700 hover:bg-slate-50">
                  {isImporting ? 'Importing…' : 'Choose Keep JSON'}
                  <input
                    type="file"
                    accept=".json,application/json"
                    disabled={isImporting}
                    onChange={(event) => {
                      void importGoogleKeepNote(event);
                    }}
                    className="sr-only"
                    aria-label="Choose Google Keep JSON"
                  />
                </label>
              </div>
            </div>
            {keepFeedback.confirmation && (
              <p
                className="bg-leaf-50 text-leaf-700 mt-3 rounded-lg px-3 py-2 text-[10px] leading-4"
                role="status"
              >
                {keepFeedback.confirmation}
              </p>
            )}
            {keepFeedback.error && (
              <p
                className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-[10px] leading-4 text-amber-900"
                role="alert"
              >
                {keepFeedback.error}
              </p>
            )}
          </div>

          <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-4">
            <div className="flex items-start gap-3">
              <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-white text-red-600">
                <Mail className="size-4" aria-hidden="true" />
              </span>
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-sm font-semibold text-slate-800">
                    Gmail
                  </h3>
                  <span className="rounded-full bg-slate-200 px-2 py-0.5 text-[9px] font-semibold text-slate-700">
                    OAuth setup pending
                  </span>
                </div>
                <p className="mt-1 text-[11px] leading-4 text-slate-600">
                  The read-only receipt and subscription adapter is ready.
                  Account connection stays unavailable until secure Google OAuth
                  credentials and consent are configured.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="border-t border-slate-100 px-5 py-5 sm:px-6">
        <div className="flex items-center gap-2">
          <Inbox className="size-4 text-slate-500" aria-hidden="true" />
          <h3 className="text-sm font-semibold text-slate-800">
            Proposals awaiting your decision
          </h3>
        </div>

        {reviewFeedback.confirmation && (
          <p
            className="bg-leaf-50 text-leaf-700 mt-3 rounded-lg px-3 py-2 text-[10px] leading-4"
            role="status"
          >
            {reviewFeedback.confirmation}
          </p>
        )}
        {reviewFeedback.error && (
          <p
            className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-[10px] leading-4 text-amber-900"
            role="alert"
          >
            {reviewFeedback.error}
          </p>
        )}

        {proposals.length === 0 ? (
          <div className="mt-3 rounded-xl border border-dashed border-slate-200 px-4 py-6 text-center">
            <p className="text-xs font-semibold text-slate-700">
              No proposals need review
            </p>
            <p className="mt-1 text-[10px] leading-4 text-slate-500">
              Add a quick note or import a Keep note to create one.
            </p>
          </div>
        ) : (
          <ul
            className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-2"
            aria-label="Financial proposals"
          >
            {proposals.map((proposal) => {
              const isReviewing = reviewing?.id === proposal.id;
              return (
                <li
                  key={proposal.id}
                  className="rounded-2xl border border-slate-200 p-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="rounded-full bg-violet-50 px-2 py-1 text-[9px] font-semibold text-violet-700">
                          {readableEnum(proposal.eventKind)}
                        </span>
                        <span className="text-[9px] font-medium text-slate-500">
                          {sourceLabel(proposal.source)}
                        </span>
                      </div>
                      <p className="mt-2 text-sm font-semibold text-slate-900">
                        {amountLabel(proposal)}
                      </p>
                    </div>
                    <span className="text-[9px] font-semibold text-slate-500">
                      {confidenceLabel(proposal.confidence)}
                    </span>
                  </div>
                  <p className="mt-2 text-xs leading-5 text-slate-700">
                    {proposal.description}
                  </p>
                  {(proposal.merchantName ?? proposal.counterparty) && (
                    <p className="mt-1 text-[10px] text-slate-500">
                      {proposal.merchantName
                        ? `Merchant: ${proposal.merchantName}`
                        : `Counterparty: ${proposal.counterparty}`}
                    </p>
                  )}
                  {proposal.recurrenceRule && (
                    <p className="mt-1 text-[10px] text-slate-500">
                      {readableEnum(proposal.recurrenceRule)} recurring payment
                      {proposal.nextExpectedDate
                        ? ` · next ${proposal.nextExpectedDate}`
                        : ''}
                    </p>
                  )}
                  {proposal.categoryHint && (
                    <p className="mt-1 text-[10px] text-slate-500">
                      Category suggestion: {proposal.categoryHint}
                    </p>
                  )}
                  {proposal.tags.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {proposal.tags.map((tag) => (
                        <span
                          key={tag}
                          className="rounded-md bg-slate-100 px-2 py-1 text-[9px] font-medium text-slate-600"
                        >
                          #{tag}
                        </span>
                      ))}
                    </div>
                  )}
                  {proposal.reviewReasons.length > 0 && (
                    <div className="mt-3 rounded-lg bg-amber-50 px-3 py-2">
                      <p className="text-[9px] font-semibold tracking-wide text-amber-900 uppercase">
                        Why review
                      </p>
                      <p className="mt-1 text-[10px] leading-4 text-amber-800">
                        {proposal.reviewReasons
                          .map((reason) => readableEnum(reason))
                          .join(' · ')}
                      </p>
                    </div>
                  )}
                  <div className="mt-4 flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={isReviewing}
                      onClick={() => {
                        void reviewProposal(proposal.id, 'approve');
                      }}
                      className="bg-leaf-600 hover:bg-leaf-700 inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-[10px] font-semibold text-white disabled:cursor-wait disabled:opacity-60"
                      aria-label={`Approve ${proposal.description}`}
                    >
                      <Check className="size-3" aria-hidden="true" />
                      {isReviewing && reviewing.action === 'approve'
                        ? 'Approving…'
                        : 'Approve'}
                    </button>
                    <button
                      type="button"
                      disabled={isReviewing}
                      onClick={() => {
                        void reviewProposal(proposal.id, 'reject');
                      }}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 px-3 py-2 text-[10px] font-semibold text-slate-700 hover:bg-slate-50 disabled:cursor-wait disabled:opacity-60"
                      aria-label={`Reject ${proposal.description}`}
                    >
                      <X className="size-3" aria-hidden="true" />
                      {isReviewing && reviewing.action === 'reject'
                        ? 'Rejecting…'
                        : 'Reject'}
                    </button>
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
