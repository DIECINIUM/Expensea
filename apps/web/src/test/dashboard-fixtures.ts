import { DASHBOARD_QUERY, type DashboardQueryData } from '../graphql/dashboard';

export const dashboardQueryData = {
  me: {
    id: 'user-001',
    name: 'Mohd Salik',
    defaultCurrency: 'INR',
    timezone: 'Asia/Kolkata',
  },
  financialSummary: {
    currency: 'INR',
    periodStart: '2026-07-01',
    periodEnd: '2026-08-01',
    spent: '18540.0000',
    income: '25000.0000',
    transactionCount: 32,
  },
  obligationSummary: {
    currency: 'INR',
    openPayables: '600.0000',
    openReceivables: '1200.0000',
    netExposure: '600.0000',
  },
  recurringSummary: {
    currency: 'INR',
    upcomingAmount: '649.0000',
    upcomingCount: 1,
    windowStart: '2026-07-24',
    windowEnd: '2026-08-24',
  },
  spendingByCategory: [
    {
      categoryId: 'category-food',
      categoryName: 'Food & dining',
      amount: '5420.0000',
      currency: 'INR',
      sharePercentage: 29,
    },
  ],
  monthlySpending: [
    {
      monthStart: '2026-06-01',
      amount: '20200.0000',
      currency: 'INR',
    },
    {
      monthStart: '2026-07-01',
      amount: '18540.0000',
      currency: 'INR',
    },
  ],
  transactions: {
    edges: [
      {
        cursor: 'cursor-transaction-1',
        node: {
          id: 'transaction-1',
          amount: '420.0000',
          currency: 'INR',
          transactionType: 'EXPENSE',
          description: 'Dinner delivery',
          transactionDate: '2026-07-24T15:01:00Z',
          status: 'POSTED',
          merchantName: 'Swiggy',
          categoryName: 'Food & dining',
        },
      },
    ],
    pageInfo: {
      hasNextPage: false,
      endCursor: 'cursor-transaction-1',
    },
  },
  categories: [
    { id: 'category-food', name: 'Food & dining' },
    { id: 'category-travel', name: 'Travel' },
  ],
  people: [{ id: 'person-1', name: 'Priya' }],
  receivables: [
    {
      id: 'receivable-1',
      personId: 'person-1',
      personName: 'Priya',
      amount: '2000.0000',
      currency: 'INR',
      paidAmount: '800.0000',
      outstandingAmount: '1200.0000',
      description: 'Shared trip',
      issuedDate: '2026-07-01',
      dueDate: '2026-07-31',
      status: 'PARTIALLY_PAID',
    },
  ],
  payables: [
    {
      id: 'payable-1',
      personId: 'person-1',
      personName: 'Priya',
      amount: '600.0000',
      currency: 'INR',
      paidAmount: '0.0000',
      outstandingAmount: '600.0000',
      description: 'Concert tickets',
      issuedDate: '2026-07-10',
      dueDate: null,
      status: 'OPEN',
    },
  ],
  recurringPayments: [
    {
      id: 'recurring-1',
      merchantName: 'Netflix',
      amount: '649.0000',
      currency: 'INR',
      recurrenceRule: 'MONTHLY',
      nextExpectedDate: '2026-07-29',
      status: 'ACTIVE',
    },
  ],
  financialEventProposals: [
    {
      __typename: 'FinancialEventProposalType',
      id: 'proposal-1',
      rawEventId: 'raw-event-1',
      source: 'MANUAL_NOTE',
      eventKind: 'EXPENSE',
      amount: '249.0000',
      currency: 'INR',
      description: 'Music subscription',
      occurredAt: '2026-07-24T10:00:00+05:30',
      dueDate: null,
      merchantName: 'Example Music',
      counterparty: null,
      recurrenceRule: null,
      nextExpectedDate: null,
      categoryHint: 'Entertainment',
      tags: ['subscription', 'music'],
      confidence: '0.9300',
      status: 'NEEDS_REVIEW',
      reviewReasons: ['AI_REVIEW_REQUIRED'],
      provider: 'ollama',
      model: 'gemma4:e4b',
      promptVersion: '1',
      createdAt: '2026-07-24T10:01:00Z',
      canonicalTargetType: null,
      canonicalTargetId: null,
    },
  ],
} satisfies DashboardQueryData;

export const emptyDashboardQueryData = {
  ...dashboardQueryData,
  financialSummary: {
    ...dashboardQueryData.financialSummary,
    spent: '0.0000',
    income: '0.0000',
    transactionCount: 0,
  },
  obligationSummary: {
    ...dashboardQueryData.obligationSummary,
    openPayables: '0.0000',
    openReceivables: '0.0000',
    netExposure: '0.0000',
  },
  recurringSummary: {
    ...dashboardQueryData.recurringSummary,
    upcomingAmount: '0.0000',
    upcomingCount: 0,
  },
  spendingByCategory: [],
  monthlySpending: [],
  transactions: {
    edges: [],
    pageInfo: {
      hasNextPage: false,
      endCursor: null,
    },
  },
  people: [],
  receivables: [],
  payables: [],
  recurringPayments: [],
  financialEventProposals: [],
} satisfies DashboardQueryData;

export const dashboardSuccessMock = {
  request: {
    query: DASHBOARD_QUERY,
  },
  result: {
    data: dashboardQueryData,
  },
};

export const emptyDashboardMock = {
  request: {
    query: DASHBOARD_QUERY,
  },
  result: {
    data: emptyDashboardQueryData,
  },
};
