import { gql } from '@apollo/client';

import type { ClientProblemResult } from './phase1-management';

export const FINANCIAL_PROPOSAL_FIELDS = gql`
  fragment FinancialProposalFields on FinancialEventProposalType {
    __typename
    id
    rawEventId
    source
    eventKind
    amount
    currency
    description
    occurredAt
    dueDate
    merchantName
    counterparty
    recurrenceRule
    nextExpectedDate
    categoryHint
    tags
    confidence
    status
    reviewReasons
    provider
    model
    promptVersion
    createdAt
    canonicalTargetType
    canonicalTargetId
  }
`;

export const SUBMIT_FINANCIAL_NOTE_MUTATION = gql`
  mutation SubmitFinancialNote($input: SubmitFinancialNoteInput!) {
    submitFinancialNote(input: $input) {
      __typename
      ... on SubmitFinancialNoteSuccess {
        proposal {
          ...FinancialProposalFields
        }
      }
      ... on ClientProblem {
        code
        message
        field
      }
    }
  }
  ${FINANCIAL_PROPOSAL_FIELDS}
`;

export const IMPORT_GOOGLE_KEEP_NOTE_MUTATION = gql`
  mutation ImportGoogleKeepNote($input: ImportGoogleKeepNoteInput!) {
    importGoogleKeepNote(input: $input) {
      __typename
      ... on ImportGoogleKeepNoteSuccess {
        ignored
        proposal {
          ...FinancialProposalFields
        }
      }
      ... on ClientProblem {
        code
        message
        field
      }
    }
  }
  ${FINANCIAL_PROPOSAL_FIELDS}
`;

export const APPROVE_FINANCIAL_PROPOSAL_MUTATION = gql`
  mutation ApproveFinancialProposal($id: ID!) {
    approveFinancialProposal(id: $id) {
      __typename
      ... on ReviewFinancialProposalSuccess {
        proposal {
          ...FinancialProposalFields
        }
      }
      ... on ClientProblem {
        code
        message
        field
      }
    }
  }
  ${FINANCIAL_PROPOSAL_FIELDS}
`;

export const REJECT_FINANCIAL_PROPOSAL_MUTATION = gql`
  mutation RejectFinancialProposal($id: ID!) {
    rejectFinancialProposal(id: $id) {
      __typename
      ... on ReviewFinancialProposalSuccess {
        proposal {
          ...FinancialProposalFields
        }
      }
      ... on ClientProblem {
        code
        message
        field
      }
    }
  }
  ${FINANCIAL_PROPOSAL_FIELDS}
`;

export type FinancialEventKind =
  | 'EXPENSE'
  | 'INCOME'
  | 'TRANSFER'
  | 'REFUND'
  | 'SHARED_EXPENSE'
  | 'RECEIVABLE'
  | 'PAYABLE'
  | 'RECURRING'
  | 'UNKNOWN';

export type FinancialProposalSource =
  | 'MANUAL_NOTE'
  | 'CSV_IMPORT'
  | 'MOCK_RECEIPT'
  | 'GMAIL'
  | 'GOOGLE_KEEP_TAKEOUT';

export type FinancialProposalStatus = 'NEEDS_REVIEW' | 'APPROVED' | 'REJECTED';

export interface FinancialEventProposalData {
  readonly __typename: 'FinancialEventProposalType';
  readonly id: string;
  readonly rawEventId: string;
  readonly source: FinancialProposalSource;
  readonly eventKind: FinancialEventKind;
  readonly amount: string | null;
  readonly currency: string | null;
  readonly description: string;
  readonly occurredAt: string | null;
  readonly dueDate: string | null;
  readonly merchantName: string | null;
  readonly counterparty: string | null;
  readonly recurrenceRule: 'WEEKLY' | 'MONTHLY' | 'QUARTERLY' | 'YEARLY' | null;
  readonly nextExpectedDate: string | null;
  readonly categoryHint: string | null;
  readonly tags: readonly string[];
  readonly confidence: string;
  readonly status: FinancialProposalStatus;
  readonly reviewReasons: readonly string[];
  readonly provider: string;
  readonly model: string;
  readonly promptVersion: string;
  readonly createdAt: string;
  readonly canonicalTargetType: string | null;
  readonly canonicalTargetId: string | null;
}

export interface SubmitFinancialNoteMutationVariables {
  readonly input: {
    readonly note: string;
    readonly sourceTimestamp: string;
    readonly clientRequestId: string;
    readonly labels: readonly string[];
  };
}

export interface SubmitFinancialNoteMutationData {
  readonly submitFinancialNote:
    | {
        readonly __typename: 'SubmitFinancialNoteSuccess';
        readonly proposal: FinancialEventProposalData;
      }
    | ClientProblemResult;
}

export interface ImportGoogleKeepNoteMutationVariables {
  readonly input: {
    readonly filename: string;
    readonly content: string;
  };
}

export interface ImportGoogleKeepNoteMutationData {
  readonly importGoogleKeepNote:
    | {
        readonly __typename: 'ImportGoogleKeepNoteSuccess';
        readonly ignored: boolean;
        readonly proposal: FinancialEventProposalData | null;
      }
    | ClientProblemResult;
}

export interface ReviewFinancialProposalMutationVariables {
  readonly id: string;
}

export interface ApproveFinancialProposalMutationData {
  readonly approveFinancialProposal:
    | {
        readonly __typename: 'ReviewFinancialProposalSuccess';
        readonly proposal: FinancialEventProposalData;
      }
    | ClientProblemResult;
}

export interface RejectFinancialProposalMutationData {
  readonly rejectFinancialProposal:
    | {
        readonly __typename: 'ReviewFinancialProposalSuccess';
        readonly proposal: FinancialEventProposalData;
      }
    | ClientProblemResult;
}
