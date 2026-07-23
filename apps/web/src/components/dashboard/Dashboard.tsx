import { Plus } from 'lucide-react';

import { summaryItems } from '../../lib/demo-data';
import { CategoryBreakdown } from './CategoryBreakdown';
import { InsightPanel } from './InsightPanel';
import { QuickCaptureCard } from './QuickCaptureCard';
import { RecentActivity } from './RecentActivity';
import { ReviewQueue } from './ReviewQueue';
import { SpendingTrend } from './SpendingTrend';
import { SummaryCard } from './SummaryCard';

export function Dashboard() {
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
              Good morning, Salik
            </h2>
            <p className="mt-1.5 text-xs text-slate-500">
              Here is your explainable financial picture for July.
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
          {summaryItems.map((item) => (
            <SummaryCard key={item.label} item={item} />
          ))}
        </div>

        <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
          <div className="xl:col-span-2">
            <SpendingTrend />
          </div>
          <QuickCaptureCard />
        </div>

        <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
          <CategoryBreakdown />
          <InsightPanel />
          <ReviewQueue />
        </div>

        <div className="mt-4">
          <RecentActivity />
        </div>

        <p className="mt-5 text-center text-[10px] font-medium text-slate-600">
          All financial values and records are synthetic Phase 0 previews. Live
          totals will come from deterministic ledger services.
        </p>
      </section>
    </div>
  );
}
