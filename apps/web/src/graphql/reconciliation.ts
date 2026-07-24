import { gql } from '@apollo/client';

import type { ClientProblemResult } from './phase1-management';

export const RECONCILIATION_CASE_FIELDS = gql`
  fragment ReconciliationCaseFields on ReconciliationCaseType {
    __typename
    id
    normalizedEventId
    source
    eventKind
    amount
    currency
    description
    occurredAt
    merchantName
    candidateTransactionId
    candidateDescription
    candidateOccurredAt
    candidateMerchantName
    resultingTransactionId
    initialDecision
    status
    score
    scoreVersion
    reasons
    createdAt
    updatedAt
    canUnmerge
    actions {
      id
      actionType
      fromTransactionId
      toTransactionId
      score
      reasons
      createdAt
    }
  }
`;

export const MERGE_RECONCILIATION_CASE_MUTATION = gql`
  mutation MergeReconciliationCase($id: ID!) {
    mergeReconciliationCase(id: $id) {
      __typename
      ... on ReviewReconciliationCaseSuccess {
        case {
          ...ReconciliationCaseFields
        }
      }
      ... on ClientProblem {
        code
        message
        field
      }
    }
  }
  ${RECONCILIATION_CASE_FIELDS}
`;

export const KEEP_RECONCILIATION_CASE_SEPARATE_MUTATION = gql`
  mutation KeepReconciliationCaseSeparate($id: ID!) {
    keepReconciliationCaseSeparate(id: $id) {
      __typename
      ... on ReviewReconciliationCaseSuccess {
        case {
          ...ReconciliationCaseFields
        }
      }
      ... on ClientProblem {
        code
        message
        field
      }
    }
  }
  ${RECONCILIATION_CASE_FIELDS}
`;

export const UNMERGE_RECONCILIATION_CASE_MUTATION = gql`
  mutation UnmergeReconciliationCase($id: ID!) {
    unmergeReconciliationCase(id: $id) {
      __typename
      ... on ReviewReconciliationCaseSuccess {
        case {
          ...ReconciliationCaseFields
        }
      }
      ... on ClientProblem {
        code
        message
        field
      }
    }
  }
  ${RECONCILIATION_CASE_FIELDS}
`;

export type ReconciliationSource =
  | 'MANUAL_NOTE'
  | 'CSV_IMPORT'
  | 'MOCK_RECEIPT'
  | 'GMAIL'
  | 'GOOGLE_KEEP_TAKEOUT';

export type ReconciliationStatus =
  'PENDING' | 'MERGED' | 'KEPT_SEPARATE' | 'UNMERGED';

export type ReconciliationDecision =
  'MERGE' | 'POSSIBLE_DUPLICATE' | 'NEW_TRANSACTION';

export type ReconciliationAction =
  | 'CANDIDATE_FLAGGED'
  | 'AUTO_MERGED'
  | 'CREATED_NEW'
  | 'USER_MERGED'
  | 'USER_KEPT_SEPARATE'
  | 'USER_UNMERGED';

export interface ReconciliationActionData {
  readonly id: string;
  readonly actionType: ReconciliationAction;
  readonly fromTransactionId: string | null;
  readonly toTransactionId: string | null;
  readonly score: string;
  readonly reasons: readonly string[];
  readonly createdAt: string;
}

export interface ReconciliationCaseData {
  readonly __typename: 'ReconciliationCaseType';
  readonly id: string;
  readonly normalizedEventId: string;
  readonly source: ReconciliationSource;
  readonly eventKind:
    'EXPENSE' | 'INCOME' | 'TRANSFER' | 'REFUND' | 'SHARED_EXPENSE';
  readonly amount: string;
  readonly currency: string;
  readonly description: string;
  readonly occurredAt: string;
  readonly merchantName: string | null;
  readonly candidateTransactionId: string | null;
  readonly candidateDescription: string | null;
  readonly candidateOccurredAt: string | null;
  readonly candidateMerchantName: string | null;
  readonly resultingTransactionId: string | null;
  readonly initialDecision: ReconciliationDecision;
  readonly status: ReconciliationStatus;
  readonly score: string;
  readonly scoreVersion: string;
  readonly reasons: readonly string[];
  readonly createdAt: string;
  readonly updatedAt: string;
  readonly canUnmerge: boolean;
  readonly actions: readonly ReconciliationActionData[];
}

export interface ReviewReconciliationCaseMutationVariables {
  readonly id: string;
}

interface ReviewReconciliationCaseSuccess {
  readonly __typename: 'ReviewReconciliationCaseSuccess';
  readonly case: ReconciliationCaseData;
}

export type ReviewReconciliationCaseResult =
  ReviewReconciliationCaseSuccess | ClientProblemResult;

export interface MergeReconciliationCaseMutationData {
  readonly mergeReconciliationCase: ReviewReconciliationCaseResult;
}

export interface KeepReconciliationCaseSeparateMutationData {
  readonly keepReconciliationCaseSeparate: ReviewReconciliationCaseResult;
}

export interface UnmergeReconciliationCaseMutationData {
  readonly unmergeReconciliationCase: ReviewReconciliationCaseResult;
}
