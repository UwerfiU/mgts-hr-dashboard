import type { Cycle, Role, Scale, Slice } from './data/types.ts';

export const roles: Role[] = ['intern', 'mentor'];
export const number = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format;
export const signed = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2, signDisplay: 'exceptZero' }).format;
export const dateTime = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Moscow',
}).format;

export function quantity(value: number, forms: [string, string, string]) {
  const last = value % 10;
  const lastTwo = value % 100;
  const form = lastTwo >= 11 && lastTwo <= 14 ? forms[2] : last === 1 ? forms[0] : last >= 2 && last <= 4 ? forms[1] : forms[2];
  return `${number(value)} ${form}`;
}

export const answers = (value: number) => quantity(value, ['ответ', 'ответа', 'ответов']);
export const pairs = (value: number) => quantity(value, ['пара', 'пары', 'пар']);
export const comments = (value: number) => quantity(value, ['отзыв', 'отзыва', 'отзывов']);
export const scaleLabel = (scale: Scale) => `${number(scale.min)}–${number(scale.max)}`;

export function periodLabel(cycles: Cycle[], { fromMonth, toMonth }: Slice) {
  const start = cycles.find(({ month }) => month === fromMonth);
  const end = cycles.find(({ month }) => month === toMonth);
  if (!start || !end) return 'Период не выбран';
  if (fromMonth === toMonth) return start.label;
  const year = start.label.match(/\s\d{4}$/)?.[0];
  const first = year && end.label.endsWith(year) ? start.label.slice(0, -year.length) : start.label;
  return `${first} — ${end.label.charAt(0).toLowerCase()}${end.label.slice(1)}`;
}
