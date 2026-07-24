import { MockedProvider } from '@apollo/client/testing/react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ManualTransactionForm } from './ManualTransactionForm';
import { CREATE_TRANSACTION_MUTATION } from '../../graphql/create-transaction';

const categories = [{ id: 'category-food', name: 'Food & dining' }] as const;

function transactionDateFromForm(): string {
  const input = screen.getByLabelText<HTMLInputElement>(/date and time/i);
  return new Date(input.value).toISOString();
}

describe('ManualTransactionForm', () => {
  it('rejects zero and malformed monetary input before mutation', async () => {
    const user = userEvent.setup();
    render(
      <MockedProvider>
        <ManualTransactionForm
          categories={categories}
          defaultCurrency="INR"
          onCreated={vi.fn()}
        />
      </MockedProvider>,
    );

    await user.type(screen.getByLabelText(/amount/i), '0.0000');
    await user.type(screen.getByLabelText(/description/i), 'Dinner');
    await user.click(screen.getByRole('button', { name: /save transaction/i }));

    expect(
      await screen.findByText(/amount must be greater than zero/i),
    ).toBeInTheDocument();
  });

  it('preserves the decimal string and refreshes after a successful mutation', async () => {
    const user = userEvent.setup();
    const onCreated = vi.fn().mockResolvedValue(undefined);
    const initialTransactionDate = '2026-07-24T20:31';
    const transactionDate = new Date(initialTransactionDate).toISOString();
    const mutationMock = {
      request: {
        query: CREATE_TRANSACTION_MUTATION,
        variables: {
          input: {
            amount: '420.1250',
            currency: 'INR',
            transactionType: 'EXPENSE',
            description: 'Dinner delivery',
            transactionDate,
            categoryId: 'category-food',
          },
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
              transactionDate,
              status: 'POSTED',
              merchantName: null,
              categoryName: 'Food & dining',
            },
          },
        },
      },
    };

    render(
      <MockedProvider mocks={[mutationMock]}>
        <ManualTransactionForm
          categories={categories}
          defaultCurrency="INR"
          initialTransactionDate={initialTransactionDate}
          onCreated={onCreated}
        />
      </MockedProvider>,
    );

    await user.type(screen.getByLabelText(/amount/i), '420.1250');
    await user.type(screen.getByLabelText(/description/i), 'Dinner delivery');
    await user.selectOptions(
      screen.getByLabelText(/category/i),
      'category-food',
    );

    expect(transactionDateFromForm()).toBe(transactionDate);
    await user.click(screen.getByRole('button', { name: /save transaction/i }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      /saved and dashboard totals refreshed/i,
    );
    expect(onCreated).toHaveBeenCalledOnce();
    expect(screen.getByLabelText(/amount/i)).toHaveValue('');
  });

  it('maps a typed validation problem back to its form field', async () => {
    const user = userEvent.setup();
    const onCreated = vi.fn();
    const initialTransactionDate = '2026-07-24T20:31';
    const transactionDate = new Date(initialTransactionDate).toISOString();
    const validationMock = {
      request: {
        query: CREATE_TRANSACTION_MUTATION,
        variables: {
          input: {
            amount: '420.0000',
            currency: 'INR',
            transactionType: 'EXPENSE',
            description: 'Dinner delivery',
            transactionDate,
            categoryId: null,
          },
        },
      },
      result: {
        data: {
          createTransaction: {
            __typename: 'ValidationProblem',
            code: 'INVALID_AMOUNT',
            message: 'Amount conflicts with the ledger policy.',
            field: 'amount',
          },
        },
      },
    };

    render(
      <MockedProvider mocks={[validationMock]}>
        <ManualTransactionForm
          categories={categories}
          defaultCurrency="INR"
          initialTransactionDate={initialTransactionDate}
          onCreated={onCreated}
        />
      </MockedProvider>,
    );

    await user.type(screen.getByLabelText(/amount/i), '420.0000');
    await user.type(screen.getByLabelText(/description/i), 'Dinner delivery');
    await user.click(screen.getByRole('button', { name: /save transaction/i }));

    expect(
      await screen.findByText(/amount conflicts with the ledger policy/i),
    ).toBeInTheDocument();
    expect(onCreated).not.toHaveBeenCalled();
  });
});
