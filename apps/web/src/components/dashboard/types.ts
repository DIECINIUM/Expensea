export type SummaryTone = 'emerald' | 'blue' | 'amber' | 'violet';

export interface DashboardSummaryItem {
  readonly id: string;
  readonly label: string;
  readonly amount: string;
  readonly currency: string;
  readonly detail: string;
  readonly trend?: string;
  readonly tone: SummaryTone;
}

export interface DashboardCategoryItem {
  readonly id: string;
  readonly name: string;
  readonly amount: string;
  readonly currency: string;
  /**
   * A service-provided display percentage. The presentation layer must not
   * derive financial totals from category rows.
   */
  readonly sharePercentage: number;
}

export interface DashboardSpendingPoint {
  /** ISO calendar date identifying the first day of the represented month. */
  readonly monthStart: string;
  /** Decimal string returned by the API. */
  readonly amount: string;
}

export interface DashboardSpendingTrendData {
  readonly currentAmount: string;
  readonly currency: string;
  readonly comparisonLabel: string;
  readonly statusLabel?: string;
  readonly points: readonly DashboardSpendingPoint[];
}

export type DashboardTransactionType =
  'EXPENSE' | 'INCOME' | 'TRANSFER' | 'REFUND' | 'SHARED_EXPENSE';

export type DashboardTransactionStatus = 'PENDING' | 'POSTED' | 'VOIDED';

export interface DashboardTransaction {
  readonly id: string;
  readonly amount: string;
  readonly currency: string;
  readonly transactionType: DashboardTransactionType;
  readonly description: string;
  /** ISO 8601 instant returned by the API. */
  readonly transactionDate: string;
  readonly status: DashboardTransactionStatus;
  readonly merchantName: string | null;
  readonly categoryName: string | null;
}

export interface DashboardCategoryBreakdownData {
  readonly periodLabel: string;
  readonly statusLabel?: string;
  readonly categories: readonly DashboardCategoryItem[];
}

export interface DashboardRecentActivityData {
  readonly description: string;
  readonly statusLabel?: string;
  readonly tableCaption: string;
  readonly timeZone: string;
  readonly transactions: readonly DashboardTransaction[];
}

export interface DashboardPresentationData {
  readonly greetingName: string;
  readonly periodLabel: string;
  readonly summaryItems: readonly DashboardSummaryItem[];
  readonly spendingTrend: DashboardSpendingTrendData;
  readonly categoryBreakdown: DashboardCategoryBreakdownData;
  readonly recentActivity: DashboardRecentActivityData;
  readonly footerNote?: string;
}
