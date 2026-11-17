import type { Meta, Role, Slice } from '../data/types.ts';
import { SelectField } from './ui.tsx';

export interface FiltersValue extends Slice {
  metricId: string;
  role?: Role;
  categoryId?: string;
}

type Screen = 'overview' | 'intern' | 'feedback';
const all = (label: string) => ({ id: '', label });

export function FilterBar({ meta, value, screen, onChange, onReset }: {
  meta: Meta;
  value: FiltersValue;
  screen: Screen;
  onChange: (patch: Partial<FiltersValue>) => void;
  onReset: () => void;
}) {
  const cycleOptions = meta.cycles.map((cycle) => ({ id: cycle.month, label: cycle.label }));
  return (
    <section className="filter-bar" aria-label="Фильтры">
      <SelectField label="С цикла" value={value.fromMonth}
        options={cycleOptions.filter(({ id }) => id <= value.toMonth)}
        onChange={(month) => onChange({ fromMonth: Number(month) })} />
      <SelectField label="До цикла" value={value.toMonth}
        options={cycleOptions.filter(({ id }) => id >= value.fromMonth)}
        onChange={(month) => onChange({ toMonth: Number(month) })} />
      {screen !== 'feedback' && (
        <SelectField label="Показатель" value={value.metricId} options={meta.metrics} className="metric-field"
          onChange={(metricId) => onChange({ metricId })} />
      )}
      {screen !== 'intern' && meta.filters.intern && meta.interns.some(({ detailAvailable }) => detailAvailable) && (
        <SelectField label="Стажёр" value={value.internId ?? ''}
          options={[all('Все стажёры'), ...meta.interns.filter(({ detailAvailable }) => detailAvailable)]}
          onChange={(internId) => onChange({ internId: internId || undefined })} />
      )}
      {screen !== 'intern' && meta.filters.mentor && meta.mentors.length > 0 && (
        <SelectField label="Наставник" value={value.mentorId ?? ''} options={[all('Все наставники'), ...meta.mentors]}
          onChange={(mentorId) => onChange({ mentorId: mentorId || undefined })} />
      )}
      {screen === 'feedback' && meta.filters.role && (
        <SelectField label="Роль автора" value={value.role ?? ''}
          options={[all('Все роли'), ...Object.entries(meta.roles).map(([id, label]) => ({ id, label }))]}
          onChange={(role) => onChange({ role: (role || undefined) as Role | undefined })} />
      )}
      {screen === 'feedback' && meta.filters.category && meta.categories.length > 0 && (
        <SelectField label="Категория" value={value.categoryId ?? ''} options={[all('Все категории'), ...meta.categories]}
          onChange={(categoryId) => onChange({ categoryId: categoryId || undefined })} />
      )}
      <button type="button" className="button button--ghost reset-button" onClick={onReset}>
        <span aria-hidden="true">↺</span> Сбросить
      </button>
    </section>
  );
}
