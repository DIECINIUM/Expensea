import { MockedProvider } from '@apollo/client/testing/react';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { DashboardPage } from './DashboardPage';
import { CREATE_TRANSACTION_MUTATION } from '../../graphql/create-transaction';
import { DASHBOARD_QUERY } from '../../graphql/dashboard';
import {
  dashboardQueryData,
  dashboardSuccessMock,
  emptyDashboardMock,
} from '../../test/dashboard-fixtures';

describe('DashboardPage', () => {
  it('announces loading without displaying placeholder financial values', () => {
    render(
      <MockedProvider mocks={[{ ...dashboardSuccessMock, delay: 1_000 }]}>
        <DashboardPage />
      </MockedProvider>,
    );

    expect(
      screen.getByRole('status', { name: /loading financial dashboard/i }),
    ).toHaveAttribute('aria-busy', 'true');
    expect(screen.queryByText('₹18,540')).not.toBeInTheDocument();
  });

  it('renders exact ledger values and API-provided transaction data', async () => {
    render(
      <MockedProvider mocks={[dashboardSuccessMock]}>
        <DashboardPage />
      </MockedProvider>,
    );

    expect(
      await screen.findByRole('heading', {
        name: /good morning, mohd salik/i,
      }),
    ).toBeInTheDocument();
    expect(screen.getAllByText('₹18,540')).toHaveLength(2);
    expect(screen.getAllByText('₹1,200')).toHaveLength(2);
    expect(screen.getAllByText('₹600')).toHaveLength(2);
    expect(screen.getByText('₹649')).toBeInTheDocument();
    expect(
      within(
        screen.getByRole('list', { name: /recurring payments/i }),
      ).getByText(/₹649/),
    ).toBeInTheDocument();
    expect(screen.getByText('29%')).toBeInTheDocument();
    expect(screen.getByRole('row', { name: /swiggy/i })).toHaveTextContent(
      '−₹420',
    );
    expect(
      screen.getByRole('heading', { name: /add transaction/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: /^people$/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: /money owed/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: /recurring payments/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: /financial notes inbox/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('list', { name: /financial proposals/i }),
    ).toHaveTextContent('Music subscription');
    expect(
      screen.getByRole('button', { name: /approve music subscription/i }),
    ).toBeEnabled();
    expect(screen.queryByText(/synthetic/i)).not.toBeInTheDocument();
  });

  it('shows an honest empty ledger alongside manual entry', async () => {
    render(
      <MockedProvider mocks={[emptyDashboardMock]}>
        <DashboardPage />
      </MockedProvider>,
    );

    expect(
      await screen.findByRole('heading', { name: /no ledger activity yet/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/api returned no financial records/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /save transaction/i }),
    ).toBeEnabled();
    expect(screen.getByRole('button', { name: /add person/i })).toBeEnabled();
    expect(
      screen.getByRole('button', { name: /add receivable/i }),
    ).toBeDisabled();
    expect(screen.queryByText('₹18,540')).not.toBeInTheDocument();
  });

  it('hides financial values on failure and retries the same query', async () => {
    const user = userEvent.setup();
    render(
      <MockedProvider
        mocks={[
          {
            request: { query: DASHBOARD_QUERY },
            error: new Error('Ledger unavailable'),
          },
          dashboardSuccessMock,
        ]}
      >
        <DashboardPage />
      </MockedProvider>,
    );

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /financial dashboard unavailable/i,
    );
    expect(screen.queryByText('₹18,540')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /retry dashboard/i }));
    expect(
      await screen.findByRole('heading', {
        name: /good morning, mohd salik/i,
      }),
    ).toBeInTheDocument();
  });

  it('refreshes live totals after a successful manual transaction', async () => {
    const user = userEvent.setup();
    const refreshedData = {
      ...dashboardQueryData,
      financialSummary: {
        ...dashboardQueryData.financialSummary,
        spent: '18960.1250',
        transactionCount: 33,
      },
      monthlySpending: [
        dashboardQueryData.monthlySpending[0]!,
        {
          ...dashboardQueryData.monthlySpending[1]!,
          amount: '18960.1250',
        },
      ],
    };
    const mutationMock = {
      request: {
        query: CREATE_TRANSACTION_MUTATION,
        variables: (variables: Record<string, unknown>) => {
          const input = variables.input as Record<string, unknown> | undefined;
          return (
            input?.amount === '420.1250' &&
            input.currency === 'INR' &&
            input.transactionType === 'EXPENSE' &&
            input.description === 'Dinner delivery' &&
            typeof input.transactionDate === 'string' &&
            input.categoryId === 'category-food'
          );
        },
      },
      result: {
        data: {
          createTransaction: {
            __typename: 'CreateTransactionSuccess',
            transaction: {
              id: 'transaction-new',
              amount: '420.1250',
              currency: 'INR',
              transactionType: 'EXPENSE',
              description: 'Dinner delivery',
              transactionDate: '2026-07-24T15:01:00Z',
              status: 'POSTED',
              merchantName: null,
              categoryName: 'Food & dining',
            },
          },
        },
      },
    };

    render(
      <MockedProvider
        mocks={[
          dashboardSuccessMock,
          mutationMock,
          {
            request: { query: DASHBOARD_QUERY },
            result: { data: refreshedData },
          },
        ]}
      >
        <DashboardPage />
      </MockedProvider>,
    );

    await screen.findByRole('heading', {
      name: /good morning, mohd salik/i,
    });
    await user.type(
      screen.getByLabelText(/^amount$/i, {
        selector: '#transaction-amount',
      }),
      '420.1250',
    );
    await user.type(
      screen.getByLabelText(/^description$/i, {
        selector: '#transaction-description',
      }),
      'Dinner delivery',
    );
    await user.selectOptions(
      screen.getByLabelText(/category/i),
      'category-food',
    );
    await user.click(screen.getByRole('button', { name: /save transaction/i }));

    expect(
      await screen.findByText(/saved and dashboard totals refreshed/i),
    ).toBeInTheDocument();
    expect(screen.getAllByText('₹18,960.125')).toHaveLength(2);
    expect(screen.getByText(/33 posted transactions/i)).toBeInTheDocument();
  });
});
