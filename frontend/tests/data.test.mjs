import assert from 'node:assert/strict';
import { test } from 'node:test';

import { createMockClient } from '../src/data/mock.ts';
import { createHttpClient } from '../src/data/http.ts';

const mock = (scenario = 'normal') => createMockClient(scenario, 0);
const query = { fromMonth: 1, toMonth: 6, metricId: 'autonomy' };

test('охват и парное сравнение зависят от выбранных циклов и наставника', async () => {
  const api = mock();
  const overview = await api.metrics(query);
  assert.equal(overview.series[0].points.length, 6);
  assert.deepEqual(overview.coverage.intern, { submitted: 28, expected: 30, percent: 93 });
  const filtered = await api.metrics({ ...query, toMonth: 1, mentorId: 'mentor-01' });
  assert.deepEqual(filtered.coverage.intern, { submitted: 1, expected: 1, percent: 100 });
  assert.deepEqual(filtered.comparison.points, [{ month: 1, value: 1, nPairs: 1 }]);
});

test('нулевая оценка и пропуск приходят как разные значения', async () => {
  const api = mock('gap');
  const { series } = await api.metrics(query);
  assert.deepEqual(series[0].points[1], { month: 2, value: 0, n: 5 });
  assert.deepEqual(series[0].points[3], { month: 4, value: null, n: 0 });
});

test('при неизвестном плане API отдаёт число ответов и null вместо процента', async () => {
  const api = mock('unknown-plan');
  const { coverage } = await api.metrics(query);
  assert.deepEqual(coverage.mentor, { submitted: 25, expected: null, percent: null });
});

test('несопоставимые шкалы, отсутствие пар и пустой срез имеют отдельные статусы', async () => {
  const api = mock();
  assert.equal((await api.metrics({ ...query, metricId: 'workload' })).comparison.status, 'incompatible');
  assert.equal((await mock('no-pairs').metrics(query)).comparison.status, 'no_pairs');
  assert.equal((await mock('empty').metrics(query)).status, 'empty');
});

test('запрещённый псевдоним закрывает оба персональных запроса', async () => {
  const api = mock('restricted');
  const meta = await api.meta();
  assert.equal(meta.filters.intern, false);
  await assert.rejects(api.metrics({ ...query, internId: 'intern-01' }), { status: 403 });
  await assert.rejects(api.feedback({ ...query, internId: 'intern-01' }), { status: 403 });
});

test('отзывы ограничены циклом, ролью, категорией и отдельным разрешением на текст', async () => {
  const api = mock();
  const allowed = await api.feedback({
    fromMonth: 3, toMonth: 3, internId: 'intern-01', role: 'mentor', categoryId: 'growth',
  });
  assert.equal(allowed.items.length, 1);
  assert.equal(allowed.items[0].month, 3);
  const mismatch = await api.feedback({ fromMonth: 3, toMonth: 3, internId: 'intern-01', role: 'intern', categoryId: 'growth' });
  assert.equal(mismatch.status, 'empty');
  assert.equal((await api.metrics({ ...query, internId: 'intern-04' })).status, 'ok');
  assert.equal((await api.feedback({ ...query, internId: 'intern-04' })).status, 'unavailable');
});

test('после ошибки повторный запрос возвращает исходный демосрез', async () => {
  const api = mock('error');
  await assert.rejects(api.metrics(query), { status: 503 });
  assert.equal((await api.metrics(query)).status, 'ok');
});

test('HTTP-клиент отправляет исходный срез и сохраняет отказ сервера', async () => {
  const urls = [];
  const api = createHttpClient('http://localhost:8000/', async (url) => {
    urls.push(String(url));
    return new Response(JSON.stringify({ message: 'Доступ закрыт' }), { status: 403 });
  });
  await assert.rejects(api.metrics({ ...query, internId: 'a/+?' }), { status: 403, message: 'Доступ закрыт' });
  assert.equal(urls[0], 'http://localhost:8000/api/v1/metrics?fromMonth=1&toMonth=6&metricId=autonomy&internId=a%2F%2B%3F');
});
