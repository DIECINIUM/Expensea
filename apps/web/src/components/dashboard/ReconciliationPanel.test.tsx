import { MockedProvider } from '@apollo/client/testing/react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ReconciliationPanel } from './ReconciliationPanel';
import {
  MERGE_RECONCILIATION_CASE_MUTATION,
  UNMERGE_RECONCILIATION_CASE_MUTATION,
  type ReconciliationCaseData,
} from '../../graphql/reconciliation';
import { dashboardQueryData } from '../../test/dashboard-fixtures';

const pendingCase = dashboardQueryData.reconciliationCases[0]!;

describe('ReconciliationPanel', () => {
  it('merges an ambiguous source and refreshes the ledger', async () => {
    const user = userEvent.setup();
    const onChanged = vi.fn().mockResolvedValue(undefined);
    const mergedCase: ReconciliationCaseData = {
      ...pendingCase,
      status: 'MERGED',
      resultingTransactionId: pendingCase.candidateTransactionId,
      canUnmerge: true,
      actions: [
        ...pendingCase.actions,
        {
          id: 'reconciliation-action-merge',
          actionType: 'USER_MERGED',
          fromTransactionId: null,
          toTransactionId: pendingCase.candidateTransactionId,
          score: pendingCase.score,
          reasons: pendingCase.reasons,
          createdAt: '2026-07-24T15:04:00Z',
        },
      ],
    };

    render(
      <MockedProvider
        mocks={[
          {
            request: {
              query: MERGE_RECONCILIATION_CASE_MUTATION,
              variables: { id: pendingCase.id },
            },
            result: {
              data: {
                mergeReconciliationCase: {
                  __typename: 'ReviewReconciliationCaseSuccess',
                  case: mergedCase,
                },
              },
            },
          },
        ]}
      >
        <ReconciliationPanel cases={[pendingCase]} onChanged={onChanged} />
      </MockedProvider>,
    );

    await user.click(
      screen.getByRole('button', { name: /merge card purchase/i }),
    );

    expect(
      await screen.findByText(/sources merged into one ledger transaction/i),
    ).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalledOnce();
  });

  it('allows a merged source to be restored without deleting evidence', async () => {
    const user = userEvent.setup();
    const onChanged = vi.fn().mockResolvedValue(undefined);
    const mergedCase: ReconciliationCaseData = {
      ...pendingCase,
      status: 'MERGED',
      resultingTransactionId: pendingCase.candidateTransactionId,
      canUnmerge: true,
    };
    const unmergedCase: ReconciliationCaseData = {
      ...mergedCase,
      status: 'UNMERGED',
      resultingTransactionId: 'transaction-restored',
      canUnmerge: false,
      actions: [
        ...mergedCase.actions,
        {
          id: 'reconciliation-action-unmerge',
          actionType: 'USER_UNMERGED',
          fromTransactionId: pendingCase.candidateTransactionId,
          toTransactionId: 'transaction-restored',
          score: pendingCase.score,
          reasons: pendingCase.reasons,
          createdAt: '2026-07-24T15:05:00Z',
        },
      ],
    };

    render(
      <MockedProvider
        mocks={[
          {
            request: {
              query: UNMERGE_RECONCILIATION_CASE_MUTATION,
              variables: { id: pendingCase.id },
            },
            result: {
              data: {
                unmergeReconciliationCase: {
                  __typename: 'ReviewReconciliationCaseSuccess',
                  case: unmergedCase,
                },
              },
            },
          },
        ]}
      >
        <ReconciliationPanel cases={[mergedCase]} onChanged={onChanged} />
      </MockedProvider>,
    );

    await user.click(
      screen.getByRole('button', { name: /undo merge for card purchase/i }),
    );

    expect(
      await screen.findByText(/restored as a separate transaction/i),
    ).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalledOnce();
  });
});
