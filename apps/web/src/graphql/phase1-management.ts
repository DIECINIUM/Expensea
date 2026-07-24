import { gql } from '@apollo/client';

import type { RecurrenceRule, RecurringPaymentStatus } from './dashboard';

const CLIENT_PROBLEM_FIELDS = gql`
  fragment ClientProblemFields on ClientProblem {
    code
    message
    field
  }
`;

export const CREATE_PERSON_MUTATION = gql`
  mutation CreatePerson($input: CreatePersonInput!) {
    createPerson(input: $input) {
      __typename
      ...ClientProblemFields
    }
  }
  ${CLIENT_PROBLEM_FIELDS}
`;

export const CREATE_RECEIVABLE_MUTATION = gql`
  mutation CreateReceivable($input: CreateReceivableInput!) {
    createReceivable(input: $input) {
      __typename
      ...ClientProblemFields
    }
  }
  ${CLIENT_PROBLEM_FIELDS}
`;

export const CREATE_PAYABLE_MUTATION = gql`
  mutation CreatePayable($input: CreatePayableInput!) {
    createPayable(input: $input) {
      __typename
      ...ClientProblemFields
    }
  }
  ${CLIENT_PROBLEM_FIELDS}
`;

export const SETTLE_RECEIVABLE_MUTATION = gql`
  mutation SettleReceivable($input: SettleReceivableInput!) {
    settleReceivable(input: $input) {
      __typename
      ...ClientProblemFields
    }
  }
  ${CLIENT_PROBLEM_FIELDS}
`;

export const SETTLE_PAYABLE_MUTATION = gql`
  mutation SettlePayable($input: SettlePayableInput!) {
    settlePayable(input: $input) {
      __typename
      ...ClientProblemFields
    }
  }
  ${CLIENT_PROBLEM_FIELDS}
`;

export const CREATE_RECURRING_PAYMENT_MUTATION = gql`
  mutation CreateRecurringPayment($input: CreateRecurringPaymentInput!) {
    createRecurringPayment(input: $input) {
      __typename
      ...ClientProblemFields
    }
  }
  ${CLIENT_PROBLEM_FIELDS}
`;

export const SET_RECURRING_PAYMENT_STATUS_MUTATION = gql`
  mutation SetRecurringPaymentStatus(
    $id: ID!
    $status: RecurringPaymentStatusValue!
  ) {
    setRecurringPaymentStatus(id: $id, status: $status) {
      __typename
      ...ClientProblemFields
    }
  }
  ${CLIENT_PROBLEM_FIELDS}
`;

export const RECORD_RECURRING_PAYMENT_MUTATION = gql`
  mutation RecordRecurringPayment(
    $id: ID!
    $expectedDate: Date!
    $transactionDate: DateTime!
  ) {
    recordRecurringPayment(
      id: $id
      expectedDate: $expectedDate
      transactionDate: $transactionDate
    ) {
      __typename
      ...ClientProblemFields
    }
  }
  ${CLIENT_PROBLEM_FIELDS}
`;

export interface ClientProblemResult {
  readonly __typename:
    'ValidationProblem' | 'NotFoundProblem' | 'ConflictProblem';
  readonly code: string;
  readonly message: string;
  readonly field: string | null;
}

export type MutationResult<SuccessName extends string> =
  { readonly __typename: SuccessName } | ClientProblemResult;

export interface CreatePersonInput {
  readonly name: string;
}

export interface CreatePersonMutationData {
  readonly createPerson: MutationResult<'CreatePersonSuccess'>;
}

export interface CreatePersonMutationVariables {
  readonly input: CreatePersonInput;
}

export interface CreateObligationInput {
  readonly personId: string;
  readonly amount: string;
  readonly currency: string;
  readonly description: string;
  readonly issuedDate: string;
  readonly dueDate: string | null;
}

export interface CreateReceivableMutationData {
  readonly createReceivable: MutationResult<'CreateReceivableSuccess'>;
}

export interface CreatePayableMutationData {
  readonly createPayable: MutationResult<'CreatePayableSuccess'>;
}

export interface CreateObligationMutationVariables {
  readonly input: CreateObligationInput;
}

export interface SettleObligationInput {
  readonly obligationId: string;
  readonly amount: string;
  readonly settledAt: string;
  readonly note: string | null;
}

export interface SettleReceivableMutationData {
  readonly settleReceivable: MutationResult<'SettleReceivableSuccess'>;
}

export interface SettlePayableMutationData {
  readonly settlePayable: MutationResult<'SettlePayableSuccess'>;
}

export interface SettleObligationMutationVariables {
  readonly input: SettleObligationInput;
}

export interface CreateRecurringPaymentInput {
  readonly merchantName: string;
  readonly amount: string;
  readonly currency: string;
  readonly recurrenceRule: RecurrenceRule;
  readonly nextExpectedDate: string;
}

export interface CreateRecurringPaymentMutationData {
  readonly createRecurringPayment: MutationResult<'CreateRecurringPaymentSuccess'>;
}

export interface CreateRecurringPaymentMutationVariables {
  readonly input: CreateRecurringPaymentInput;
}

export interface SetRecurringPaymentStatusMutationData {
  readonly setRecurringPaymentStatus: MutationResult<'SetRecurringPaymentStatusSuccess'>;
}

export interface SetRecurringPaymentStatusMutationVariables {
  readonly id: string;
  readonly status: RecurringPaymentStatus;
}

export interface RecordRecurringPaymentMutationData {
  readonly recordRecurringPayment: MutationResult<'RecordRecurringPaymentSuccess'>;
}

export interface RecordRecurringPaymentMutationVariables {
  readonly id: string;
  readonly expectedDate: string;
  readonly transactionDate: string;
}
