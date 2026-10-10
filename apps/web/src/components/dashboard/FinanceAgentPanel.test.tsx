import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { FinanceAgentPanel } from './FinanceAgentPanel';
import {
  askFinanceAgent,
  type FinanceAgentResult,
} from '../../lib/finance-agent-client';

vi.mock('../../lib/finance-agent-client', () => ({ askFinanceAgent: vi.fn() }));
const ask = vi.mocked(askFinanceAgent);

const answer: FinanceAgentResult = {
  status: 'answered',
  mode: 'deterministic',
  tool: 'get_transactions',
  answer: 'expense 2026-07-24 (posted): INR 120.1234',
  facts: [
    {
      label: 'expense 2026-07-24 (posted)',
      value: '120.1234',
      currency: 'INR',
      record_id: '30000000-0000-4000-8000-000000000001',
      record_kind: 'transaction',
    },
  ],
  period_start: null,
  period_end: null,
  period_end_inclusive: false,
  previous_period_start: null,
  previous_period_end: null,
  truncated: false,
  limitations: ['Read-only. No currency conversion.'],
};

afterEach(() => vi.resetAllMocks());

async function question(text = 'Show recent transactions') {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('Finance question'), text);
  await user.click(screen.getByRole('button', { name: 'Ask ledger' }));
  return user;
}

describe('FinanceAgentPanel', () => {
  it('shows exact grounded facts and owner-local record IDs without floating point conversion', async () => {
    ask.mockResolvedValue(answer);
    render(<FinanceAgentPanel />);
    await question();
    expect(await screen.findByText(answer.answer)).toBeInTheDocument();
    expect(
      screen.getByText('30000000-0000-4000-8000-000000000001'),
    ).toBeInTheDocument();
    expect(ask).toHaveBeenCalledWith(
      { question: 'Show recent transactions' },
      expect.any(AbortSignal),
    );
  });

  it('explicitly labels unavailable-provider deterministic fallback and interpretation failure', async () => {
    ask.mockResolvedValue({
      ...answer,
      status: 'unsupported',
      mode: 'deterministic_provider_unavailable',
      tool: 'unsupported',
      answer: 'Could not interpret this question.',
      facts: [],
    });
    render(<FinanceAgentPanel />);
    await question('Give me a quick overview');
    expect(
      await screen.findByText(
        /Deterministic fallback — model unavailable or invalid/,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Could not interpret this question.'),
    ).toBeInTheDocument();
  });

  it('shows exclusive periods and bounded-list warnings', async () => {
    ask.mockResolvedValue({
      ...answer,
      period_start: '2026-07-01',
      period_end: '2026-08-01',
      truncated: true,
    });
    render(<FinanceAgentPanel />);
    await question();
    expect(
      await screen.findByText(
        /Period: 2026-07-01 to 2026-08-01 \(end exclusive\)/,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Only a bounded subset is shown/),
    ).toBeInTheDocument();
  });

  it('renders errors instead of retaining an old answer', async () => {
    ask
      .mockResolvedValueOnce(answer)
      .mockRejectedValueOnce(new Error('Please sign in again.'));
    render(<FinanceAgentPanel />);
    const user = await question();
    await screen.findByText(answer.answer);
    await user.click(screen.getByRole('button', { name: 'Ask ledger' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Please sign in again.',
    );
    expect(screen.queryByText(answer.answer)).not.toBeInTheDocument();
  });

  it('blocks blank questions and repeated submission while a query runs', async () => {
    let finish: ((value: FinanceAgentResult) => void) | undefined;
    ask.mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    render(<FinanceAgentPanel />);
    expect(screen.getByRole('button', { name: 'Ask ledger' })).toBeDisabled();
    await question();
    expect(
      screen.getByRole('button', { name: 'Checking ledger…' }),
    ).toBeDisabled();
    expect(screen.getByLabelText('Finance question')).toBeDisabled();
    finish?.(answer);
    await screen.findByText(answer.answer);
    expect(ask).toHaveBeenCalledOnce();
  });

  it('cancels in-flight requests on unmount', async () => {
    ask.mockImplementation(() => new Promise(() => {}));
    const { unmount } = render(<FinanceAgentPanel />);
    await question();
    const signal = ask.mock.calls[0]?.[1];
    unmount();
    await waitFor(() => expect(signal?.aborted).toBe(true));
  });
});
