import { demoComments, demoMeta, demoScores } from './fixtures.ts';
import type { DemoScenario } from './fixtures.ts';
import { ApiError } from './types.ts';
import type {
  Comparison, Coverage, DataClient, Feedback, Meta, Metrics, MetricsQuery, Role, Slice,
} from './types.ts';

const roles: Role[] = ['intern', 'mentor'];
const demoMode = 'demo' as const;
const round = (value: number) => Math.round(value * 100) / 100;
const mean = (values: number[]) =>
  values.length ? round(values.reduce((sum, value) => sum + value, 0) / values.length) : null;

export function createMockClient(scenario: DemoScenario, latency = 210): DataClient {
  const meta: Meta = structuredClone(demoMeta);
  const failures = new Set<string>();
  if (scenario === 'restricted') {
    meta.interns = [];
    meta.mentors = [];
    meta.filters.intern = false;
    meta.filters.mentor = false;
    meta.detailAvailable = false;
  }
  if (scenario === 'incompatible') meta.defaultMetricId = 'workload';
  if (scenario === 'stale') meta.sync = { status: 'stale', updatedAt: '2026-10-03T08:40:00.000Z' };

  async function wait(endpoint: string, signal?: AbortSignal) {
    signal?.throwIfAborted();
    if (latency) {
      await new Promise<void>((resolve, reject) => {
        const timer = setTimeout(() => {
          signal?.removeEventListener('abort', abort);
          resolve();
        }, latency);
        function abort() {
          clearTimeout(timer);
          reject(signal?.reason);
        }
        signal?.addEventListener('abort', abort, { once: true });
      });
    }
    if (scenario === 'error' && endpoint !== 'meta' && !failures.has(endpoint)) {
      failures.add(endpoint);
      throw new ApiError(503, 'Сервис временно недоступен.');
    }
  }

  function participants(query: Slice) {
    if (query.internId && !meta.interns.some(({ id, detailAvailable }) => id === query.internId && detailAvailable)) {
      throw new ApiError(403, 'Детализация по стажёру недоступна для этого среза.');
    }
    if (query.mentorId && !meta.mentors.some(({ id }) => id === query.mentorId)) {
      throw new ApiError(403, 'Фильтр по наставнику недоступен.');
    }
    return demoMeta.interns.filter(({ id, mentorId }) =>
      (!query.internId || id === query.internId) && (!query.mentorId || mentorId === query.mentorId));
  }

  function cyclesFor(query: Slice) {
    return meta.cycles.filter(({ month }) => month >= query.fromMonth && month <= query.toMonth);
  }

  function metricsFor(query: MetricsQuery): Metrics {
    const participantsInSlice = participants(query);
    const cycles = cyclesFor(query);
    const metric = meta.metrics.find(({ id }) => id === query.metricId);
    if (!metric) throw new ApiError(400, 'Показатель недоступен.');
    const metricId = metric.id;

    const rows = cycles.map(({ month }) => ({
      month,
      ratings: participantsInSlice.map((person) => {
        const index = demoMeta.interns.findIndex(({ id }) => id === person.id);
        function score(role: Role) {
          if (scenario === 'empty' || (scenario === 'gap' && month === 4)) return null;
          if (scenario === 'no-pairs' && (role === 'intern' ? month > 3 : month < 4)) return null;
          if (scenario === 'gap' && month === 2 && role === 'intern' && metricId === 'autonomy') return 0;
          return demoScores[metricId][role][month - 1][index];
        }
        return { intern: score('intern'), mentor: score('mentor') };
      }),
    }));

    function scores(role: Role, ratings: (typeof rows)[number]['ratings']) {
      return ratings.map((rating) => rating[role]).filter((value) => value !== null);
    }

    const allScores = Object.fromEntries(
      roles.map((role) => [role, rows.flatMap(({ ratings }) => scores(role, ratings))]),
    ) as Record<Role, number[]>;

    function coverage(role: Role): Coverage {
      const submitted = allScores[role].length;
      const expected = scenario === 'unknown-plan' && role === 'mentor' ? null : cycles.length * participantsInSlice.length;
      return { submitted, expected, percent: expected ? Math.round(100 * submitted / expected) : null };
    }

    const series = roles.map((role) => ({
      role,
      points: rows.map(({ month, ratings }) => {
        const values = scores(role, ratings);
        return { month, value: mean(values), n: values.length };
      }),
    }));

    const distribution = roles.map((role) => {
      const scale = metric.scales[role]!;
      const totals = new Map<number, number>();
      for (const score of allScores[role]) totals.set(score, (totals.get(score) ?? 0) + 1);
      const buckets = Array.from({ length: (scale.max - scale.min) / scale.step + 1 }, (_, index) => {
        const score = scale.min + index * scale.step;
        return { score, count: totals.get(score) ?? 0 };
      });
      return { role, buckets };
    });

    const comparisonPoints = rows.map(({ month, ratings }) => {
      const deltas = ratings.flatMap(({ intern, mentor }) =>
        intern === null || mentor === null ? [] : [intern - mentor]);
      return { month, value: mean(deltas), nPairs: deltas.length };
    });
    let comparison: Comparison;
    if (metric.id === 'workload') comparison = { status: 'incompatible' };
    else if (comparisonPoints.every(({ nPairs }) => !nPairs)) comparison = { status: 'no_pairs' };
    else comparison = { status: 'available', direction: 'intern_minus_mentor', points: comparisonPoints };

    return {
      dataMode: demoMode,
      metricId: metric.id,
      status: allScores.intern.length || allScores.mentor.length ? 'ok' : 'empty',
      coverage: { intern: coverage('intern'), mentor: coverage('mentor') },
      series,
      distribution,
      comparison,
    };
  }

  return {
    async meta(signal) {
      await wait('meta', signal);
      return structuredClone(meta);
    },
    async metrics(query, signal) {
      await wait('metrics', signal);
      return metricsFor(query);
    },
    async feedback(query, signal): Promise<Feedback> {
      await wait('feedback', signal);
      const ids = new Set(participants(query).map(({ id }) => id));
      if (query.internId === 'intern-04' || query.mentorId === 'mentor-04') {
        return { dataMode: demoMode, status: 'unavailable', items: [], message: 'Тексты отзывов скрыты для этого среза.' };
      }
      const cycles = new Set(cyclesFor(query).map(({ month }) => month));
      if (scenario === 'gap') cycles.delete(4);
      const items = scenario === 'empty' ? [] : demoComments
        .filter((comment) => ids.has(comment.internId) && cycles.has(comment.month) &&
          comment.aggregateAllowed !== false &&
          (scenario !== 'no-pairs' || (comment.role === 'intern' ? comment.month <= 3 : comment.month >= 4)) &&
          (!query.role || comment.role === query.role) &&
          (!query.categoryId || comment.categoryId === query.categoryId))
        .map(({ id, month, role, categoryId, text }) => ({ id, month, role, categoryId, text }));
      return { dataMode: demoMode, status: items.length ? 'ok' : 'empty', items };
    },
  };
}
