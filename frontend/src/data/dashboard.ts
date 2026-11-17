import type { DataClient, Metric, Metrics, Slice } from './types.ts';

export type DashboardResult =
  | { metricId: string; status: 'ready'; data: Metrics }
  | { metricId: string; status: 'error'; error: unknown };

export async function loadDashboardMetrics(
  client: DataClient, metrics: Metric[], slice: Slice, signal?: AbortSignal,
): Promise<DashboardResult[]> {
  signal?.throwIfAborted();
  const rows = await Promise.all(metrics.map(async ({ id }): Promise<DashboardResult> => {
    try {
      const data = await client.metrics({ ...slice, metricId: id }, signal);
      return { metricId: id, status: 'ready', data };
    } catch (error) {
      return { metricId: id, status: 'error', error };
    }
  }));
  signal?.throwIfAborted();
  return rows;
}
