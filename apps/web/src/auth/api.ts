let csrfToken = '';

export function setCsrfToken(value: string) {
  csrfToken = value;
}

export function getCsrfToken() {
  return csrfToken;
}

export function apiUrl(path: string) {
  const graphql = import.meta.env.VITE_GRAPHQL_URL?.trim();
  if (graphql?.startsWith('https://') || graphql?.startsWith('http://')) {
    return new URL(path, graphql).toString();
  }
  return path;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function apiRequest<T>(
  path: string,
  method = 'GET',
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(apiUrl(path), {
    method,
    credentials: 'include',
    headers: method === 'GET' ? {} : { 'X-CSRF-Token': csrfToken },
    ...(signal ? { signal } : {}),
  });
  const data: unknown = await response.json();
  if (!response.ok) {
    let code = 'API_REQUEST_FAILED';
    if (data && typeof data === 'object' && 'detail' in data) {
      const detail = data.detail;
      if (
        detail &&
        typeof detail === 'object' &&
        'code' in detail &&
        typeof detail.code === 'string'
      )
        code = detail.code;
    }
    throw new ApiError(response.status, code);
  }
  return data as T;
}
