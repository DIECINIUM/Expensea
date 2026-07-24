import { gql } from '@apollo/client';

import type { DashboardTransactionNode } from './dashboard';
import type { DashboardTransactionType } from '../components/dashboard/types';

export const CREATE_TRANSACTION_MUTATION = gql`
  mutation CreateTransaction($input: CreateTransactionInput!) {
    createTransaction(input: $input) {
      __typename
      ... on CreateTransactionSuccess {
        transaction {
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
      ... on ValidationProblem {
        code
        message
        field
      }
      ... on NotFoundProblem {
        code
        message
        field
      }
      ... on ConflictProblem {
        code
        message
        field
      }
    }
  }
`;

export interface CreateTransactionInput {
  readonly amount: string;
  readonly currency: string;
  readonly transactionType: DashboardTransactionType;
  readonly description: string;
  readonly transactionDate: string;
  readonly categoryId: string | null;
}

export interface CreateTransactionSuccess {
  readonly __typename: 'CreateTransactionSuccess';
  readonly transaction: DashboardTransactionNode;
}

export interface CreateTransactionProblem {
  readonly __typename:
    'ValidationProblem' | 'NotFoundProblem' | 'ConflictProblem';
  readonly code: string;
  readonly message: string;
  readonly field: string | null;
}

export interface CreateTransactionMutationData {
  readonly createTransaction:
    CreateTransactionSuccess | CreateTransactionProblem;
}

export interface CreateTransactionMutationVariables {
  readonly input: CreateTransactionInput;
}
