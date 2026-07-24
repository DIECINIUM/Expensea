import { MockedProvider } from '@apollo/client/testing/react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { FinancialNotesPanel } from './FinancialNotesPanel';
import {
  APPROVE_FINANCIAL_PROPOSAL_MUTATION,
  SUBMIT_FINANCIAL_NOTE_MUTATION,
  type FinancialEventProposalData,
} from '../../graphql/financial-proposals';
import { dashboardQueryData } from '../../test/dashboard-fixtures';

const existingProposal = dashboardQueryData.financialEventProposals[0]!;

function extractedProposal(): FinancialEventProposalData {
  return {
    ...existingProposal,
    id: 'proposal-new',
    rawEventId: 'raw-event-new',
    description: 'Airport cab',
    amount: '450.0000',
    merchantName: 'Example Cabs',
    tags: ['Travel'],
  };
}

describe('FinancialNotesPanel', () => {
  it('approves a proposal and refreshes deterministic ledger data', async () => {
    const user = userEvent.setup();
    const onChanged = vi.fn().mockResolvedValue(undefined);
    const approved = {
      ...existingProposal,
      status: 'APPROVED' as const,
      canonicalTargetType: 'transaction',
      canonicalTargetId: 'transaction-approved',
    };

    render(
      <MockedProvider
        mocks={[
          {
            request: {
              query: APPROVE_FINANCIAL_PROPOSAL_MUTATION,
              variables: { id: existingProposal.id },
            },
            result: {
              data: {
                approveFinancialProposal: {
                  __typename: 'ReviewFinancialProposalSuccess',
                  proposal: approved,
                },
              },
            },
          },
        ]}
      >
        <FinancialNotesPanel
          proposals={[existingProposal]}
          onChanged={onChanged}
        />
      </MockedProvider>,
    );

    await user.click(
      screen.getByRole('button', {
        name: /approve music subscription/i,
      }),
    );

    expect(
      await screen.findByText(/approved and ledger data refreshed/i),
    ).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalledOnce();
  });

  it('extracts an informal note into the review queue', async () => {
    const user = userEvent.setup();
    const onChanged = vi.fn().mockResolvedValue(undefined);
    const proposal = extractedProposal();

    render(
      <MockedProvider
        mocks={[
          {
            request: {
              query: SUBMIT_FINANCIAL_NOTE_MUTATION,
              variables: (variables: Record<string, unknown>) => {
                const input = variables.input as
                  Record<string, unknown> | undefined;
                return (
                  input?.note === 'Paid ₹450 for an airport cab today' &&
                  Array.isArray(input.labels) &&
                  input.labels.join(',') === 'Travel,Work' &&
                  typeof input.sourceTimestamp === 'string' &&
                  typeof input.clientRequestId === 'string'
                );
              },
            },
            result: {
              data: {
                submitFinancialNote: {
                  __typename: 'SubmitFinancialNoteSuccess',
                  proposal,
                },
              },
            },
          },
        ]}
      >
        <FinancialNotesPanel proposals={[]} onChanged={onChanged} />
      </MockedProvider>,
    );

    await user.type(
      screen.getByLabelText(/informal expense or money note/i),
      'Paid ₹450 for an airport cab today',
    );
    await user.type(screen.getByLabelText(/^labels/i), 'Travel, travel, Work');
    await user.click(
      screen.getByRole('button', { name: /create review proposal/i }),
    );

    expect(
      await screen.findByText(/note extracted into a proposal/i),
    ).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalledOnce();
  });
});
