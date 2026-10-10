import { ApolloProvider } from '@apollo/client/react';
import type { PropsWithChildren } from 'react';

import { apolloClient } from '../graphql/client';
import { AuthProvider } from '../auth/AuthProvider';

export function AppProviders({ children }: PropsWithChildren) {
  return (
    <ApolloProvider client={apolloClient}>
      <AuthProvider>{children}</AuthProvider>
    </ApolloProvider>
  );
}
