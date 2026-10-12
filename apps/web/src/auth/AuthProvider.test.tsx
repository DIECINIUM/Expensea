import { MockedProvider } from '@apollo/client/testing/react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthBoundary, AuthProvider } from './AuthProvider';
import { getCsrfToken, setCsrfToken } from './api';

afterEach(() => {
  vi.unstubAllGlobals();
  setCsrfToken('');
});

function renderAuth() {
  render(
    <MockedProvider>
      <AuthProvider>
        <AuthBoundary>
          <p>Private ledger</p>
        </AuthBoundary>
      </AuthProvider>
    </MockedProvider>,
  );
}

describe('OIDC application identity', () => {
  it('blocks unauthenticated dashboard and offers separate identity-provider login', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: () => Promise.resolve({ detail: { code: 'AUTH_REQUIRED' } }),
      }),
    );
    renderAuth();
    expect(
      await screen.findByRole('link', {
        name: 'Sign in with your identity provider',
      }),
    ).toHaveAttribute('href', '/auth/login');
    expect(screen.queryByText('Private ledger')).not.toBeInTheDocument();
    expect(getCsrfToken()).toBe('');
  });

  it('loads server CSRF secret and removes identity after local logout', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({
            authenticated: true,
            name: 'Owner',
            mode: 'oidc',
            csrfToken: 'csrf',
          }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ loggedOut: true }),
      });
    vi.stubGlobal('fetch', fetcher);
    renderAuth();
    expect(await screen.findByText('Private ledger')).toBeInTheDocument();
    expect(getCsrfToken()).toBe('csrf');
    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }));
    expect(
      await screen.findByRole('link', {
        name: 'Sign in with your identity provider',
      }),
    ).toBeInTheDocument();
    expect(getCsrfToken()).toBe('');
    expect(fetcher.mock.calls[1]).toEqual([
      '/auth/logout',
      {
        method: 'POST',
        credentials: 'include',
        headers: { 'X-CSRF-Token': 'csrf' },
      },
    ]);
  });
});
