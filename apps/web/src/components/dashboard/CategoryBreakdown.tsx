import { formatMoney, formatPercentage } from '../../lib/ledger-formatters';
import { Card } from './Card';
import type { DashboardCategoryBreakdownData } from './types';

const categoryColors = ['#2c9b67', '#315f8c', '#d08b45', '#8065a8', '#8a9892'];

function categoryColor(index: number): string {
  return categoryColors[index % categoryColors.length] ?? '#8a9892';
}

function visualShare(sharePercentage: number): number {
  if (!Number.isFinite(sharePercentage)) {
    return 0;
  }
  return Math.min(100, Math.max(0, sharePercentage));
}

export function CategoryBreakdown({
  categories,
  periodLabel,
  statusLabel,
}: DashboardCategoryBreakdownData) {
  return (
    <Card className="p-5 sm:p-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-slate-800">By category</h2>
          <p className="mt-1 text-[11px] font-medium text-slate-600">
            {periodLabel}
          </p>
        </div>
        {statusLabel && (
          <span className="rounded-full bg-mist-100 px-2.5 py-1 text-[10px] font-semibold text-slate-600">
            {statusLabel}
          </span>
        )}
      </div>

      {categories.length > 0 ? (
        <>
          <div
            className="mt-5 flex h-2 overflow-hidden rounded-full bg-slate-100"
            aria-hidden="true"
          >
            {categories.map((category, index) => (
              <span
                key={category.id}
                style={{
                  width: `${visualShare(category.sharePercentage)}%`,
                  backgroundColor: categoryColor(index),
                }}
              />
            ))}
          </div>

          <ul className="mt-5 space-y-3.5">
            {categories.map((category, index) => (
              <li key={category.id} className="flex items-center gap-3">
                <span
                  className="size-2.5 shrink-0 rounded-[4px]"
                  style={{ backgroundColor: categoryColor(index) }}
                  aria-hidden="true"
                />
                <span className="min-w-0 flex-1 truncate text-xs font-medium text-slate-600">
                  {category.name}
                </span>
                <span className="text-xs font-semibold text-slate-800 tabular-nums">
                  {formatMoney(category.amount, category.currency)}
                </span>
                <span className="w-7 text-right text-[10px] font-medium text-slate-600 tabular-nums">
                  {formatPercentage(category.sharePercentage)}
                </span>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p className="mt-5 rounded-xl bg-mist-50 px-4 py-5 text-center text-xs text-slate-600">
          No categorized spending in this period.
        </p>
      )}
    </Card>
  );
}
