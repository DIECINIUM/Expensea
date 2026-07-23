import { MockedProvider } from '@apollo/client/testing/react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ApiFoundationStatus } from './ApiFoundationStatus';
import {
  FOUNDATION_STATUS_QUERY,
  useFoundationStatus,
} from '../../graphql/foundation-status';

function ApiStatusHarness() {
  const status = useFoundationStatus();
  return <ApiFoundationStatus status={status} />;
}

const successMock = {
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

describe('ApiFoundationStatus', () => {
  it('announces while the GraphQL foundation is being checked', () => {
    render(
      <MockedProvider mocks={[{ ...successMock, delay: 1_000 }]}>
        <ApiStatusHarness />
      </MockedProvider>,
    );

    expect(screen.getByRole('status')).toHaveTextContent(/checking api/i);
  });

  it('surfaces backend app metadata after a successful query', async () => {
    render(
      <MockedProvider mocks={[successMock]}>
        <ApiStatusHarness />
      </MockedProvider>,
    );

    expect(
      await screen.findByText(/api foundation online/i),
    ).toBeInTheDocument();
    expect(screen.getByText('SpendGraph Test API')).toBeInTheDocument();
    expect(screen.getByText('v0.1.0-test · test')).toBeInTheDocument();
  });

  it('shows an honest, retryable offline state', async () => {
    render(
      <MockedProvider
        mocks={[
          {
            request: { query: FOUNDATION_STATUS_QUERY },
            error: new Error('Backend unavailable'),
          },
        ]}
      >
        <ApiStatusHarness />
      </MockedProvider>,
    );

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /api unavailable/i,
    );
    expect(
      screen.getByRole('button', { name: /retry connection/i }),
    ).toBeEnabled();
  });
});
