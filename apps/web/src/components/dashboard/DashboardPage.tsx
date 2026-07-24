import { CircleAlert, LoaderCircle, RefreshCw } from 'lucide-react';
import { useQuery } from '@apollo/client/react';

import { Dashboard } from './Dashboard';
import type { DashboardPresentationData } from './types';
import {
  DASHBOARD_QUERY,
  type DashboardQueryData,
} from '../../graphql/dashboard';
import { formatLedgerMonth } from '../../lib/ledger-formatters';

function transactionCountLabel(count: number): string {
  return `${count} posted transaction${count === 1 ? '' : 's'}`;
}

function mapDashboardData(data: DashboardQueryData): DashboardPresentationData {
  const periodLabel = formatLedgerMonth(data.financialSummary.periodStart);
  const transactionNodes = data.transactions.edges.map((edge) => edge.node);

  return {
    greetingName: data.me.name,
    periodLabel,
    summaryItems: [
      {
        id: 'month-spending',
        label: 'Spent this month',
        amount: data.financialSummary.spent,
        currency: data.financialSummary.currency,
        detail: transactionCountLabel(data.financialSummary.transactionCount),
        trend: 'Posted expenses less posted refunds',
        tone: 'emerald',
      },
      {
        id: 'open-payables',
        label: 'You owe',
        amount: data.obligationSummary.openPayables,
        currency: data.obligationSummary.currency,
        detail: 'Open payable balance',
        trend: 'Settlements reduce this balance',
        tone: 'amber',
      },
      {
        id: 'open-receivables',
        label: 'Owed to you',
        amount: data.obligationSummary.openReceivables,
        currency: data.obligationSummary.currency,
        detail: 'Open receivable balance',
        trend: 'Tracked separately from income',
        tone: 'blue',
      },
      {
        id: 'upcoming-recurring',
        label: 'Upcoming recurring',
        amount: data.recurringSummary.upcomingAmount,
        currency: data.recurringSummary.currency,
        detail: `${data.recurringSummary.upcomingCount} expected payment${
          data.recurringSummary.upcomingCount === 1 ? '' : 's'
        }`,
        trend: `Through ${data.recurringSummary.windowEnd}`,
        tone: 'violet',
      },
    ],
    spendingTrend: {
      currentAmount: data.financialSummary.spent,
      currency: data.financialSummary.currency,
      comparisonLabel: 'Six-month spending history from the ledger',
      points: data.monthlySpending.map((point) => ({
        monthStart: point.monthStart,
        amount: point.amount,
      })),
    },
    categoryBreakdown: {
      periodLabel: `${periodLabel} spending allocation`,
      categories: data.spendingByCategory.map((category) => ({
        id: category.categoryId ?? 'uncategorized',
        name: category.categoryName ?? 'Uncategorized',
        amount: category.amount,
        currency: category.currency,
        sharePercentage: category.sharePercentage,
      })),
    },
    recentActivity: {
      description: data.transactions.pageInfo.hasNextPage
        ? 'Latest 10 ledger transactions · more available'
        : 'Latest ledger transactions',
      tableCaption: 'Latest transactions from the financial ledger',
      timeZone: data.me.timezone,
      transactions: transactionNodes,
    },
    footerNote:
      'Ledger values stay deterministic; AI-derived records appear only after explicit approval.',
  };
}

function isZeroDecimal(value: string): boolean {
  return /^0+(?:\.0+)?$/.test(value);
}

function dashboardIsEmpty(data: DashboardQueryData): boolean {
  return (
    data.transactions.edges.length === 0 &&
    isZeroDecimal(data.financialSummary.spent) &&
    isZeroDecimal(data.financialSummary.income)
  );
}

function DashboardLoading() {
  return (
    <div
      className="mx-auto max-w-[1540px] px-4 py-8 md:px-7 lg:px-9"
      role="status"
      aria-label="Loading financial dashboard"
      aria-busy="true"
      aria-live="polite"
    >
      <div className="shadow-card flex items-center gap-3 rounded-2xl border border-slate-200 bg-white p-5">
        <LoaderCircle
          className="text-leaf-700 size-5 animate-spin"
          aria-hidden="true"
        />
        <div>
          <p className="text-sm font-semibold text-slate-800">
            Loading financial dashboard
          </p>
          <p className="mt-1 text-xs text-slate-600">
            Requesting current ledger totals and transactions…
          </p>
        </div>
      </div>
      <div
        className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2"
        aria-hidden="true"
      >
        {[0, 1].map((item) => (
          <div
            key={item}
            className="h-32 animate-pulse rounded-2xl border border-slate-200 bg-white"
          />
        ))}
      </div>
    </div>
  );
}

interface DashboardErrorProps {
  readonly retry: () => void;
}

function DashboardError({ retry }: DashboardErrorProps) {
  return (
    <div className="mx-auto max-w-[1540px] px-4 py-8 md:px-7 lg:px-9">
      <div
        className="shadow-card rounded-2xl border border-amber-200 bg-white p-6"
        role="alert"
      >
        <span className="grid size-10 place-items-center rounded-xl bg-amber-50 text-amber-700">
          <CircleAlert className="size-5" aria-hidden="true" />
        </span>
        <h2 className="mt-4 text-base font-semibold text-slate-800">
          Financial dashboard unavailable
        </h2>
        <p className="mt-2 max-w-xl text-xs leading-5 text-slate-600">
          Ledger values are hidden because the GraphQL request failed. No demo
          or cached placeholder amounts are being substituted.
        </p>
        <button
          type="button"
          onClick={retry}
          className="bg-ink-900 hover:bg-ink-800 mt-4 inline-flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-semibold text-white"
        >
          <RefreshCw className="size-3.5" aria-hidden="true" />
          Retry dashboard
        </button>
      </div>
    </div>
  );
}

export function DashboardPage() {
  const { data, error, loading, refetch } = useQuery<DashboardQueryData>(
    DASHBOARD_QUERY,
    {
      notifyOnNetworkStatusChange: true,
    },
  );

  if (loading && !data) {
    return <DashboardLoading />;
  }

  if (!data) {
    return (
      <DashboardError
        retry={() => {
          void refetch();
        }}
      />
    );
  }

  const presentation = mapDashboardData(data);

  return (
    <Dashboard
      categories={data.categories}
      data={presentation}
      isEmpty={dashboardIsEmpty(data)}
      isRefreshing={loading}
      people={data.people}
      receivables={data.receivables}
      payables={data.payables}
      recurringPayments={data.recurringPayments}
      financialEventProposals={data.financialEventProposals}
      onDataChanged={async () => {
        const result = await refetch();
        if (result.error) {
          throw new Error('Dashboard refresh failed.');
        }
      }}
      refreshWarning={
        error
          ? 'The last refresh failed. Displayed ledger values may be stale; retry before relying on them.'
          : null
      }
    />
  );
}
