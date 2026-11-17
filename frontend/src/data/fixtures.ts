import type { FeedbackItem, Meta, Role } from './types.ts';

export const demoScenarios = [
  { id: 'normal', label: 'Обычный срез' },
  { id: 'gap', label: 'Пропуск цикла и ноль' },
  { id: 'unknown-plan', label: 'Неизвестный план' },
  { id: 'incompatible', label: 'Несопоставимые шкалы' },
  { id: 'no-pairs', label: 'Нет пар для сравнения' },
  { id: 'empty', label: 'Пустой срез' },
  { id: 'error', label: 'Ошибка запроса' },
  { id: 'restricted', label: 'Недоступная детализация' },
  { id: 'stale', label: 'Устаревшая синхронизация' },
] as const;

export type DemoScenario = typeof demoScenarios[number]['id'];

export const demoMeta: Meta = {
  dataMode: 'demo',
  programLabel: 'Программа стажировок',
  cycles: [
    { month: 1, label: 'Апрель 2026', shortLabel: 'Апр' },
    { month: 2, label: 'Май 2026', shortLabel: 'Май' },
    { month: 3, label: 'Июнь 2026', shortLabel: 'Июн' },
    { month: 4, label: 'Июль 2026', shortLabel: 'Июл' },
    { month: 5, label: 'Август 2026', shortLabel: 'Авг' },
    { month: 6, label: 'Сентябрь 2026', shortLabel: 'Сен' },
  ],
  metrics: [
    { id: 'autonomy', label: 'Самостоятельность', scales: { intern: { min: 0, max: 5, step: 1 }, mentor: { min: 0, max: 5, step: 1 } } },
    { id: 'clarity', label: 'Понимание задач', scales: { intern: { min: 1, max: 5, step: 1 }, mentor: { min: 1, max: 5, step: 1 } } },
    { id: 'workload', label: 'Нагрузка', scales: { intern: { min: 1, max: 5, step: 1 }, mentor: { min: 1, max: 10, step: 1 } } },
    { id: 'quality', label: 'Качество работы', scales: { intern: { min: 1, max: 5, step: 1 }, mentor: { min: 1, max: 5, step: 1 } } },
    { id: 'teamwork', label: 'Командное взаимодействие', scales: { intern: { min: 1, max: 5, step: 1 }, mentor: { min: 1, max: 5, step: 1 } } },
    { id: 'initiative', label: 'Инициативность', scales: { intern: { min: 1, max: 5, step: 1 }, mentor: { min: 1, max: 5, step: 1 } } },
    { id: 'learning', label: 'Освоение навыков', scales: { intern: { min: 1, max: 5, step: 1 }, mentor: { min: 1, max: 5, step: 1 } } },
    { id: 'motivation', label: 'Мотивация', scales: { intern: { min: 1, max: 5, step: 1 }, mentor: { min: 1, max: 5, step: 1 } } },
  ],
  defaultMetricId: 'autonomy',
  roles: { intern: 'Стажёры', mentor: 'Наставники' },
  interns: [
    { id: 'intern-01', label: 'Стажёр 01', mentorId: 'mentor-01', detailAvailable: true },
    { id: 'intern-02', label: 'Стажёр 02', mentorId: 'mentor-02', detailAvailable: true },
    { id: 'intern-03', label: 'Стажёр 03', mentorId: 'mentor-03', detailAvailable: true },
    { id: 'intern-04', label: 'Стажёр 04', mentorId: 'mentor-04', detailAvailable: true },
    { id: 'intern-05', label: 'Стажёр 05', mentorId: 'mentor-05', detailAvailable: false },
  ],
  mentors: [
    { id: 'mentor-01', label: 'Наставник 01' },
    { id: 'mentor-02', label: 'Наставник 02' },
    { id: 'mentor-03', label: 'Наставник 03' },
    { id: 'mentor-04', label: 'Наставник 04' },
    { id: 'mentor-05', label: 'Наставник 05' },
  ],
  categories: [
    { id: 'growth', label: 'Развитие' },
    { id: 'support', label: 'Поддержка' },
    { id: 'workload', label: 'Нагрузка' },
  ],
  filters: { intern: true, mentor: true, role: true, category: true },
  detailAvailable: true,
  aiAvailable: false,
  sync: { status: 'current', updatedAt: '2026-11-16T08:40:00.000Z' },
};

type ScoreGrid = (number | null)[][];
type ScoreFixture = Record<Role, ScoreGrid>;

// Строки соответствуют циклам, столбцы — пяти участникам программы.
export const demoScores: Record<string, ScoreFixture> = {
  autonomy: {
    intern: [[3, 3, 3, 4, 3], [4, 4, 3, 4, 3], [4, 4, 4, null, 3], [4, 3, 3, 4, 3], [5, 4, 4, 4, null], [5, 5, 4, 4, 4]],
    mentor: [[2, 3, 2, 3, null], [3, 3, 3, 4, null], [3, 4, 3, null, 3], [3, 4, 3, 4, 4], [4, 4, 4, 4, null], [4, 5, 4, 4, null]],
  },
  clarity: {
    intern: [[3, 3, 4, 3, 4], [3, 4, 4, 4, 4], [4, 4, 4, null, 3], [4, 4, 4, 4, 4], [5, 4, 4, 4, null], [5, 5, 4, 5, 4]],
    mentor: [[3, 3, 4, 3, null], [3, 4, 4, 3, null], [3, 4, 4, null, 3], [4, 4, 4, 5, 4], [5, 4, 4, 4, null], [5, 5, 5, 4, null]],
  },
  workload: {
    intern: [[3, 2, 3, 3, 2], [3, 3, 3, 4, 3], [4, 3, 3, null, 3], [5, 4, 3, 5, 4], [4, 4, 4, 4, null], [4, 3, 3, 4, 3]],
    mentor: [[4, 4, 5, 4, null], [5, 4, 5, 5, null], [6, 6, 5, null, 5], [7, 7, 6, 8, 7], [6, 6, 6, 6, null], [5, 6, 5, 6, null]],
  },
  // Синтетические истории для проверки интерфейса, не утверждённые вопросы анкет.
  quality: {
    intern: [[3, 3, 2, 3, 3], [3, 3, 3, 4, 3], [4, 3, 3, null, 4], [4, 4, 3, 4, 4], [4, 5, 4, 4, null], [5, 5, 4, 5, 4]],
    mentor: [[2, 2, 2, 3, null], [3, 2, 3, 3, null], [3, 3, 3, null, 3], [3, 4, 3, 4, 3], [4, 4, 4, 4, null], [4, 5, 4, 4, null]],
  },
  teamwork: {
    intern: [[3, 4, 3, 3, 4], [4, 4, 3, 4, 4], [4, 4, 4, null, 4], [4, 4, 4, 4, 4], [5, 4, 5, 4, null], [5, 4, 5, 4, 5]],
    mentor: [[3, 3, 3, 4, null], [4, 3, 4, 4, null], [4, 4, 4, null, 4], [4, 5, 4, 4, 4], [5, 5, 4, 4, null], [5, 5, 5, 4, null]],
  },
  initiative: {
    intern: [[2, 2, 3, 2, 2], [2, 3, 3, 2, 3], [3, 3, 3, null, 3], [3, 4, 3, 3, 4], [4, 4, 4, 3, null], [4, 5, 4, 4, 4]],
    mentor: [[1, 2, 2, 2, null], [2, 2, 2, 2, null], [2, 3, 2, null, 3], [3, 3, 3, 2, 3], [3, 4, 3, 3, null], [4, 4, 4, 3, null]],
  },
  learning: {
    intern: [[2, 3, 2, 2, 3], [3, 3, 3, 3, 3], [4, 4, 3, null, 4], [4, 4, 4, 4, 4], [5, 4, 4, 5, null], [5, 5, 5, 4, 5]],
    mentor: [[2, 2, 2, 2, null], [3, 3, 2, 3, null], [3, 4, 3, null, 3], [4, 4, 4, 3, 4], [4, 4, 5, 4, null], [5, 4, 5, 5, null]],
  },
  motivation: {
    intern: [[5, 5, 4, 5, 4], [4, 4, 4, 5, 4], [4, 3, 4, null, 3], [3, 3, 2, 3, 3], [3, 4, 3, 3, null], [4, 3, 3, 4, 3]],
    mentor: [[4, 4, 4, 4, null], [4, 4, 4, 4, null], [4, 4, 3, null, 4], [4, 3, 3, 4, 3], [4, 4, 3, 4, null], [4, 4, 4, 4, null]],
  },
};

type DemoComment = FeedbackItem & { internId: string; aggregateAllowed?: false };

export const demoComments: DemoComment[] = [
  { id: 'f-10', month: 6, role: 'intern', categoryId: 'growth', internId: 'intern-01', text: 'К последнему месяцу уже самостоятельно составляю план работы на неделю. На встречах с наставником разбираем только спорные решения.' },
  { id: 'f-09', month: 6, role: 'mentor', categoryId: 'growth', internId: 'intern-02', text: 'Стажёр впервые провёл разбор задачи с командой и сам зафиксировал следующие шаги.' },
  { id: 'f-08', month: 5, role: 'intern', categoryId: 'support', internId: 'intern-03', text: 'Короткие встречи в начале недели помогли понять, когда просить помощи и что можно решить самостоятельно.' },
  { id: 'f-07', month: 5, role: 'mentor', categoryId: 'support', internId: 'intern-04', text: 'Полезно заранее договориться о критериях готовности задачи и сверить их после первого черновика.', aggregateAllowed: false },
  { id: 'f-06', month: 4, role: 'intern', categoryId: 'workload', internId: 'intern-02', text: 'В июле две задачи пришли одновременно. Когда расставили приоритеты вместе, получилось уложиться в сроки.' },
  { id: 'f-05', month: 4, role: 'mentor', categoryId: 'workload', internId: 'intern-03', text: 'На следующем цикле стоит оставить больше времени на проверку результата, особенно при нескольких задачах.' },
  { id: 'f-04', month: 3, role: 'mentor', categoryId: 'growth', internId: 'intern-01', text: 'Уверенно разбирает типовые задачи. Следующий шаг — самостоятельно оценивать риски до начала работы.' },
  { id: 'f-03', month: 2, role: 'intern', categoryId: 'support', internId: 'intern-01', text: 'Помогло, что наставник показал пример готовой задачи и объяснил, как проверять результат перед сдачей.' },
  { id: 'f-02', month: 2, role: 'mentor', categoryId: 'growth', internId: 'intern-02', text: 'Уже может выбрать подход к задаче и объяснить, почему он подходит.' },
  { id: 'f-01', month: 1, role: 'intern', categoryId: 'support', internId: 'intern-03', text: 'В начале было трудно понять, у кого уточнять требования. После знакомства с командой вопросы стали решаться быстрее.' },
];
