import {
  formatLedgerDate,
  formatTransactionAmount,
  getTransactionDirection,
} from '../../lib/ledger-formatters';
import { Card } from './Card';
import type {
  DashboardRecentActivityData,
  DashboardTransactionStatus,
} from './types';

function titleCaseStatus(status: DashboardTransactionStatus): string {
  return `${status.charAt(0)}${status.slice(1).toLowerCase()}`;
}

function initials(label: string): string {
  const words = label.trim().split(/\s+/).filter(Boolean);
  return (
    words
      .slice(0, 2)
      .map((word) => word.charAt(0).toUpperCase())
      .join('') || 'TX'
  );
}

export function RecentActivity({
  description,
  statusLabel,
  tableCaption,
  timeZone,
  transactions,
}: DashboardRecentActivityData) {
  return (
    <Card id="transactions" className="overflow-hidden">
      <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4 sm:px-6">
        <div>
          <h2 className="text-sm font-semibold text-slate-800">
            Recent activity
          </h2>
          <p className="mt-1 text-[11px] font-medium text-slate-600">
            {description}
          </p>
        </div>
        {statusLabel && (
          <span className="rounded-full bg-mist-100 px-2.5 py-1 text-[10px] font-semibold text-slate-600">
            {statusLabel}
          </span>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[660px] border-collapse text-left">
          <caption className="sr-only">{tableCaption}</caption>
          <thead>
            <tr className="border-b border-slate-100 text-[10px] font-semibold tracking-[0.1em] text-slate-600 uppercase">
              <th scope="col" className="px-5 py-3 sm:px-6">
                Merchant or person
              </th>
              <th scope="col" className="px-4 py-3">
                Category
              </th>
              <th scope="col" className="px-4 py-3">
                Status
              </th>
              <th scope="col" className="px-4 py-3 text-right">
                Amount
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {transactions.length > 0 ? (
              transactions.map((transaction) => {
                const label =
                  transaction.merchantName ?? transaction.description;
                const direction = getTransactionDirection(
                  transaction.transactionType,
                );

                return (
                  <tr
                    key={transaction.id}
                    className="group hover:bg-mist-50/70"
                  >
                    <th scope="row" className="px-5 py-3.5 font-normal sm:px-6">
                      <div className="flex items-center gap-3">
                        <span
                          className={`grid size-9 shrink-0 place-items-center rounded-xl text-[10px] font-bold ${
                            direction === 'inflow'
                              ? 'bg-leaf-50 text-leaf-700'
                              : direction === 'outflow'
                                ? 'bg-slate-100 text-slate-700'
                                : 'bg-blue-50 text-blue-700'
                          }`}
                          aria-hidden="true"
                        >
                          {initials(label)}
                        </span>
                        <span>
                          <span className="block text-xs font-semibold text-slate-700">
                            {label}
                          </span>
                          <span className="mt-0.5 block text-[10px] font-medium text-slate-600">
                            {formatLedgerDate(
                              transaction.transactionDate,
                              timeZone,
                            )}
                          </span>
                        </span>
                      </div>
                    </th>
                    <td className="px-4 py-3.5 text-xs text-slate-500">
                      {transaction.categoryName ?? 'Uncategorized'}
                    </td>
                    <td className="px-4 py-3.5">
                      <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-medium text-slate-500">
                        {titleCaseStatus(transaction.status)}
                      </span>
                    </td>
                    <td
                      className={`px-4 py-3.5 text-right text-xs font-semibold tabular-nums ${
                        direction === 'inflow'
                          ? 'text-leaf-700'
                          : 'text-slate-800'
                      }`}
                    >
                      {formatTransactionAmount(
                        transaction.amount,
                        transaction.currency,
                        transaction.transactionType,
                      )}
                    </td>
                  </tr>
                );
              })
            ) : (
              <tr>
                <td
                  colSpan={4}
                  className="px-5 py-10 text-center text-xs text-slate-600 sm:px-6"
                >
                  No transactions have been recorded yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
