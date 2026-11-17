import {
  Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { useId } from 'react';
import type { Comparison, Coverage, Distribution, Meta, Metric, Role, Series, Slice } from '../data/types.ts';
import { answers, number, pairs, roles, scaleLabel, signed } from '../format.ts';
import { RoleMark, SectionTitle } from './ui.tsx';

const color = { intern: 'var(--intern)', mentor: 'var(--mentor)' };

export function CoverageStrip({ coverage, meta }: { coverage: Record<Role, Coverage>; meta: Meta }) {
  return (
    <div className="coverage-grid" role="region" aria-label="Охват анкет">
      {roles.map((role) => {
        const { submitted, expected, percent } = coverage[role];
        const knownPercent = expected !== null && percent != null;
        return (
          <section className={`panel coverage ${role}`} key={role}>
            <div className="coverage-top"><h2>{meta.roles[role]}</h2><RoleMark role={role} variant="dot" /></div>
            <div className="coverage-value">
              <strong>{knownPercent ? `${number(percent)}%` : expected === null ? answers(submitted) : number(submitted)}</strong>
              {expected !== null && <span>{`${number(submitted)} из ${number(expected)} ответов`}</span>}
            </div>
            {knownPercent && (
              <div className="meter" aria-hidden="true">
                <span style={{ width: `${Math.min(100, Math.max(0, percent))}%` }} />
              </div>
            )}
            {expected === null && <p className="coverage-note">План ответов неизвестен</p>}
          </section>
        );
      })}
    </div>
  );
}

function Legend({ meta, metric, showScales = false, variant = 'line' }: {
  meta: Meta; metric: Metric; showScales?: boolean; variant?: 'line' | 'bar';
}) {
  return (
    <ul className="legend" aria-label={showScales ? 'Роли и шкалы' : 'Роли'}>
      {roles.map((role) => {
        const scale = metric.scales[role];
        return scale && (
          <li key={role}>
            <RoleMark role={role} variant={variant} />{meta.roles[role]}
            {showScales && <span>{scaleLabel(scale)}</span>}
          </li>
        );
      })}
    </ul>
  );
}

export function ScoresTable({ meta, metric, series, slice, label }: {
  meta: Meta; metric: Metric; series: Series[]; slice: Slice; label: string;
}) {
  return (
    <table className="data-table score-table" aria-label={label}>
      <thead><tr><th scope="col">Цикл</th>{roles.map((role) => {
        const scale = metric.scales[role];
        return scale && <th key={role} scope="col">{meta.roles[role]} <span>{scaleLabel(scale)}</span></th>;
      })}</tr></thead>
      <tbody>{meta.cycles.map((cycle) => (
        <tr key={cycle.month}>
          <th scope="row">{cycle.label}</th>
          {roles.map((role) => {
            if (!metric.scales[role]) return null;
            const point = series.find((row) => row.role === role)?.points.find(({ month }) => month === cycle.month);
            const outside = cycle.month < slice.fromMonth || cycle.month > slice.toMonth;
            return (
              <td key={role}>
                {outside ? <span className="muted">Вне периода</span> : point?.value == null
                  ? <span className="muted">Нет оценки</span>
                  : <>{number(point.value)} <span className="muted" aria-label={answers(point.n)}>({number(point.n)})</span></>}
              </td>
            );
          })}
        </tr>
      ))}</tbody>
    </table>
  );
}

type ChartRow = { month: number; label: string; intern: number | null; mentor: number | null; internCount: number; mentorCount: number };

function TrendTooltip({ active, payload, meta, activeRoles }: { active: boolean; payload: ReadonlyArray<{ payload?: unknown }>; meta: Meta; activeRoles: Role[] }) {
  const row = payload?.[0]?.payload as ChartRow | undefined;
  if (!active || !row) return null;
  return (
    <div className="chart-tooltip">
      <strong>{meta.cycles.find(({ month }) => month === row.month)?.label}</strong>
      {activeRoles.map((role) => (
        <div key={role}>
          <RoleMark role={role} /> {meta.roles[role]}
          <b>{row[role] == null ? 'Нет оценки' : number(row[role])}</b>
          {row[role] != null && <span>{answers(row[`${role}Count`])}</span>}
        </div>
      ))}
    </div>
  );
}

export function TrendChart({ meta, metric, series, slice, showTable = true }: {
  meta: Meta; metric: Metric; series: Series[]; slice: Slice; showTable?: boolean;
}) {
  const activeRoles = roles.filter((role) => metric.scales[role]);
  const visibleCycles = meta.cycles.filter(({ month }) => month >= slice.fromMonth && month <= slice.toMonth);
  const rows: ChartRow[] = visibleCycles.map((cycle) => {
    const findPoint = (role: Role) => series.find((item) => item.role === role)?.points.find(({ month }) => month === cycle.month);
    const intern = findPoint('intern');
    const mentor = findPoint('mentor');
    return {
      month: cycle.month, label: cycle.shortLabel, intern: intern?.value ?? null, mentor: mentor?.value ?? null,
      internCount: intern?.n ?? 0, mentorCount: mentor?.n ?? 0,
    };
  });
  const scales = activeRoles.map((role) => metric.scales[role]!);
  const split = scales.length === 2 && (scales[0].min !== scales[1].min || scales[0].max !== scales[1].max);
  const gaps = rows.filter((row) => activeRoles.some((role) => row[role] === null)).map(({ label }) => label);
  const available = rows.some((row) => activeRoles.some((role) => row[role] !== null));

  return (
    <section className="panel chart-panel">
      <SectionTitle title="Средняя оценка по циклам" extra={<Legend meta={meta} metric={metric} showScales={split} />} />
      {available ? (
        <div className="chart-area trend-area" aria-label={`График динамики. ${metric.label}`}>
          <ResponsiveContainer width="100%" height="100%" minWidth={0} initialDimension={{ width: 600, height: 196 }}>
            <LineChart data={rows} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--grid)" />
              <XAxis dataKey="label" tickLine={false} axisLine={false} tickMargin={11} />
              {activeRoles.filter((_, i) => split || i === 0).map((role, i) => {
                const scale = metric.scales[role]!;
                return (
                  <YAxis key={role} yAxisId={split ? role : 'shared'} domain={[scale.min, scale.max]} interval="preserveStartEnd"
                    tickCount={Math.min(6, Math.floor((scale.max - scale.min) / scale.step) + 1)}
                    allowDecimals={scale.step < 1} tickLine={false} axisLine={false} tickMargin={6} width={31}
                    orientation={i === 1 ? 'right' : 'left'} tickFormatter={number}
                    tick={{ fill: split ? color[role] : 'var(--subtle)' }} />
                );
              })}
              <Tooltip content={(props) => <TrendTooltip active={props.active} payload={props.payload} meta={meta} activeRoles={activeRoles} />} filterNull={false} />
              {activeRoles.map((role) => (
                <Line key={role} name={meta.roles[role]} dataKey={role} yAxisId={split ? role : 'shared'}
                  type="linear" connectNulls={false} stroke={color[role]} strokeWidth={2.5}
                  strokeDasharray={role === 'mentor' ? '6 5' : undefined}
                  dot={{ r: 4, fill: 'var(--surface)', strokeWidth: 2.5 }}
                  activeDot={{ r: 5 }} isAnimationActive={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : <div className="chart-empty">За этот период нет оценок показателя.</div>}
      {gaps.length > 0 && available && <p className="chart-note"><span aria-hidden="true">╌</span> Пропуск цикла или ряда: {gaps.join(', ')}.</p>}
      {showTable && (
        <details className="chart-details">
          <summary>Таблица значений</summary>
          <ScoresTable meta={{ ...meta, cycles: visibleCycles }} metric={metric} series={series} slice={slice} label="Значения графика" />
        </details>
      )}
    </section>
  );
}

type BucketRow = { score: number; intern?: number; mentor?: number };

export function DistributionChart({ meta, metric, distribution }: { meta: Meta; metric: Metric; distribution: Distribution[] }) {
  const pattern = useId().replace(/:/g, '');
  const makeRows = (items: Distribution[]) => {
    const rows = new Map<number, BucketRow>();
    for (const { role, buckets } of items) {
      for (const { score, count } of buckets) {
        const row = rows.get(score) ?? { score };
        row[role] = count;
        rows.set(score, row);
      }
    }
    return [...rows.values()].sort((a, b) => a.score - b.score);
  };

  const scale = metric.scales.intern;
  const other = metric.scales.mentor;
  const split = scale && other && (scale.min !== other.min || scale.max !== other.max || scale.step !== other.step);
  const groups = split ? distribution.map((series) => [series]) : [distribution];
  const available = distribution.some(({ buckets }) => buckets.some(({ count }) => count > 0));

  return (
    <section className="panel chart-panel distribution-panel">
      <SectionTitle title="Распределение оценок"
        extra={<Legend meta={meta} metric={metric} showScales={Boolean(split)} variant="bar" />} />
      {available ? groups.map((group) => (
        <div key={group.map(({ role }) => role).join()} className={`chart-area ${split ? 'distribution-split' : 'trend-area'}`}
          aria-label={split ? `Распределение: ${meta.roles[group[0].role]}` : 'Распределение по ролям'}>
          <ResponsiveContainer width="100%" height="100%" minWidth={0} initialDimension={{ width: 340, height: split ? 116 : 196 }}>
            <BarChart data={makeRows(group)} barGap={4} margin={{ top: 10, right: 4, bottom: 0, left: 0 }}>
              <defs>
                <pattern id={pattern + group[0].role} width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(35)">
                  <rect width="5" height="5" fill="var(--mentor)" />
                  <path d="M 0 0 L 0 5" stroke="var(--mentor-pattern)" strokeWidth="2" />
                </pattern>
              </defs>
              <CartesianGrid vertical={false} stroke="var(--grid)" />
              <XAxis dataKey="score" axisLine={false} tickLine={false} tickMargin={9} tickFormatter={number} />
              <YAxis allowDecimals={false} axisLine={false} tickLine={false} tickMargin={6} width={29} tickFormatter={number} />
              <Tooltip labelFormatter={(score) => `Оценка ${score}`} formatter={(count) => number(Number(count))}
                cursor={{ fill: 'var(--canvas)' }} />
              {group.map(({ role }) => (
                <Bar key={role} dataKey={role} name={meta.roles[role]} fill={role === 'mentor' ? `url(#${pattern + group[0].role})` : color[role]} maxBarSize={22}
                  radius={[4, 4, 0, 0]} isAnimationActive={false} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )) : <div className="chart-empty">Нет ответов для распределения.</div>}
      {available && (
        <details className="chart-details">
          <summary>Таблица оценок</summary>
          <table className="data-table" aria-label="Число ответов по баллам">
            <thead><tr><th scope="col">Балл</th>{distribution.map(({ role }) => <th key={role} scope="col">{meta.roles[role]}</th>)}</tr></thead>
            <tbody>{makeRows(distribution).map((row) => (
              <tr key={row.score}><th scope="row">{number(row.score)}</th>
                {distribution.map(({ role }) => <td key={role}>{row[role] == null ? 'Вне шкалы' : number(row[role])}</td>)}</tr>
            ))}</tbody>
          </table>
        </details>
      )}
    </section>
  );
}

const comparisonMessages = {
  incompatible: 'Шкалы или вопросы несопоставимы.',
  no_pairs: 'Нет сопоставленных пар в выбранном срезе.',
  unavailable: 'Сравнение для этого среза недоступно.',
};

export function ComparisonPanel({ comparison, meta }: { comparison: Comparison; meta: Meta }) {
  if (comparison.status !== 'available') {
    return (
      <section className="panel comparison-panel">
        <SectionTitle title="Сравнение оценок" />
        <p className="inline-state" role="status">{comparison.message ?? comparisonMessages[comparison.status]}</p>
      </section>
    );
  }
  const internFirst = comparison.direction === 'intern_minus_mentor';
  const [first, second] = internFirst ? [meta.roles.intern, meta.roles.mentor] : [meta.roles.mentor, meta.roles.intern];
  return (
    <section className="panel comparison-panel">
      <SectionTitle title="Разница в баллах" extra={<span className="comparison-formula">{first} − {second.toLowerCase()}</span>} />
      <ul className="comparison-cycles">
        {comparison.points.map(({ month, value, nPairs }) => {
          const cycle = meta.cycles.find((item) => item.month === month);
          return (
            <li key={month} className={value == null ? 'comparison-gap' : ''}>
              <span className="comparison-month">{cycle?.shortLabel ?? month}</span>
              <strong className={value == null || value === 0 ? '' : (value > 0) === internFirst ? 'intern-text' : 'mentor-text'}>
                {value == null ? 'Нет оценки' : signed(value)}
              </strong>
              <span className="pair-count">{pairs(nPairs)}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
