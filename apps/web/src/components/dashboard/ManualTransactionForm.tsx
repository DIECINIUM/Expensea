import { zodResolver } from '@hookform/resolvers/zod';
import { ArrowRight, ReceiptText } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { useMutation } from '@apollo/client/react';

import { Card } from './Card';
import type { DashboardCategoryData } from '../../graphql/dashboard';
import {
  CREATE_TRANSACTION_MUTATION,
  type CreateTransactionMutationData,
  type CreateTransactionMutationVariables,
} from '../../graphql/create-transaction';

const amountPattern = /^(?:0|[1-9]\d{0,14})(?:\.\d{1,4})?$/;

const transactionFormSchema = z.object({
  amount: z
    .string()
    .trim()
    .regex(
      amountPattern,
      'Use a positive decimal amount with up to four fractional digits.',
    )
    .refine(
      (amount) => /[1-9]/.test(amount),
      'Amount must be greater than zero.',
    ),
  transactionType: z.enum([
    'EXPENSE',
    'INCOME',
    'TRANSFER',
    'REFUND',
    'SHARED_EXPENSE',
  ]),
  description: z
    .string()
    .trim()
    .min(2, 'Describe the transaction in at least 2 characters.')
    .max(240, 'Keep the description under 240 characters.'),
  transactionDate: z
    .string()
    .min(1, 'Choose when the transaction happened.')
    .refine(
      (value) => !Number.isNaN(new Date(value).getTime()),
      'Choose a valid transaction date and time.',
    ),
  categoryId: z.string(),
});

type TransactionFormValues = z.infer<typeof transactionFormSchema>;
type TransactionFormField = keyof TransactionFormValues;

const transactionFormFields: readonly TransactionFormField[] = [
  'amount',
  'transactionType',
  'description',
  'transactionDate',
  'categoryId',
];

function defaultTransactionDate(): string {
  const now = new Date();
  const localTime = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return localTime.toISOString().slice(0, 16);
}

function formFieldForProblem(
  field: string | null,
): TransactionFormField | null {
  if (field && transactionFormFields.some((candidate) => candidate === field)) {
    return field as TransactionFormField;
  }
  return null;
}

interface ManualTransactionFormProps {
  readonly categories: readonly DashboardCategoryData[];
  readonly defaultCurrency: string;
  readonly initialTransactionDate?: string;
  readonly onCreated: () => Promise<void>;
}

export function ManualTransactionForm({
  categories,
  defaultCurrency,
  initialTransactionDate = defaultTransactionDate(),
  onCreated,
}: ManualTransactionFormProps) {
  const [confirmation, setConfirmation] = useState<string | null>(null);
  const [submissionError, setSubmissionError] = useState<string | null>(null);
  const [createTransaction] = useMutation<
    CreateTransactionMutationData,
    CreateTransactionMutationVariables
  >(CREATE_TRANSACTION_MUTATION);
  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<TransactionFormValues>({
    resolver: zodResolver(transactionFormSchema),
    defaultValues: {
      amount: '',
      transactionType: 'EXPENSE',
      description: '',
      transactionDate: initialTransactionDate,
      categoryId: '',
    },
  });

  const clearFeedback = () => {
    setConfirmation(null);
    setSubmissionError(null);
  };

  const submitTransaction = async (values: TransactionFormValues) => {
    clearFeedback();

    try {
      const response = await createTransaction({
        variables: {
          input: {
            amount: values.amount,
            currency: defaultCurrency,
            transactionType: values.transactionType,
            description: values.description,
            transactionDate: new Date(values.transactionDate).toISOString(),
            categoryId: values.categoryId || null,
          },
        },
      });
      const result = response.data?.createTransaction;

      if (!result) {
        setSubmissionError(
          'The API returned no transaction result. Your entry was not confirmed.',
        );
        return;
      }

      if (result.__typename !== 'CreateTransactionSuccess') {
        const problemField = formFieldForProblem(result.field);
        if (problemField) {
          setError(problemField, {
            type: 'server',
            message: result.message,
          });
        } else {
          setSubmissionError(result.message);
        }
        return;
      }

      reset({
        amount: '',
        transactionType: 'EXPENSE',
        description: '',
        transactionDate: defaultTransactionDate(),
        categoryId: '',
      });

      try {
        await onCreated();
        setConfirmation('Transaction saved and dashboard totals refreshed.');
      } catch {
        setSubmissionError(
          'Transaction saved, but the dashboard could not refresh. Retry the dashboard query to see current totals.',
        );
      }
    } catch {
      setSubmissionError(
        'The transaction could not be saved. Check the API connection and try again.',
      );
    }
  };

  return (
    <Card
      id="manual-transaction"
      className="border-ink-800 bg-ink-900 relative overflow-hidden p-5 text-white sm:p-6"
    >
      <div
        className="bg-leaf-500/10 pointer-events-none absolute -top-14 -right-12 size-44 rounded-full blur-2xl"
        aria-hidden="true"
      />
      <div className="relative">
        <div className="flex items-center gap-2">
          <span className="text-leaf-200 grid size-8 place-items-center rounded-lg bg-white/10">
            <ReceiptText className="size-4" aria-hidden="true" />
          </span>
          <div>
            <h2 className="text-sm font-semibold">Add transaction</h2>
            <p className="text-[10px] font-medium text-white/70">
              Manual ledger entry · {defaultCurrency}
            </p>
          </div>
        </div>

        <form
          className="mt-5 space-y-3"
          noValidate
          onSubmit={(event) => void handleSubmit(submitTransaction)(event)}
        >
          <div>
            <label
              htmlFor="transaction-amount"
              className="text-[11px] font-semibold text-white/85"
            >
              Amount
            </label>
            <div className="mt-1 flex rounded-xl border border-white/15 bg-white/[0.08] focus-within:border-white/35">
              <input
                id="transaction-amount"
                inputMode="decimal"
                placeholder="420.00"
                aria-invalid={Boolean(errors.amount)}
                aria-describedby={
                  errors.amount ? 'transaction-amount-error' : undefined
                }
                {...register('amount', { onChange: clearFeedback })}
                className="min-w-0 flex-1 bg-transparent px-3 py-2.5 text-xs text-white placeholder:text-white/50"
              />
              <span className="flex items-center border-l border-white/15 px-3 text-[10px] font-semibold text-white/70">
                {defaultCurrency}
              </span>
            </div>
            {errors.amount && (
              <p
                id="transaction-amount-error"
                className="mt-1 text-[10px] leading-4 text-amber-200"
              >
                {errors.amount.message}
              </p>
            )}
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-1">
            <div>
              <label
                htmlFor="transaction-type"
                className="text-[11px] font-semibold text-white/85"
              >
                Type
              </label>
              <select
                id="transaction-type"
                aria-invalid={Boolean(errors.transactionType)}
                aria-describedby={
                  errors.transactionType ? 'transaction-type-error' : undefined
                }
                {...register('transactionType', { onChange: clearFeedback })}
                className="mt-1 w-full rounded-xl border border-white/15 bg-white/[0.08] px-3 py-2.5 text-xs text-white"
              >
                <option className="text-slate-900" value="EXPENSE">
                  Expense
                </option>
                <option className="text-slate-900" value="INCOME">
                  Income
                </option>
                <option className="text-slate-900" value="TRANSFER">
                  Transfer
                </option>
                <option className="text-slate-900" value="REFUND">
                  Refund
                </option>
                <option className="text-slate-900" value="SHARED_EXPENSE">
                  Shared expense
                </option>
              </select>
              {errors.transactionType && (
                <p
                  id="transaction-type-error"
                  className="mt-1 text-[10px] leading-4 text-amber-200"
                >
                  {errors.transactionType.message}
                </p>
              )}
            </div>

            <div>
              <label
                htmlFor="transaction-category"
                className="text-[11px] font-semibold text-white/85"
              >
                Category
              </label>
              <select
                id="transaction-category"
                aria-invalid={Boolean(errors.categoryId)}
                aria-describedby={
                  errors.categoryId ? 'transaction-category-error' : undefined
                }
                {...register('categoryId', { onChange: clearFeedback })}
                className="mt-1 w-full rounded-xl border border-white/15 bg-white/[0.08] px-3 py-2.5 text-xs text-white"
              >
                <option className="text-slate-900" value="">
                  Uncategorized
                </option>
                {categories.map((category) => (
                  <option
                    key={category.id}
                    className="text-slate-900"
                    value={category.id}
                  >
                    {category.name}
                  </option>
                ))}
              </select>
              {errors.categoryId && (
                <p
                  id="transaction-category-error"
                  className="mt-1 text-[10px] leading-4 text-amber-200"
                >
                  {errors.categoryId.message}
                </p>
              )}
            </div>
          </div>

          <div>
            <label
              htmlFor="transaction-description"
              className="text-[11px] font-semibold text-white/85"
            >
              Description
            </label>
            <textarea
              id="transaction-description"
              rows={2}
              maxLength={240}
              placeholder="Dinner delivery"
              aria-invalid={Boolean(errors.description)}
              aria-describedby={
                errors.description ? 'transaction-description-error' : undefined
              }
              {...register('description', { onChange: clearFeedback })}
              className="mt-1 w-full resize-none rounded-xl border border-white/15 bg-white/[0.08] px-3 py-2.5 text-xs leading-relaxed text-white placeholder:text-white/50"
            />
            {errors.description && (
              <p
                id="transaction-description-error"
                className="mt-1 text-[10px] leading-4 text-amber-200"
              >
                {errors.description.message}
              </p>
            )}
          </div>

          <div>
            <label
              htmlFor="transaction-date"
              className="text-[11px] font-semibold text-white/85"
            >
              Date and time
            </label>
            <input
              id="transaction-date"
              type="datetime-local"
              aria-invalid={Boolean(errors.transactionDate)}
              aria-describedby={
                errors.transactionDate ? 'transaction-date-error' : undefined
              }
              {...register('transactionDate', { onChange: clearFeedback })}
              className="mt-1 w-full rounded-xl border border-white/15 bg-white/[0.08] px-3 py-2.5 text-xs text-white"
            />
            {errors.transactionDate && (
              <p
                id="transaction-date-error"
                className="mt-1 text-[10px] leading-4 text-amber-200"
              >
                {errors.transactionDate.message}
              </p>
            )}
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="bg-leaf-500 hover:bg-leaf-600 disabled:bg-leaf-700 mt-1 inline-flex w-full items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-xs font-semibold text-white shadow-sm transition disabled:cursor-wait"
          >
            {isSubmitting ? 'Saving transaction…' : 'Save transaction'}
            <ArrowRight className="size-3.5" aria-hidden="true" />
          </button>

          {confirmation && (
            <p
              className="text-leaf-100 rounded-lg bg-white/[0.06] px-3 py-2 text-[10px] leading-4"
              role="status"
            >
              {confirmation}
            </p>
          )}
          {submissionError && (
            <p
              className="rounded-lg bg-amber-300/10 px-3 py-2 text-[10px] leading-4 text-amber-100"
              role="alert"
            >
              {submissionError}
            </p>
          )}
        </form>
      </div>
    </Card>
  );
}
