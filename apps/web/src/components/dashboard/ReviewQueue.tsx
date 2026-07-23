import { AlertCircle, Mail } from 'lucide-react';

import { Card } from './Card';

export function ReviewQueue() {
  return (
    <Card className="p-5 sm:p-6" id="review">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-800">
            Review queue preview
          </h2>
          <p className="mt-1 text-[11px] font-medium text-slate-600">
            Synthetic event for layout testing
          </p>
        </div>
        <span className="grid size-8 place-items-center rounded-lg bg-amber-50 text-amber-700">
          <AlertCircle className="size-4" aria-hidden="true" />
        </span>
      </div>

      <div className="mt-5 rounded-xl border border-amber-100 bg-amber-50/50 p-4">
        <div className="flex gap-3">
          <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-white text-slate-500 shadow-sm">
            <Mail className="size-4" aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-xs font-semibold text-slate-700">
                  Example: possible refund
                </p>
                <p className="mt-0.5 truncate text-[10px] font-medium text-slate-600">
                  Amazon · Email receipt
                </p>
              </div>
              <span className="text-xs font-semibold text-slate-800">
                ₹1,299
              </span>
            </div>
            <div className="mt-3 flex items-center justify-between gap-3">
              <span className="text-[10px] font-semibold text-amber-800">
                Example confidence: 72%
              </span>
              <span className="rounded-full bg-white px-2 py-1 text-[10px] font-semibold text-slate-600 shadow-sm">
                Not actionable
              </span>
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
}
