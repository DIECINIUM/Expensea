import { categoryBreakdown } from '../../lib/demo-data';
import { Card } from './Card';

export function CategoryBreakdown() {
  return (
    <Card className="p-5 sm:p-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-slate-800">By category</h2>
          <p className="mt-1 text-[11px] font-medium text-slate-600">
            July spending allocation
          </p>
        </div>
        <span className="rounded-full bg-mist-100 px-2.5 py-1 text-[10px] font-semibold text-slate-600">
          Synthetic
        </span>
      </div>

      <div
        className="mt-5 flex h-2 overflow-hidden rounded-full bg-slate-100"
        aria-hidden="true"
      >
        {categoryBreakdown.map((category) => (
          <span
            key={category.name}
            style={{
              width: `${category.share}%`,
              backgroundColor: category.color,
            }}
          />
        ))}
      </div>

      <ul className="mt-5 space-y-3.5">
        {categoryBreakdown.map((category) => (
          <li key={category.name} className="flex items-center gap-3">
            <span
              className="size-2.5 shrink-0 rounded-[4px]"
              style={{ backgroundColor: category.color }}
              aria-hidden="true"
            />
            <span className="min-w-0 flex-1 truncate text-xs font-medium text-slate-600">
              {category.name}
            </span>
            <span className="text-xs font-semibold text-slate-800 tabular-nums">
              {category.amount}
            </span>
            <span className="w-7 text-right text-[10px] font-medium text-slate-600 tabular-nums">
              {category.share}%
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
