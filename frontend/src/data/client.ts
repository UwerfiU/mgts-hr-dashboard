import { createHttpClient } from './http.ts';
import { createMockClient } from './mock.ts';
import type { DemoScenario } from './fixtures.ts';

export const isHttp = import.meta.env.VITE_DATA_MODE === 'http';

export function createDataClient(scenario: DemoScenario) {
  return isHttp ? createHttpClient(import.meta.env.VITE_API_BASE_URL) : createMockClient(scenario);
}
