import { gql } from '@apollo/client';

export const CORRECT_TRANSACTION_CATEGORY_MUTATION = gql`
  mutation CorrectTransactionCategory(
    $input: CorrectTransactionCategoryInput!
  ) {
    correctTransactionCategory(input: $input) {
      __typename
      ... on CorrectTransactionCategorySuccess {
        correction {
          id
          correctedCategoryName
        }
      }
      ... on ClientProblem {
        code
        message
        field
      }
    }
  }
`;

export interface CorrectCategoryMutationData {
  readonly correctTransactionCategory:
    | {
        readonly __typename: 'CorrectTransactionCategorySuccess';
        readonly correction: {
          readonly id: string;
          readonly correctedCategoryName: string;
        };
      }
    | {
        readonly __typename: 'ValidationProblem' | 'NotFoundProblem';
        readonly code: string;
        readonly message: string;
        readonly field: string | null;
      };
}

export interface CorrectCategoryMutationVariables {
  readonly input: {
    readonly transactionId: string;
    readonly categoryId: string;
  };
}
