import { ArrowDownLeft, ArrowUpRight, CircleDollarSign } from 'lucide-react';
import { type FormEvent, useState } from 'react';
import { useMutation } from '@apollo/client/react';

import { Card } from './Card';
import type { ObligationData, PersonData } from '../../graphql/dashboard';
import {
  CREATE_PAYABLE_MUTATION,
  CREATE_RECEIVABLE_MUTATION,
  SETTLE_PAYABLE_MUTATION,
  SETTLE_RECEIVABLE_MUTATION,
  type CreateObligationMutationVariables,
  type CreatePayableMutationData,
  type CreateReceivableMutationData,
  type MutationResult,
  type SettleObligationMutationVariables,
  type SettlePayableMutationData,
  type SettleReceivableMutationData,
} from '../../graphql/phase1-management';
import { formatMoney } from '../../lib/ledger-formatters';
import {
  isPositiveDecimalString,
  localDateTimeToIso,
  localDateTimeValue,
  localDateValue,
  mutationProblem,
  readableEnum,
} from '../../lib/management-values';

type ObligationKind = 'RECEIVABLE' | 'PAYABLE';

interface MutationFeedback {
  readonly confirmation: string | null;
  readonly error: string | null;
}

interface SettlementFormProps {
  readonly kind: ObligationKind;
  readonly obligation: ObligationData;
  readonly onChanged: () => Promise<void>;
}

function SettlementForm({ kind, obligation, onChanged }: SettlementFormProps) {
  const formId = `settlement-${kind.toLowerCase()}-${obligation.id}`;
  const [amount, setAmount] = useState(obligation.outstandingAmount);
  const [settledAt, setSettledAt] = useState(localDateTimeValue);
  const [note, setNote] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [feedback, setFeedback] = useState<MutationFeedback>({
    confirmation: null,
    error: null,
  });
  const [settleReceivable] = useMutation<
    SettleReceivableMutationData,
    SettleObligationMutationVariables
  >(SETTLE_RECEIVABLE_MUTATION);
  const [settlePayable] = useMutation<
    SettlePayableMutationData,
    SettleObligationMutationVariables
  >(SETTLE_PAYABLE_MUTATION);

  const clearFeedback = () => {
    setFeedback({ confirmation: null, error: null });
  };

  const submitSettlement = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    clearFeedback();

    if (!isPositiveDecimalString(amount)) {
      setFeedback({
        confirmation: null,
        error:
          'Use a positive decimal amount with up to four fractional digits.',
      });
      return;
    }

    setIsSaving(true);
    try {
      const variables = {
        input: {
          obligationId: obligation.id,
          amount,
          settledAt: localDateTimeToIso(settledAt),
          note: note.trim() || null,
        },
      };
      let result:
        | MutationResult<'SettleReceivableSuccess' | 'SettlePayableSuccess'>
        | undefined;
      if (kind === 'RECEIVABLE') {
        const response = await settleReceivable({ variables });
        result = response.data?.settleReceivable;
      } else {
        const response = await settlePayable({ variables });
        result = response.data?.settlePayable;
      }
      const problem = mutationProblem(result);

      if (problem) {
        setFeedback({ confirmation: null, error: problem });
        return;
      }

      const expectedSuccess =
        kind === 'RECEIVABLE'
          ? 'SettleReceivableSuccess'
          : 'SettlePayableSuccess';
      if (result?.__typename !== expectedSuccess) {
        setFeedback({
          confirmation: null,
          error: 'The API did not confirm the settlement.',
        });
        return;
      }

      try {
        await onChanged();
        setFeedback({
          confirmation: 'Settlement saved and balances refreshed.',
          error: null,
        });
      } catch {
        setFeedback({
          confirmation: null,
          error:
            'Settlement saved, but balances could not refresh. Retry the dashboard query before recording another payment.',
        });
      }
    } catch {
      setFeedback({
        confirmation: null,
        error:
          'The settlement could not be saved. Check the API connection and try again.',
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <details className="mt-3 rounded-xl border border-slate-200 bg-slate-50">
      <summary className="cursor-pointer px-3 py-2 text-[11px] font-semibold text-slate-700">
        Record settlement
      </summary>
      <form
        className="grid grid-cols-1 gap-2 border-t border-slate-200 p-3 sm:grid-cols-2"
        onSubmit={(event) => {
          void submitSettlement(event);
        }}
      >
        <div>
          <label
            htmlFor={`${formId}-amount`}
            className="text-[10px] font-semibold text-slate-700"
          >
            Settlement amount
          </label>
          <div className="mt-1 flex rounded-lg border border-slate-200 bg-white">
            <input
              id={`${formId}-amount`}
              value={amount}
              required
              inputMode="decimal"
              onChange={(event) => {
                setAmount(event.target.value);
                clearFeedback();
              }}
              className="min-w-0 flex-1 bg-transparent px-2.5 py-2 text-xs"
            />
            <span className="flex items-center border-l border-slate-200 px-2 text-[9px] font-semibold text-slate-500">
              {obligation.currency}
            </span>
          </div>
        </div>
        <div>
          <label
            htmlFor={`${formId}-date`}
            className="text-[10px] font-semibold text-slate-700"
          >
            Settled at
          </label>
          <input
            id={`${formId}-date`}
            type="datetime-local"
            value={settledAt}
            required
            onChange={(event) => {
              setSettledAt(event.target.value);
              clearFeedback();
            }}
            className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"
          />
        </div>
        <div className="sm:col-span-2">
          <label
            htmlFor={`${formId}-note`}
            className="text-[10px] font-semibold text-slate-700"
          >
            Note <span className="font-normal text-slate-500">(optional)</span>
          </label>
          <input
            id={`${formId}-note`}
            value={note}
            maxLength={500}
            placeholder="Bank transfer"
            onChange={(event) => {
              setNote(event.target.value);
              clearFeedback();
            }}
            className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"
          />
        </div>
        <button
          type="submit"
          disabled={isSaving}
          className="bg-ink-900 hover:bg-ink-800 rounded-lg px-3 py-2 text-[11px] font-semibold text-white disabled:cursor-wait disabled:opacity-70 sm:col-span-2"
        >
          {isSaving ? 'Recording…' : 'Confirm settlement'}
        </button>
        {feedback.confirmation && (
          <p
            className="bg-leaf-50 text-leaf-700 rounded-lg px-3 py-2 text-[10px] sm:col-span-2"
            role="status"
          >
            {feedback.confirmation}
          </p>
        )}
        {feedback.error && (
          <p
            className="rounded-lg bg-amber-50 px-3 py-2 text-[10px] leading-4 text-amber-800 sm:col-span-2"
            role="alert"
          >
            {feedback.error}
          </p>
        )}
      </form>
    </details>
  );
}

interface ObligationListProps {
  readonly kind: ObligationKind;
  readonly obligations: readonly ObligationData[];
  readonly onChanged: () => Promise<void>;
}

function ObligationList({ kind, obligations, onChanged }: ObligationListProps) {
  const label = kind === 'RECEIVABLE' ? 'Owed to you' : 'You owe';

  return (
    <section aria-labelledby={`${kind.toLowerCase()}-heading`}>
      <div className="flex items-center gap-2">
        <span
          className={
            kind === 'RECEIVABLE'
              ? 'grid size-7 place-items-center rounded-lg bg-blue-50 text-blue-700'
              : 'grid size-7 place-items-center rounded-lg bg-amber-50 text-amber-700'
          }
          aria-hidden="true"
        >
          {kind === 'RECEIVABLE' ? (
            <ArrowDownLeft className="size-3.5" />
          ) : (
            <ArrowUpRight className="size-3.5" />
          )}
        </span>
        <h3
          id={`${kind.toLowerCase()}-heading`}
          className="text-xs font-semibold text-slate-800"
        >
          {label}
        </h3>
      </div>

      {obligations.length === 0 ? (
        <p className="mt-3 rounded-xl border border-dashed border-slate-200 px-3 py-4 text-center text-[11px] text-slate-600">
          No {kind === 'RECEIVABLE' ? 'receivables' : 'payables'} recorded.
        </p>
      ) : (
        <ul className="mt-3 space-y-2">
          {obligations.map((obligation) => {
            const canSettle = !['PAID', 'CANCELLED'].includes(
              obligation.status,
            );

            return (
              <li
                key={obligation.id}
                className="rounded-xl border border-slate-200 p-3"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-xs font-semibold text-slate-800">
                      {obligation.personName}
                    </p>
                    <p className="mt-0.5 text-[10px] leading-4 text-slate-600">
                      {obligation.description}
                    </p>
                  </div>
                  <span className="rounded-full bg-slate-100 px-2 py-1 text-[9px] font-semibold text-slate-600">
                    {readableEnum(obligation.status)}
                  </span>
                </div>
                <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 text-[10px]">
                  <div>
                    <dt className="text-slate-500">Outstanding</dt>
                    <dd className="mt-0.5 font-semibold text-slate-900">
                      {formatMoney(
                        obligation.outstandingAmount,
                        obligation.currency,
                      )}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Original · paid</dt>
                    <dd className="mt-0.5 font-medium text-slate-700">
                      {formatMoney(obligation.amount, obligation.currency)} ·{' '}
                      {formatMoney(obligation.paidAmount, obligation.currency)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Issued</dt>
                    <dd className="mt-0.5 font-medium text-slate-700">
                      {obligation.issuedDate}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Due</dt>
                    <dd className="mt-0.5 font-medium text-slate-700">
                      {obligation.dueDate ?? 'No due date'}
                    </dd>
                  </div>
                </dl>
                {canSettle && (
                  <SettlementForm
                    kind={kind}
                    obligation={obligation}
                    onChanged={onChanged}
                  />
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

interface ObligationsPanelProps {
  readonly defaultCurrency: string;
  readonly people: readonly PersonData[];
  readonly receivables: readonly ObligationData[];
  readonly payables: readonly ObligationData[];
  readonly onChanged: () => Promise<void>;
}

export function ObligationsPanel({
  defaultCurrency,
  people,
  receivables,
  payables,
  onChanged,
}: ObligationsPanelProps) {
  const [kind, setKind] = useState<ObligationKind>('RECEIVABLE');
  const [personId, setPersonId] = useState('');
  const [amount, setAmount] = useState('');
  const [description, setDescription] = useState('');
  const [issuedDate, setIssuedDate] = useState(localDateValue);
  const [dueDate, setDueDate] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [feedback, setFeedback] = useState<MutationFeedback>({
    confirmation: null,
    error: null,
  });
  const [createReceivable] = useMutation<
    CreateReceivableMutationData,
    CreateObligationMutationVariables
  >(CREATE_RECEIVABLE_MUTATION);
  const [createPayable] = useMutation<
    CreatePayableMutationData,
    CreateObligationMutationVariables
  >(CREATE_PAYABLE_MUTATION);

  const clearFeedback = () => {
    setFeedback({ confirmation: null, error: null });
  };

  const submitObligation = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    clearFeedback();

    if (!personId) {
      setFeedback({
        confirmation: null,
        error: 'Choose a person for this obligation.',
      });
      return;
    }
    if (!isPositiveDecimalString(amount)) {
      setFeedback({
        confirmation: null,
        error:
          'Use a positive decimal amount with up to four fractional digits.',
      });
      return;
    }
    if (!description.trim()) {
      setFeedback({
        confirmation: null,
        error: 'Enter a description for this obligation.',
      });
      return;
    }

    setIsSaving(true);
    try {
      const variables = {
        input: {
          personId,
          amount,
          currency: defaultCurrency,
          description: description.trim(),
          issuedDate,
          dueDate: dueDate || null,
        },
      };
      let result:
        | MutationResult<'CreateReceivableSuccess' | 'CreatePayableSuccess'>
        | undefined;
      if (kind === 'RECEIVABLE') {
        const response = await createReceivable({ variables });
        result = response.data?.createReceivable;
      } else {
        const response = await createPayable({ variables });
        result = response.data?.createPayable;
      }
      const problem = mutationProblem(result);

      if (problem) {
        setFeedback({ confirmation: null, error: problem });
        return;
      }

      const expectedSuccess =
        kind === 'RECEIVABLE'
          ? 'CreateReceivableSuccess'
          : 'CreatePayableSuccess';
      if (result?.__typename !== expectedSuccess) {
        setFeedback({
          confirmation: null,
          error: 'The API did not confirm the obligation.',
        });
        return;
      }

      setAmount('');
      setDescription('');
      setDueDate('');
      try {
        await onChanged();
        setFeedback({
          confirmation: `${
            kind === 'RECEIVABLE' ? 'Receivable' : 'Payable'
          } saved and balances refreshed.`,
          error: null,
        });
      } catch {
        setFeedback({
          confirmation: null,
          error:
            'Obligation saved, but balances could not refresh. Retry the dashboard query to see current values.',
        });
      }
    } catch {
      setFeedback({
        confirmation: null,
        error:
          'The obligation could not be saved. Check the API connection and try again.',
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Card className="p-5 sm:p-6 xl:col-span-2">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">Money owed</h2>
          <p className="mt-1 text-xs leading-5 text-slate-600">
            Track receivables, payables, and immutable settlement records.
          </p>
        </div>
        <span
          className="grid size-9 shrink-0 place-items-center rounded-xl bg-blue-50 text-blue-700"
          aria-hidden="true"
        >
          <CircleDollarSign className="size-4" />
        </span>
      </div>

      <form
        className="mt-4 grid grid-cols-1 gap-3 rounded-xl border border-slate-200 bg-slate-50 p-4 sm:grid-cols-2 xl:grid-cols-3"
        onSubmit={(event) => {
          void submitObligation(event);
        }}
      >
        <div>
          <label
            htmlFor="obligation-kind"
            className="text-[10px] font-semibold text-slate-700"
          >
            Direction
          </label>
          <select
            id="obligation-kind"
            value={kind}
            onChange={(event) => {
              setKind(event.target.value as ObligationKind);
              clearFeedback();
            }}
            className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"
          >
            <option value="RECEIVABLE">They owe you</option>
            <option value="PAYABLE">You owe them</option>
          </select>
        </div>
        <div>
          <label
            htmlFor="obligation-person"
            className="text-[10px] font-semibold text-slate-700"
          >
            Person
          </label>
          <select
            id="obligation-person"
            value={personId}
            required
            disabled={people.length === 0}
            onChange={(event) => {
              setPersonId(event.target.value);
              clearFeedback();
            }}
            className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs disabled:bg-slate-100"
          >
            <option value="">
              {people.length === 0 ? 'Add a person first' : 'Choose a person'}
            </option>
            {people.map((person) => (
              <option key={person.id} value={person.id}>
                {person.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label
            htmlFor="obligation-amount"
            className="text-[10px] font-semibold text-slate-700"
          >
            Amount
          </label>
          <div className="mt-1 flex rounded-lg border border-slate-200 bg-white">
            <input
              id="obligation-amount"
              value={amount}
              required
              inputMode="decimal"
              placeholder="1250.00"
              onChange={(event) => {
                setAmount(event.target.value);
                clearFeedback();
              }}
              className="min-w-0 flex-1 bg-transparent px-2.5 py-2 text-xs"
            />
            <span className="flex items-center border-l border-slate-200 px-2 text-[9px] font-semibold text-slate-500">
              {defaultCurrency}
            </span>
          </div>
        </div>
        <div className="sm:col-span-2 xl:col-span-1">
          <label
            htmlFor="obligation-description"
            className="text-[10px] font-semibold text-slate-700"
          >
            Description
          </label>
          <input
            id="obligation-description"
            value={description}
            required
            maxLength={500}
            placeholder="Shared hotel booking"
            onChange={(event) => {
              setDescription(event.target.value);
              clearFeedback();
            }}
            className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"
          />
        </div>
        <div>
          <label
            htmlFor="obligation-issued-date"
            className="text-[10px] font-semibold text-slate-700"
          >
            Issued date
          </label>
          <input
            id="obligation-issued-date"
            type="date"
            value={issuedDate}
            required
            onChange={(event) => {
              setIssuedDate(event.target.value);
              clearFeedback();
            }}
            className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"
          />
        </div>
        <div>
          <label
            htmlFor="obligation-due-date"
            className="text-[10px] font-semibold text-slate-700"
          >
            Due date{' '}
            <span className="font-normal text-slate-500">(optional)</span>
          </label>
          <input
            id="obligation-due-date"
            type="date"
            value={dueDate}
            min={issuedDate}
            onChange={(event) => {
              setDueDate(event.target.value);
              clearFeedback();
            }}
            className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"
          />
        </div>
        <button
          type="submit"
          disabled={isSaving || people.length === 0}
          className="bg-ink-900 hover:bg-ink-800 rounded-lg px-3 py-2 text-[11px] font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60 sm:col-span-2 xl:col-span-3"
        >
          {isSaving
            ? 'Saving…'
            : `Add ${kind === 'RECEIVABLE' ? 'receivable' : 'payable'}`}
        </button>
        {feedback.confirmation && (
          <p
            className="bg-leaf-50 text-leaf-700 rounded-lg px-3 py-2 text-[10px] sm:col-span-2 xl:col-span-3"
            role="status"
          >
            {feedback.confirmation}
          </p>
        )}
        {feedback.error && (
          <p
            className="rounded-lg bg-amber-50 px-3 py-2 text-[10px] leading-4 text-amber-800 sm:col-span-2 xl:col-span-3"
            role="alert"
          >
            {feedback.error}
          </p>
        )}
      </form>

      <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-2">
        <ObligationList
          kind="RECEIVABLE"
          obligations={receivables}
          onChanged={onChanged}
        />
        <ObligationList
          kind="PAYABLE"
          obligations={payables}
          onChanged={onChanged}
        />
      </div>
    </Card>
  );
}
