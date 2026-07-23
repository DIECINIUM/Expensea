import { FlaskConical, Sparkles } from 'lucide-react';

import { Card } from './Card';

export function InsightPanel() {
  return (
    <Card id="assistant" className="p-5 sm:p-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="grid size-9 place-items-center rounded-xl bg-violet-50 text-violet-700">
            <Sparkles className="size-[18px]" aria-hidden="true" />
          </span>
          <div>
            <h2 className="text-sm font-semibold text-slate-800">
              AI insight preview
            </h2>
            <p className="mt-0.5 text-[10px] font-medium text-slate-600">
              Illustrative copy · no live analysis
            </p>
          </div>
        </div>
        <span className="rounded-full bg-violet-50 px-2.5 py-1 text-[10px] font-semibold text-violet-700">
          Synthetic
        </span>
      </div>

      <p className="mt-5 text-sm leading-5 font-semibold text-slate-800">
        Example: your spending is ₹1,660 lower than this point last month.
      </p>
      <p className="mt-2 text-xs leading-5 text-slate-500">
        Shopping contributed most to the decrease, down ₹2,140. Travel rose by
        ₹620, which partially offset those savings.
      </p>

      <div className="mt-5 flex items-center justify-between border-t border-slate-100 pt-4">
        <span className="inline-flex items-center gap-1.5 text-[10px] font-medium text-slate-600">
          <FlaskConical
            className="size-3.5 text-violet-600"
            aria-hidden="true"
          />
          Preview only · no records queried
        </span>
      </div>
    </Card>
  );
}
