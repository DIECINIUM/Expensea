import { describe, expect, it } from 'vitest';

import { DEFAULT_GRAPHQL_URL, resolveGraphqlUrl } from './client';

describe('resolveGraphqlUrl', () => {
  it('uses the deployment-safe same-origin endpoint when no URL is configured', () => {
    expect(resolveGraphqlUrl()).toBe(DEFAULT_GRAPHQL_URL);
    expect(resolveGraphqlUrl('   ')).toBe(DEFAULT_GRAPHQL_URL);
    expect(DEFAULT_GRAPHQL_URL).toBe('/graphql');
  });

  it('normalizes a configured GraphQL endpoint', () => {
    expect(resolveGraphqlUrl(' https://api.example.test/graphql ')).toBe(
      'https://api.example.test/graphql',
    );
  });
});
