import { ApolloClient, HttpLink, InMemoryCache } from '@apollo/client';

export const DEFAULT_GRAPHQL_URL = '/graphql';

export function resolveGraphqlUrl(configuredUrl?: string): string {
  const normalizedUrl = configuredUrl?.trim();
  return normalizedUrl || DEFAULT_GRAPHQL_URL;
}

export function createApolloClient(
  uri = resolveGraphqlUrl(import.meta.env.VITE_GRAPHQL_URL),
) {
  return new ApolloClient({
    link: new HttpLink({
      uri,
      credentials: 'include',
    }),
    cache: new InMemoryCache({
      typePolicies: {
        Query: {
          fields: {
            transactions: {
              keyArgs: ['filter'],
              merge: false,
            },
          },
        },
      },
    }),
    devtools: {
      enabled: import.meta.env.DEV,
    },
  });
}

export const apolloClient = createApolloClient();
