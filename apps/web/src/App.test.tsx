import { MockedProvider } from '@apollo/client/testing/react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { App } from './App';
import { FOUNDATION_STATUS_QUERY } from './graphql/foundation-status';
import { dashboardSuccessMock } from './test/dashboard-fixtures';

const foundationStatusMock = {
  request: {
    query: FOUNDATION_STATUS_QUERY,
  },
  result: {
    data: {
      health: 'ok',
      appInfo: {
        name: 'SpendGraph Test API',
        version: '0.1.0-test',
        environment: 'test',
      },
    },
  },
};

function renderApp() {
  return render(
    <MockedProvider mocks={[foundationStatusMock, dashboardSuccessMock]}>
      <App />
    </MockedProvider>,
  );
}

describe('SpendGraph dashboard', () => {
  it('renders the live financial overview and review-first AI inbox', async () => {
    renderApp();

    expect(
      await screen.findByRole('heading', {
        name: /good morning, mohd salik/i,
      }),
    ).toBeInTheDocument();
    expect(screen.getAllByText('₹18,540')).toHaveLength(2);
    expect(screen.getByText('Open payable balance')).toBeInTheDocument();
    expect(screen.getByText('Open receivable balance')).toBeInTheDocument();
    expect(screen.getByText('1 expected payment')).toBeInTheDocument();
    expect(
      screen.getByRole('table', { name: /latest transactions/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /ai-derived records appear only after explicit approval/i,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: /financial notes inbox/i }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/synthetic/i)).not.toBeInTheDocument();
  });

  it('surfaces the successful backend foundation query', async () => {
    renderApp();

    expect(
      await screen.findByText(/api foundation online/i),
    ).toBeInTheDocument();
    expect(screen.getByText('SpendGraph Test API')).toBeInTheDocument();
  });

  it('provides a trapped, dismissible mobile navigation modal', async () => {
    const user = userEvent.setup();
    renderApp();
    const openButton = screen.getByRole('button', { name: /open navigation/i });

    expect(openButton).toHaveAttribute('aria-expanded', 'false');
    await user.click(openButton);

    const dialog = screen.getByRole('dialog', { name: /navigation menu/i });
    const closeButton = within(dialog).getByRole('button', {
      name: /close navigation panel/i,
    });
    expect(openButton).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByTestId('app-background')).toHaveAttribute('inert');
    await waitFor(() => expect(closeButton).toHaveFocus());
    expect(
      Array.from(dialog.querySelectorAll<HTMLElement>('*'))
        .filter((element) =>
          element.matches(
            'a[href], button:not(:disabled):not([tabindex="-1"])',
          ),
        )
        .map(
          (element) =>
            element.getAttribute('aria-label') ?? element.textContent?.trim(),
        ),
    ).toEqual([
      'Close navigation panel',
      'Overview',
      'Transactions',
      'AI inbox',
      'People',
      'Money owed',
      'Recurring',
    ]);
    within(dialog)
      .getByText(/wrap focus to the end/i)
      .focus();
    expect(
      within(dialog).getByRole('link', { name: /recurring/i }),
    ).toHaveFocus();
    within(dialog)
      .getByText(/wrap focus to the start/i)
      .focus();
    expect(closeButton).toHaveFocus();

    await user.keyboard('{Escape}');
    expect(
      screen.queryByRole('dialog', { name: /navigation menu/i }),
    ).not.toBeInTheDocument();
    expect(openButton).toHaveAttribute('aria-expanded', 'false');
    await waitFor(() => expect(openButton).toHaveFocus());
    expect(screen.getByTestId('app-background')).not.toHaveAttribute('inert');
  });
});
