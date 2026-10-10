import { createContext, useContext } from 'react';

export interface AuthProfile {
  authenticated: boolean;
  mode: 'development' | 'oidc';
  name: string;
  csrfToken: string;
}

export interface AuthState {
  profile: AuthProfile | null;
  loading: boolean;
  error: string | null;
  reload: () => Promise<void>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthState | null>(null);

export function useAuth() {
  return useContext(AuthContext);
}
