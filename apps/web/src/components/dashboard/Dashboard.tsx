import { Plus } from 'lucide-react';

import { CategoryBreakdown } from './CategoryBreakdown';
import { InsightPanel } from './InsightPanel';
import { QuickCaptureCard } from './QuickCaptureCard';
import { RecentActivity } from './RecentActivity';
import { ReviewQueue } from './ReviewQueue';
import { SpendingTrend } from './SpendingTrend';
import { SummaryCard } from './SummaryCard';
import { temporaryDashboardPresentationData } from './temporary-dashboard-adapter';
import type { DashboardPresentationData } from './types';

interface DashboardProps {
  readonly data?: DashboardPresentationData;
}

export function Dashboard({
  data = temporaryDashboardPresentationData,
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
            href="#quick-capture"
            className="bg-ink-900 hover:bg-ink-800 inline-flex w-fit items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-semibold text-white shadow-sm transition"
          >
            <Plus className="size-4" aria-hidden="true" />
            Add financial note
          </a>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {data.summaryItems.map((item) => (
            <SummaryCard key={item.id} item={item} />
          ))}
        </div>

        <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
          <div className="xl:col-span-2">
            <SpendingTrend {...data.spendingTrend} />
          </div>
          <QuickCaptureCard />
        </div>

        <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
          <CategoryBreakdown {...data.categoryBreakdown} />
          <InsightPanel />
          <ReviewQueue />
        </div>

        <div className="mt-4">
          <RecentActivity {...data.recentActivity} />
        </div>

        {data.footerNote && (
          <p className="mt-5 text-center text-[10px] font-medium text-slate-600">
            {data.footerNote}
          </p>
        )}
      </section>
    </div>
  );
}
