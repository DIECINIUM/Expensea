import { CalendarCheck, Repeat2 } from 'lucide-react';
import { type FormEvent, useState } from 'react';
import { useMutation } from '@apollo/client/react';

import { Card } from './Card';
import type {
  RecurrenceRule,
  RecurringPaymentData,
  RecurringPaymentStatus,
} from '../../graphql/dashboard';
import {
  CREATE_RECURRING_PAYMENT_MUTATION,
  RECORD_RECURRING_PAYMENT_MUTATION,
  SET_RECURRING_PAYMENT_STATUS_MUTATION,
  type CreateRecurringPaymentMutationData,
  type CreateRecurringPaymentMutationVariables,
  type RecordRecurringPaymentMutationData,
  type RecordRecurringPaymentMutationVariables,
  type SetRecurringPaymentStatusMutationData,
  type SetRecurringPaymentStatusMutationVariables,
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

const recurrenceRules: readonly RecurrenceRule[] = [
  'WEEKLY',
  'MONTHLY',
  'QUARTERLY',
  'YEARLY',
];
const selectableStatuses: readonly RecurringPaymentStatus[] = [
  'ACTIVE',
  'PAUSED',
  'ENDED',
];

interface MutationFeedback {
  readonly confirmation: string | null;
  readonly error: string | null;
}

interface RecurringPaymentActionsProps {
  readonly payment: RecurringPaymentData;
  readonly onChanged: () => Promise<void>;
}

function RecurringPaymentActions({
  payment,
  onChanged,
}: RecurringPaymentActionsProps) {
  const actionId = `recurring-${payment.id}`;
  const initialSelectableStatus = selectableStatuses.includes(payment.status)
    ? payment.status
    : 'ACTIVE';
  const [status, setStatus] = useState<RecurringPaymentStatus>(
    initialSelectableStatus,
  );
  const [expectedDate, setExpectedDate] = useState(payment.nextExpectedDate);
  const [transactionDate, setTransactionDate] = useState(localDateTimeValue);
  const [isChangingStatus, setIsChangingStatus] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [statusFeedback, setStatusFeedback] = useState<MutationFeedback>({
    confirmation: null,
    error: null,
  });
  const [recordFeedback, setRecordFeedback] = useState<MutationFeedback>({
    confirmation: null,
    error: null,
  });
  const [setRecurringStatus] = useMutation<
    SetRecurringPaymentStatusMutationData,
    SetRecurringPaymentStatusMutationVariables
  >(SET_RECURRING_PAYMENT_STATUS_MUTATION);
  const [recordRecurringPayment] = useMutation<
    RecordRecurringPaymentMutationData,
    RecordRecurringPaymentMutationVariables
  >(RECORD_RECURRING_PAYMENT_MUTATION);

  const submitStatus = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setStatusFeedback({ confirmation: null, error: null });
    setIsChangingStatus(true);

    try {
      const response = await setRecurringStatus({
        variables: { id: payment.id, status },
      });
      const result = response.data?.setRecurringPaymentStatus;
      const problem = mutationProblem(result);

      if (problem) {
        setStatusFeedback({ confirmation: null, error: problem });
        return;
      }
      if (result?.__typename !== 'SetRecurringPaymentStatusSuccess') {
        setStatusFeedback({
          confirmation: null,
          error: 'The API did not confirm the status change.',
        });
        return;
      }

      try {
        await onChanged();
        setStatusFeedback({
          confirmation: 'Status updated and schedule refreshed.',
          error: null,
        });
      } catch {
        setStatusFeedback({
          confirmation: null,
          error:
            'Status updated, but the schedule could not refresh. Retry the dashboard query.',
        });
      }
    } catch {
      setStatusFeedback({
        confirmation: null,
        error:
          'The status could not be updated. Check the API connection and try again.',
      });
    } finally {
      setIsChangingStatus(false);
    }
  };

  const submitOccurrence = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setRecordFeedback({ confirmation: null, error: null });
    setIsRecording(true);

    try {
      const response = await recordRecurringPayment({
        variables: {
          id: payment.id,
          expectedDate,
          transactionDate: localDateTimeToIso(transactionDate),
        },
      });
      const result = response.data?.recordRecurringPayment;
      const problem = mutationProblem(result);

      if (problem) {
        setRecordFeedback({ confirmation: null, error: problem });
        return;
      }
      if (result?.__typename !== 'RecordRecurringPaymentSuccess') {
        setRecordFeedback({
          confirmation: null,
          error: 'The API did not confirm the recorded payment.',
        });
        return;
      }

      try {
        await onChanged();
        setRecordFeedback({
          confirmation: 'Payment recorded and ledger values refreshed.',
          error: null,
        });
      } catch {
        setRecordFeedback({
          confirmation: null,
          error:
            'Payment recorded, but ledger values could not refresh. Retry the dashboard query before recording it again.',
        });
      }
    } catch {
      setRecordFeedback({
        confirmation: null,
        error:
          'The payment could not be recorded. Check the API connection and try again.',
      });
    } finally {
      setIsRecording(false);
    }
  };

  return (
    <div className="mt-3 space-y-2 border-t border-slate-100 pt-3">
      <form
        className="flex flex-col gap-2 sm:flex-row"
        onSubmit={(event) => {
          void submitStatus(event);
        }}
      >
        <label htmlFor={`${actionId}-status`} className="sr-only">
          Status for {payment.merchantName}
        </label>
        <select
          id={`${actionId}-status`}
          value={status}
          onChange={(event) => {
            setStatus(event.target.value as RecurringPaymentStatus);
            setStatusFeedback({ confirmation: null, error: null });
          }}
          className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-[11px]"
        >
          {selectableStatuses.map((option) => (
            <option key={option} value={option}>
              {readableEnum(option)}
            </option>
          ))}
        </select>
        <button
          type="submit"
          disabled={isChangingStatus || status === payment.status}
          className="rounded-lg border border-slate-300 px-3 py-2 text-[11px] font-semibold text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isChangingStatus ? 'Updating…' : 'Update status'}
        </button>
      </form>
      {statusFeedback.confirmation && (
        <p
          className="bg-leaf-50 text-leaf-700 rounded-lg px-3 py-2 text-[10px]"
          role="status"
        >
          {statusFeedback.confirmation}
        </p>
      )}
      {statusFeedback.error && (
        <p
          className="rounded-lg bg-amber-50 px-3 py-2 text-[10px] leading-4 text-amber-800"
          role="alert"
        >
          {statusFeedback.error}
        </p>
      )}

      {payment.status !== 'ENDED' && (
        <details className="rounded-xl border border-slate-200 bg-slate-50">
          <summary className="cursor-pointer px-3 py-2 text-[11px] font-semibold text-slate-700">
            Record expected payment
          </summary>
          <form
            className="grid grid-cols-1 gap-2 border-t border-slate-200 p-3"
            onSubmit={(event) => {
              void submitOccurrence(event);
            }}
          >
            <div>
              <label
                htmlFor={`${actionId}-expected-date`}
                className="text-[10px] font-semibold text-slate-700"
              >
                Expected date
              </label>
              <input
                id={`${actionId}-expected-date`}
                type="date"
                value={expectedDate}
                required
                onChange={(event) => {
                  setExpectedDate(event.target.value);
                  setRecordFeedback({ confirmation: null, error: null });
                }}
                className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"
              />
            </div>
            <div>
              <label
                htmlFor={`${actionId}-transaction-date`}
                className="text-[10px] font-semibold text-slate-700"
              >
                Transaction date and time
              </label>
              <input
                id={`${actionId}-transaction-date`}
                type="datetime-local"
                value={transactionDate}
                required
                onChange={(event) => {
                  setTransactionDate(event.target.value);
                  setRecordFeedback({ confirmation: null, error: null });
                }}
                className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"
              />
            </div>
            <button
              type="submit"
              disabled={isRecording}
              className="bg-ink-900 hover:bg-ink-800 rounded-lg px-3 py-2 text-[11px] font-semibold text-white disabled:cursor-wait disabled:opacity-70"
            >
              {isRecording ? 'Recording…' : 'Record payment'}
            </button>
            {recordFeedback.confirmation && (
              <p
                className="bg-leaf-50 text-leaf-700 rounded-lg px-3 py-2 text-[10px]"
                role="status"
              >
                {recordFeedback.confirmation}
              </p>
            )}
            {recordFeedback.error && (
              <p
                className="rounded-lg bg-amber-50 px-3 py-2 text-[10px] leading-4 text-amber-800"
                role="alert"
              >
                {recordFeedback.error}
              </p>
            )}
          </form>
        </details>
      )}
    </div>
  );
}

interface RecurringPaymentsPanelProps {
  readonly defaultCurrency: string;
  readonly payments: readonly RecurringPaymentData[];
  readonly onChanged: () => Promise<void>;
}

export function RecurringPaymentsPanel({
  defaultCurrency,
  payments,
  onChanged,
}: RecurringPaymentsPanelProps) {
  const [merchantName, setMerchantName] = useState('');
  const [amount, setAmount] = useState('');
  const [recurrenceRule, setRecurrenceRule] =
    useState<RecurrenceRule>('MONTHLY');
  const [nextExpectedDate, setNextExpectedDate] = useState(localDateValue);
  const [isSaving, setIsSaving] = useState(false);
  const [feedback, setFeedback] = useState<MutationFeedback>({
    confirmation: null,
    error: null,
  });
  const [createRecurringPayment] = useMutation<
    CreateRecurringPaymentMutationData,
    CreateRecurringPaymentMutationVariables
  >(CREATE_RECURRING_PAYMENT_MUTATION);

  const clearFeedback = () => {
    setFeedback({ confirmation: null, error: null });
  };

  const submitRecurringPayment = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    clearFeedback();

    if (!merchantName.trim()) {
      setFeedback({
        confirmation: null,
        error: 'Enter a merchant name.',
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

    setIsSaving(true);
    try {
      const response = await createRecurringPayment({
        variables: {
          input: {
            merchantName: merchantName.trim(),
            amount,
            currency: defaultCurrency,
            recurrenceRule,
            nextExpectedDate,
          },
        },
      });
      const result = response.data?.createRecurringPayment;
      const problem = mutationProblem(result);

      if (problem) {
        setFeedback({ confirmation: null, error: problem });
        return;
      }
      if (result?.__typename !== 'CreateRecurringPaymentSuccess') {
        setFeedback({
          confirmation: null,
          error: 'The API did not confirm the recurring payment.',
        });
        return;
      }

      setMerchantName('');
      setAmount('');
      try {
        await onChanged();
        setFeedback({
          confirmation: 'Recurring payment saved and schedule refreshed.',
          error: null,
        });
      } catch {
        setFeedback({
          confirmation: null,
          error:
            'Recurring payment saved, but the schedule could not refresh. Retry the dashboard query.',
        });
      }
    } catch {
      setFeedback({
        confirmation: null,
        error:
          'The recurring payment could not be saved. Check the API connection and try again.',
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Card className="p-5 sm:p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">
            Recurring payments
          </h2>
          <p className="mt-1 text-xs leading-5 text-slate-600">
            Manage expected expenses without guessing future transactions.
          </p>
        </div>
        <span
          className="grid size-9 shrink-0 place-items-center rounded-xl bg-violet-50 text-violet-700"
          aria-hidden="true"
        >
          <Repeat2 className="size-4" />
        </span>
      </div>

      <form
        className="mt-4 grid grid-cols-1 gap-3 rounded-xl border border-slate-200 bg-slate-50 p-4 sm:grid-cols-2"
        onSubmit={(event) => {
          void submitRecurringPayment(event);
        }}
      >
        <div className="sm:col-span-2">
          <label
            htmlFor="recurring-merchant"
            className="text-[10px] font-semibold text-slate-700"
          >
            Merchant
          </label>
          <input
            id="recurring-merchant"
            value={merchantName}
            required
            maxLength={160}
            placeholder="Internet provider"
            onChange={(event) => {
              setMerchantName(event.target.value);
              clearFeedback();
            }}
            className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"
          />
        </div>
        <div>
          <label
            htmlFor="recurring-amount"
            className="text-[10px] font-semibold text-slate-700"
          >
            Amount
          </label>
          <div className="mt-1 flex rounded-lg border border-slate-200 bg-white">
            <input
              id="recurring-amount"
              value={amount}
              required
              inputMode="decimal"
              placeholder="999.00"
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
        <div>
          <label
            htmlFor="recurrence-rule"
            className="text-[10px] font-semibold text-slate-700"
          >
            Frequency
          </label>
          <select
            id="recurrence-rule"
            value={recurrenceRule}
            onChange={(event) => {
              setRecurrenceRule(event.target.value as RecurrenceRule);
              clearFeedback();
            }}
            className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"
          >
            {recurrenceRules.map((rule) => (
              <option key={rule} value={rule}>
                {readableEnum(rule)}
              </option>
            ))}
          </select>
        </div>
        <div className="sm:col-span-2">
          <label
            htmlFor="recurring-next-date"
            className="text-[10px] font-semibold text-slate-700"
          >
            Next expected date
          </label>
          <input
            id="recurring-next-date"
            type="date"
            value={nextExpectedDate}
            required
            onChange={(event) => {
              setNextExpectedDate(event.target.value);
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
          {isSaving ? 'Saving…' : 'Add recurring payment'}
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

      {payments.length === 0 ? (
        <p className="mt-4 rounded-xl border border-dashed border-slate-200 px-3 py-4 text-center text-[11px] text-slate-600">
          No recurring payments recorded.
        </p>
      ) : (
        <ul className="mt-4 space-y-3" aria-label="Recurring payments">
          {payments.map((payment) => (
            <li
              key={payment.id}
              className="rounded-xl border border-slate-200 p-3"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-xs font-semibold text-slate-800">
                    {payment.merchantName}
                  </p>
                  <p className="mt-1 text-[10px] text-slate-600">
                    {formatMoney(payment.amount, payment.currency)} ·{' '}
                    {readableEnum(payment.recurrenceRule)}
                  </p>
                  <p className="mt-1 inline-flex items-center gap-1 text-[10px] text-slate-500">
                    <CalendarCheck className="size-3" aria-hidden="true" />
                    Next: {payment.nextExpectedDate}
                  </p>
                </div>
                <span className="rounded-full bg-slate-100 px-2 py-1 text-[9px] font-semibold text-slate-600">
                  {readableEnum(payment.status)}
                </span>
              </div>
              <RecurringPaymentActions
                payment={payment}
                onChanged={onChanged}
              />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
