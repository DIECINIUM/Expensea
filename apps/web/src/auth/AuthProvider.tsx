import { useApolloClient } from '@apollo/client/react';
import {
  useCallback,
  useEffect,
  useState,
  type PropsWithChildren,
} from 'react';

import { ApiError, apiRequest, apiUrl, setCsrfToken } from './api';
import { AuthContext, useAuth, type AuthProfile } from './context';

export function AuthProvider({ children }: PropsWithChildren) {
  const client = useApolloClient();
  const [profile, setProfile] = useState<AuthProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    () =>
      apiRequest<AuthProfile>('/auth/me')
        .then((result) => {
          setCsrfToken(result.csrfToken);
          setProfile(result);
        })
        .catch((failure: unknown) => {
          setCsrfToken('');
          setProfile(null);
          if (!(failure instanceof ApiError && failure.status === 401)) {
            setError('Authentication service unavailable. Please retry.');
          }
        })
        .finally(() => {
          setLoading(false);
        }),
    [],
  );

  async function reload() {
    setLoading(true);
    setError(null);
    await load();
  }

  useEffect(() => {
    void load();
  }, [load]);

  async function logout() {
    try {
      await apiRequest('/auth/logout', 'POST');
      setCsrfToken('');
      setProfile(null);
      await client.clearStore();
    } catch {
      setError('Sign out failed. Please retry.');
    }
  }

  return (
    <AuthContext.Provider value={{ profile, loading, error, reload, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function AuthBoundary({ children }: PropsWithChildren) {
  const auth = useAuth();
  // Component-level GraphQL mock harnesses may omit the application providers.
  if (!auth) return children;
  if (auth.loading) return <p role="status">Checking your session…</p>;
  if (!auth.profile) {
    return (
      <main className="mx-auto max-w-lg p-8">
        <h1 className="text-2xl font-semibold">Sign in to SpendGraph AI</h1>
        <p>Your app identity is separate from connecting a Gmail account.</p>
        {auth.error && <p role="alert">{auth.error}</p>}
        <a href={apiUrl('/auth/login')}>Sign in with your identity provider</a>
        <button onClick={() => void auth.reload()}>Retry session check</button>
      </main>
    );
  }
  return (
    <>
      {auth.profile.mode === 'oidc' && (
        <div className="flex justify-end gap-3 p-2">
          <span>Signed in as {auth.profile.name}</span>
          <button onClick={() => void auth.logout()}>Sign out</button>
          {auth.error && <p role="alert">{auth.error}</p>}
        </div>
      )}
      {children}
    </>
  );
}
