import { Lightbulb, TrendingDown, TrendingUp } from 'lucide-react';

import type { AnalyticsReportData } from '../../graphql/dashboard';
import { formatMoney } from '../../lib/ledger-formatters';
import { Card } from './Card';

function signed(value: string): 'positive' | 'negative' | 'zero' {
  const parsed = Number(value);
  if (parsed > 0) return 'positive';
  if (parsed < 0) return 'negative';
  return 'zero';
}

export function InsightsPanel({
  report,
}: {
  readonly report: AnalyticsReportData;
}) {
  const direction = signed(report.totalChange);
  return (
    <Card id="insights" className="overflow-hidden">
      <div className="border-b border-slate-100 px-5 py-4 sm:px-6">
        <p className="text-leaf-700 text-[10px] font-semibold tracking-[0.12em] uppercase">
          Deterministic analysis
        </p>
        <h2 className="mt-1 text-sm font-semibold text-slate-800">
          Why spending changed
        </h2>
        <p className="mt-1 text-[11px] text-slate-600">
          Current month compared with the previous local calendar month. Every
          insight is grounded in ledger record IDs.
        </p>
      </div>

      <div className="grid gap-3 border-b border-slate-100 p-5 sm:grid-cols-3 sm:px-6">
        <Metric
          label="Total change"
          value={formatMoney(report.totalChange, report.currency)}
          direction={direction}
        />
        <Metric
          label="Transaction count"
          value={`${report.countChange >= 0 ? '+' : ''}${report.countChange}`}
          direction={
            report.countChange > 0
              ? 'positive'
              : report.countChange < 0
                ? 'negative'
                : 'zero'
          }
        />
        <Metric
          label="Average-size change"
          value={formatMoney(report.averageSizeChange, report.currency)}
          direction={signed(report.averageSizeChange)}
        />
      </div>

      <div className="grid gap-5 p-5 sm:px-6 lg:grid-cols-2">
        <div>
          <h3 className="text-xs font-semibold text-slate-700">
            Category contributions
          </h3>
          <ul className="mt-3 space-y-2">
            {report.contributions.length ? (
              report.contributions.slice(0, 6).map((item) => (
                <li
                  key={item.categoryId ?? item.categoryName}
                  className="flex items-center justify-between gap-3 text-xs"
                >
                  <span className="text-slate-600">{item.categoryName}</span>
                  <span className="font-semibold text-slate-800 tabular-nums">
                    {formatMoney(item.change, report.currency)}
                  </span>
                </li>
              ))
            ) : (
              <li className="text-xs text-slate-500">
                No posted spending in either period.
              </li>
            )}
          </ul>
        </div>

        <div>
          <h3 className="text-xs font-semibold text-slate-700">
            Grounded signals
          </h3>
          <ul className="mt-3 space-y-2">
            {report.insights.length ? (
              report.insights.map((insight) => (
                <li
                  key={`${insight.code}-${insight.supportingTransactionIds.join('-')}`}
                  className="rounded-xl bg-mist-50 p-3"
                >
                  <div className="flex gap-2">
                    <Lightbulb
                      className="text-leaf-700 mt-0.5 size-3.5 shrink-0"
                      aria-hidden="true"
                    />
                    <div>
                      <p className="text-xs font-semibold text-slate-700">
                        {insight.title}
                      </p>
                      <p className="mt-1 text-[11px] leading-4 text-slate-600">
                        {insight.detail}
                      </p>
                      <p className="mt-1 text-[10px] text-slate-500">
                        Grounded by{' '}
                        {insight.supportingTransactionIds.length +
                          insight.supportingObligationIds.length}{' '}
                        ledger record
                        {insight.supportingTransactionIds.length +
                          insight.supportingObligationIds.length ===
                        1
                          ? ''
                          : 's'}
                      </p>
                    </div>
                  </div>
                </li>
              ))
            ) : (
              <li className="text-xs text-slate-500">
                No conservative insight rule fired for this period.
              </li>
            )}
          </ul>
        </div>
      </div>
    </Card>
  );
}

function Metric({
  direction,
  label,
  value,
}: {
  readonly direction: 'positive' | 'negative' | 'zero';
  readonly label: string;
  readonly value: string;
}) {
  const Icon =
    direction === 'positive'
      ? TrendingUp
      : direction === 'negative'
        ? TrendingDown
        : Lightbulb;
  return (
    <div className="rounded-xl bg-slate-50 p-3">
      <div className="flex items-center gap-2 text-slate-500">
        <Icon className="size-3.5" aria-hidden="true" />
        <span className="text-[10px] font-semibold uppercase">{label}</span>
      </div>
      <p className="mt-2 text-sm font-semibold text-slate-800">{value}</p>
    </div>
  );
}
