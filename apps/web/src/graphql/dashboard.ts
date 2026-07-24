import { gql } from '@apollo/client';

import type {
  DashboardTransactionStatus,
  DashboardTransactionType,
} from '../components/dashboard/types';
import {
  FINANCIAL_PROPOSAL_FIELDS,
  type FinancialEventProposalData,
} from './financial-proposals';

export const DASHBOARD_QUERY = gql`
  query PhaseOneDashboard {
    me {
      id
      name
      defaultCurrency
      timezone
    }
    financialSummary {
      currency
      periodStart
      periodEnd
      spent
      income
      transactionCount
    }
    obligationSummary {
      currency
      openPayables
      openReceivables
      netExposure
    }
    recurringSummary {
      currency
      upcomingAmount
      upcomingCount
      windowStart
      windowEnd
    }
    spendingByCategory {
      categoryId
      categoryName
      amount
      currency
      sharePercentage
    }
    monthlySpending(months: 6) {
      monthStart
      amount
      currency
    }
    transactions(first: 10) {
      edges {
        cursor
        node {
          id
          amount
          currency
          transactionType
          description
          transactionDate
          status
          merchantName
          categoryName
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
    categories {
      id
      name
    }
    people {
      id
      name
    }
    receivables {
      id
      personId
      personName
      amount
      currency
      paidAmount
      outstandingAmount
      description
      issuedDate
      dueDate
      status
    }
    payables {
      id
      personId
      personName
      amount
      currency
      paidAmount
      outstandingAmount
      description
      issuedDate
      dueDate
      status
    }
    recurringPayments {
      id
      merchantName
      amount
      currency
      recurrenceRule
      nextExpectedDate
      status
    }
    financialEventProposals {
      ...FinancialProposalFields
    }
  }
  ${FINANCIAL_PROPOSAL_FIELDS}
`;

export interface DashboardUserData {
  readonly id: string;
  readonly name: string;
  readonly defaultCurrency: string;
  readonly timezone: string;
}

export interface FinancialSummaryData {
  readonly currency: string;
  readonly periodStart: string;
  readonly periodEnd: string;
  readonly spent: string;
  readonly income: string;
  readonly transactionCount: number;
}

export interface ObligationSummaryData {
  readonly currency: string;
  readonly openPayables: string;
  readonly openReceivables: string;
  readonly netExposure: string;
}

export interface RecurringSummaryData {
  readonly currency: string;
  readonly upcomingAmount: string;
  readonly upcomingCount: number;
  readonly windowStart: string;
  readonly windowEnd: string;
}

export interface SpendingByCategoryData {
  readonly categoryId: string | null;
  readonly categoryName: string | null;
  readonly amount: string;
  readonly currency: string;
  readonly sharePercentage: number;
}

export interface MonthlySpendingData {
  readonly monthStart: string;
  readonly amount: string;
  readonly currency: string;
}

export interface DashboardTransactionNode {
  readonly id: string;
  readonly amount: string;
  readonly currency: string;
  readonly transactionType: DashboardTransactionType;
  readonly description: string;
  readonly transactionDate: string;
  readonly status: DashboardTransactionStatus;
  readonly merchantName: string | null;
  readonly categoryName: string | null;
}

export interface TransactionEdgeData {
  readonly cursor: string;
  readonly node: DashboardTransactionNode;
}

export interface TransactionConnectionData {
  readonly edges: readonly TransactionEdgeData[];
  readonly pageInfo: {
    readonly hasNextPage: boolean;
    readonly endCursor: string | null;
  };
}

export interface DashboardCategoryData {
  readonly id: string;
  readonly name: string;
}

export interface PersonData {
  readonly id: string;
  readonly name: string;
}

export type ObligationStatus =
  'OPEN' | 'PARTIALLY_PAID' | 'PAID' | 'OVERDUE' | 'CANCELLED';

export interface ObligationData {
  readonly id: string;
  readonly personId: string;
  readonly personName: string;
  readonly amount: string;
  readonly currency: string;
  readonly paidAmount: string;
  readonly outstandingAmount: string;
  readonly description: string;
  readonly issuedDate: string;
  readonly dueDate: string | null;
  readonly status: ObligationStatus;
}

export type RecurrenceRule = 'WEEKLY' | 'MONTHLY' | 'QUARTERLY' | 'YEARLY';

export type RecurringPaymentStatus =
  'ACTIVE' | 'PAUSED' | 'ENDED' | 'NEEDS_REVIEW';

export interface RecurringPaymentData {
  readonly id: string;
  readonly merchantName: string;
  readonly amount: string;
  readonly currency: string;
  readonly recurrenceRule: RecurrenceRule;
  readonly nextExpectedDate: string;
  readonly status: RecurringPaymentStatus;
}

export interface DashboardQueryData {
  readonly me: DashboardUserData;
  readonly financialSummary: FinancialSummaryData;
  readonly obligationSummary: ObligationSummaryData;
  readonly recurringSummary: RecurringSummaryData;
  readonly spendingByCategory: readonly SpendingByCategoryData[];
  readonly monthlySpending: readonly MonthlySpendingData[];
  readonly transactions: TransactionConnectionData;
  readonly categories: readonly DashboardCategoryData[];
  readonly people: readonly PersonData[];
  readonly receivables: readonly ObligationData[];
  readonly payables: readonly ObligationData[];
  readonly recurringPayments: readonly RecurringPaymentData[];
  readonly financialEventProposals: readonly FinancialEventProposalData[];
}
