import { Plus, ReceiptText } from 'lucide-react';

import { CategoryBreakdown } from './CategoryBreakdown';
import { Card } from './Card';
import { ManualTransactionForm } from './ManualTransactionForm';
import { ObligationsPanel } from './ObligationsPanel';
import { PeoplePanel } from './PeoplePanel';
import { RecentActivity } from './RecentActivity';
import { RecurringPaymentsPanel } from './RecurringPaymentsPanel';
import { SpendingTrend } from './SpendingTrend';
import { SummaryCard } from './SummaryCard';
import type { DashboardPresentationData } from './types';
import type {
  DashboardCategoryData,
  ObligationData,
  PersonData,
  RecurringPaymentData,
} from '../../graphql/dashboard';

interface DashboardProps {
  readonly categories: readonly DashboardCategoryData[];
  readonly data: DashboardPresentationData;
  readonly isEmpty: boolean;
  readonly isRefreshing: boolean;
  readonly people: readonly PersonData[];
  readonly receivables: readonly ObligationData[];
  readonly payables: readonly ObligationData[];
  readonly recurringPayments: readonly RecurringPaymentData[];
  readonly onDataChanged: () => Promise<void>;
  readonly refreshWarning: string | null;
}

export function Dashboard({
  categories,
  data,
  isEmpty,
  isRefreshing,
  people,
  receivables,
  payables,
  recurringPayments,
  onDataChanged,
  refreshWarning,
}: DashboardProps) {
  return (
    <div
      id="overview"
      className="mx-auto max-w-[1540px] px-4 py-6 md:px-7 md:py-8 lg:px-9"
    >
      <section aria-labelledby="dashboard-heading">
        <div className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
          <div>
            <p className="text-leaf-700 mb-1 text-xs font-semibold tracking-[0.12em] uppercase">
              Financial overview
            </p>
            <h2
              id="dashboard-heading"
              className="text-2xl font-semibold tracking-[-0.035em] text-slate-900 sm:text-[28px]"
            >
              Good morning, {data.greetingName}
            </h2>
            <p className="mt-1.5 text-xs text-slate-500">
              Here is your explainable financial picture for {data.periodLabel}.
            </p>
          </div>
          <a
            href="#manual-transaction"
            className="bg-ink-900 hover:bg-ink-800 inline-flex w-fit items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-semibold text-white shadow-sm transition"
          >
            <Plus className="size-4" aria-hidden="true" />
            Add transaction
          </a>
        </div>

        {isRefreshing && (
          <p
            className="mb-4 rounded-xl border border-blue-100 bg-blue-50 px-4 py-2 text-xs font-medium text-blue-800"
            role="status"
          >
            Refreshing ledger totals…
          </p>
        )}
        {refreshWarning && (
          <p
            className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2 text-xs font-medium text-amber-900"
            role="alert"
          >
            {refreshWarning}
          </p>
        )}

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {data.summaryItems.map((item) => (
            <SummaryCard key={item.id} item={item} />
          ))}
        </div>

        {isEmpty ? (
          <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
            <Card className="grid min-h-72 place-items-center p-6 text-center xl:col-span-2">
              <div className="max-w-sm">
                <span className="bg-leaf-50 text-leaf-700 mx-auto grid size-11 place-items-center rounded-xl">
                  <ReceiptText className="size-5" aria-hidden="true" />
                </span>
                <h3 className="mt-4 text-base font-semibold text-slate-800">
                  No ledger activity yet
                </h3>
                <p className="mt-2 text-xs leading-5 text-slate-600">
                  Your dashboard is empty because the API returned no financial
                  records. Add a manual transaction to create the first ledger
                  entry.
                </p>
                <a
                  href="#manual-transaction"
                  className="text-leaf-700 mt-4 inline-flex text-xs font-semibold hover:underline"
                >
                  Go to transaction form
                </a>
              </div>
            </Card>
            <ManualTransactionForm
              categories={categories}
              defaultCurrency={data.spendingTrend.currency}
              onCreated={onDataChanged}
            />
          </div>
        ) : (
          <>
            <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
              <div className="xl:col-span-2">
                <SpendingTrend {...data.spendingTrend} />
              </div>
              <ManualTransactionForm
                categories={categories}
                defaultCurrency={data.spendingTrend.currency}
                onCreated={onDataChanged}
              />
            </div>

            <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
              <CategoryBreakdown {...data.categoryBreakdown} />
              <div className="xl:col-span-2">
                <RecentActivity {...data.recentActivity} />
              </div>
            </div>
          </>
        )}

        <section
          id="management"
          className="mt-8 scroll-mt-24"
          aria-labelledby="management-heading"
        >
          <div className="mb-4">
            <p className="text-leaf-700 text-xs font-semibold tracking-[0.12em] uppercase">
              Phase 1 controls
            </p>
            <h2
              id="management-heading"
              className="mt-1 text-xl font-semibold tracking-[-0.025em] text-slate-900"
            >
              Manage your financial ledger
            </h2>
            <p className="mt-1 text-xs leading-5 text-slate-600">
              Record people, money owed, settlements, and recurring payments.
            </p>
          </div>
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <div id="people" className="scroll-mt-24">
              <PeoplePanel people={people} onChanged={onDataChanged} />
            </div>
            <div id="recurring" className="scroll-mt-24">
              <RecurringPaymentsPanel
                defaultCurrency={data.spendingTrend.currency}
                payments={recurringPayments}
                onChanged={onDataChanged}
              />
            </div>
            <div id="obligations" className="scroll-mt-24 xl:col-span-2">
              <ObligationsPanel
                defaultCurrency={data.spendingTrend.currency}
                people={people}
                receivables={receivables}
                payables={payables}
                onChanged={onDataChanged}
              />
            </div>
          </div>
        </section>

        {data.footerNote && (
          <p className="mt-5 text-center text-[10px] font-medium text-slate-600">
            {data.footerNote}
          </p>
        )}
      </section>
    </div>
  );
}
