import { ApiError } from './types.ts';
import type { DataClient, FeedbackQuery, MetricsQuery } from './types.ts';

export function createHttpClient(baseUrl = '', transport: typeof fetch = fetch): DataClient {
  const prefix = baseUrl.replace(/\/+$/, '');
  async function get<T>(path: string, signal: AbortSignal | undefined, query?: MetricsQuery | FeedbackQuery): Promise<T> {
    const params = new URLSearchParams();
    if (query) {
      for (const [name, value] of Object.entries(query)) {
        if (value !== undefined && value !== '') params.set(name, String(value));
      }
    }
    const response = await transport(`${prefix}/api/v1/${path}${params.size ? `?${params}` : ''}`, {
      signal,
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) {
      const body: { message?: string } | null = await response.json().catch(() => null);
      throw new ApiError(response.status, body?.message || 'Сервис вернул ошибку.');
    }
    return response.json();
  }

  return {
    meta: (signal) => get('meta', signal),
    metrics: (query, signal) => get('metrics', signal, query),
    feedback: (query, signal) => get('feedback', signal, query),
  };
}
