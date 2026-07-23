import { gql } from '@apollo/client';
import { useQuery } from '@apollo/client/react';

export const FOUNDATION_STATUS_QUERY = gql`
  query FoundationStatus {
    health
    appInfo {
      name
      version
      environment
    }
  }
`;

interface FoundationStatusData {
  readonly health: string;
  readonly appInfo: {
    readonly name: string;
    readonly version: string;
    readonly environment: string;
  };
}

export type FoundationStatus =
  | { readonly kind: 'loading' }
  | { readonly kind: 'offline'; readonly retry: () => void }
  | {
      readonly kind: 'online';
      readonly name: string;
      readonly version: string;
      readonly environment: string;
    };

export function useFoundationStatus(): FoundationStatus {
  const { data, error, loading, refetch } = useQuery<FoundationStatusData>(
    FOUNDATION_STATUS_QUERY,
    {
      fetchPolicy: 'network-only',
      nextFetchPolicy: 'cache-first',
    },
  );

  if (loading) {
    return { kind: 'loading' };
  }

  if (error || data?.health !== 'ok' || !data.appInfo) {
    return {
      kind: 'offline',
      retry: () => {
        void refetch();
      },
    };
  }

  return {
    kind: 'online',
    name: data.appInfo.name,
    version: data.appInfo.version,
    environment: data.appInfo.environment,
  };
}
