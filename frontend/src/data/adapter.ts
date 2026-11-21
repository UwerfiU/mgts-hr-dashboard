// Адаптер «контракт Backend → контракт дашборда» (см. README, «Подключение Backend»).
//
// Backend отдаёт собственные формы /api/v1/{meta,metrics,feedback}; экраны ждут
// Meta/Metrics/Feedback из types.ts. Здесь — согласование форм без изменения UI:
//   * cycles: [1..N] → [{month, label, shortLabel}] (цикл 1 = Апрель 2026, как в моках);
//   * metrics: {metricId, role, scale} → {id, scales: {role: {min, max, step}}};
//   * interns/mentors: aliases.interns/mentors {id, alias} → {id, label};
//     связь «стажёр → наставник» в API /meta отсутствует → mentorId не задаём;
//   * coverage: добавляется percent (Backend отдаёт только submitted/expected);
//   * comparison: unavailable (нет пар) → no_pairs, not_configured → unavailable;
//   * feedback: {texts: [{month, role, questionKey, text}]} → {items: [...]};
//   * sync: список коннекторов → единый статус (пустой список в demo — 'current').

import type { Comparison, Cycle, Coverage, DataMode, Feedback, Meta, Metrics, Role, Scale } from './types.ts';

const ROLES: Role[] = ['intern', 'mentor'];

// Цикл 1 программы соответствует апрелю 2026 (как в демо-моках).
const PROGRAM_START_MONTH_INDEX = 3; // 0 = январь
const PROGRAM_START_YEAR = 2026;
const MONTH_FULL = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
const MONTH_SHORT = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'];

export function cycleLabels(months: number[]): Cycle[] {
  return months.map((month) => {
    const offset = PROGRAM_START_MONTH_INDEX + month - 1;
    const index = ((offset % 12) + 12) % 12;
    const year = PROGRAM_START_YEAR + Math.floor(offset / 12);
    return { month, label: `${MONTH_FULL[index]} ${year}`, shortLabel: MONTH_SHORT[index] };
  });
}

function toDataMode(value: unknown): DataMode {
  return value === 'real' ? 'live' : 'demo';
}

// /meta отдаётся до всех остальных запросов — запоминаем режим для feedback.
let lastDataMode: DataMode = 'demo';

export function toMeta(raw: Record<string, any>): Meta {
  const dataMode = toDataMode(raw.dataMode);
  lastDataMode = dataMode;
  const personal = raw.detailPermissions?.personalSlicesAllowed === true;
  const detailAvailable = personal && raw.detailPermissions?.numericHistoryAllowed === true;

  const metrics = (Array.isArray(raw.metrics) ? raw.metrics : []).map((m: any) => {
    const scales: Partial<Record<Role, Scale>> = {};
    const role = m.role as Role | undefined;
    const scale = m.scale as { min?: unknown; max?: unknown } | null | undefined;
    if ((role === 'intern' || role === 'mentor') && scale && typeof scale.min === 'number' && typeof scale.max === 'number') {
      scales[role] = { min: scale.min, max: scale.max, step: 1 };
    }
    return { id: String(m.metricId), label: String(m.label ?? m.metricId), scales };
  });
  // По умолчанию — метрика с настроенной парой сравнения (в каталоге это skill_growth);
  // иначе первый показатель роли «стажёр», затем любой.
  const defaultMetricId =
    metrics.find(({ id }) => id === 'skill_growth')?.id ??
    metrics.find(({ scales }) => Boolean(scales.intern))?.id ??
    metrics[0]?.id ?? '';

  const aliases = raw.aliases ?? {};
  const interns = (Array.isArray(aliases.interns) ? aliases.interns : []).map((p: any) => ({
    id: String(p.id), label: String(p.alias ?? p.id), detailAvailable,
  }));
  const mentors = (Array.isArray(aliases.mentors) ? aliases.mentors : []).map((p: any) => ({
    id: String(p.id), label: String(p.alias ?? p.id),
  }));
  const categories = (Array.isArray(raw.categories) ? raw.categories : []).map((c: any) => ({
    id: String(c.id), label: String(c.label ?? c.id),
  }));

  // sync: Backend — список коннекторов. Пустой список (demo без внешних источников)
  // считаем актуальным; ошибка у любого коннектора — 'stale'.
  const connectors = Array.isArray(raw.sync) ? raw.sync : [];
  const latest = connectors.reduce<string | null>(
    (acc, s: any) => (typeof s.lastSuccessAt === 'string' && (!acc || s.lastSuccessAt > acc) ? s.lastSuccessAt : acc),
    null,
  );
  const sync = {
    status: (connectors.length === 0 || !connectors.some((s: any) => s.lastError)) ? 'current' as const : 'stale' as const,
    updatedAt: latest,
  };

  return {
    dataMode,
    programLabel: 'Программа стажировок',
    cycles: cycleLabels(Array.isArray(raw.cycles) ? raw.cycles.map(Number).filter((n) => Number.isFinite(n)) : []),
    metrics,
    defaultMetricId,
    roles: { intern: 'Стажёры', mentor: 'Наставники' },
    interns,
    mentors,
    categories,
    // Фильтр «Наставник» не показываем: /meta не отдаёт связь «стажёр → наставник»,
    // и колонка в каталоге была бы сплошь «Связь недоступна».
    filters: { intern: personal, mentor: false, role: true, category: true },
    detailAvailable,
    aiAvailable: raw.aiAvailable === true,
    sync,
  };
}

export function toMetrics(raw: Record<string, any>): Metrics {
  const coverage = {} as Record<Role, Coverage>;
  for (const role of ROLES) {
    const c = raw.coverage?.[role] ?? {};
    const submitted = typeof c.submitted === 'number' ? c.submitted : 0;
    const expected = typeof c.expected === 'number' ? c.expected : null;
    coverage[role] = {
      submitted,
      expected,
      percent: expected && expected > 0 ? Math.round((submitted / expected) * 100) : null,
    };
  }
  return {
    dataMode: toDataMode(raw.dataMode),
    metricId: String(raw.metricId ?? ''),
    coverage,
    series: Array.isArray(raw.series) ? raw.series : [],
    distribution: Array.isArray(raw.distribution) ? raw.distribution : [],
    comparison: toComparison(raw.comparison),
  };
}

function toComparison(raw: any): Comparison {
  if (raw?.status === 'available') {
    return {
      status: 'available',
      direction: raw.direction === 'mentor_minus_intern' ? 'mentor_minus_intern' : 'intern_minus_mentor',
      points: Array.isArray(raw.points) ? raw.points : [],
    };
  }
  if (raw?.status === 'unavailable') return { status: 'no_pairs' };
  return { status: 'unavailable', message: 'Сравнение не настроено для этого показателя.' };
}

export function toFeedback(raw: Record<string, any>): Feedback {
  const items = (Array.isArray(raw.texts) ? raw.texts : []).map((t: any, i: number) => ({
    id: `fb-${t.role}-${t.month}-${t.questionKey ?? 'text'}-${i}`,
    month: Number(t.month),
    role: t.role === 'mentor' ? 'mentor' as const : 'intern' as const,
    categoryId: typeof t.questionKey === 'string' ? t.questionKey : undefined,
    text: String(t.text ?? ''),
  }));
  return {
    dataMode: lastDataMode, // /feedback в ответе Backend не содержит режима данных
    status: items.length > 0 ? 'ok' : 'empty',
    items,
  };
}
