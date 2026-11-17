import { useCallback, useRef } from 'react';
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { loadDashboardMetrics } from '../data/dashboard.ts';
import type { DashboardResult } from '../data/dashboard.ts';
import { useRequest } from '../data/use-request.ts';
import { ApiError } from '../data/types.ts';
import type { DataClient, Meta, Metric, Slice } from '../data/types.ts';
import { answers, number, roles } from '../format.ts';
import { ComparisonPanel, CoverageStrip, DistributionChart, TrendChart } from './metrics.tsx';
import { GlassLayer } from './glass.tsx';
import { Loading, RoleMark, StatePanel } from './ui.tsx';

function MetricWidget({ meta, metric, result, slice, selected, onSelect }: {
  meta: Meta; metric: Metric; result: DashboardResult; slice: Slice; selected: boolean; onSelect: () => void;
}) {
  const data = result.status === 'ready' ? result.data : undefined;
  const denied = data?.status === 'unavailable' || (result.status === 'error' && result.error instanceof ApiError && result.error.status === 403);
  const available = data && !denied && data.status !== 'empty' && data.series.some(({ points }) => points.some(({ value }) => value !== null));
  const activeRoles = roles.filter((role) => metric.scales[role]);
  const rows = meta.cycles.filter(({ month }) => month >= slice.fromMonth && month <= slice.toMonth).map((cycle) => ({
    label: cycle.shortLabel,
    ...Object.fromEntries(activeRoles.map((role) => [role, data?.series.find((series) => series.role === role)?.points.find(({ month }) => month === cycle.month)?.value ?? null])),
    ...Object.fromEntries(activeRoles.map((role) => [`${role}Count`, data?.series.find((series) => series.role === role)?.points.find(({ month }) => month === cycle.month)?.n ?? 0])),
  }));
  const last = rows.at(-1) as Record<string, number | string | null> | undefined;
  const split = activeRoles.length === 2 && (metric.scales.intern?.max !== metric.scales.mentor?.max || metric.scales.intern?.min !== metric.scales.mentor?.min);
  return (
    <section className="panel metric-widget" data-selected={selected} aria-label={`Показатель: ${metric.label}`}>
      <GlassLayer />
      <button className="widget-open" type="button" onClick={onSelect} aria-label={`Подробнее: ${metric.label}`} aria-pressed={selected}>
        <span>{metric.label}</span><span className="widget-arrow" aria-hidden="true">↗</span>
      </button>
      {available ? <>
        <div className="widget-values">
          {activeRoles.map((role) => <div className={role} key={role}>
            <RoleMark role={role} variant="dot" />
            <span className="sr-only">{meta.roles[role]}: </span>
            <strong>{last?.[role] == null ? <><span aria-hidden="true">—</span><span className="sr-only">Нет оценки</span></> : number(Number(last[role]))}</strong>
            <span className="widget-scale">/{metric.scales[role]!.max}</span>
          </div>)}
        </div>
        <div className="widget-chart" aria-label={`История показателя ${metric.label}`}>
          <ResponsiveContainer width="100%" height="100%" minWidth={0} initialDimension={{width:260,height:120}}>
            <LineChart data={rows} accessibilityLayer={false} margin={{top:8,right:8,bottom:0,left:0}}>
              <CartesianGrid vertical={false} stroke="var(--grid)" strokeDasharray="2 5" />
              <XAxis dataKey="label" axisLine={false} tickLine={false} tickMargin={8} interval="preserveStartEnd" minTickGap={4} height={24} />
              {activeRoles.map((role, index) => <YAxis key={role} yAxisId={role} hide={index > 0 && !split}
                orientation={index === 1 ? 'right' : 'left'} width={20} tickMargin={4}
                domain={[metric.scales[role]!.min, metric.scales[role]!.max]} ticks={[metric.scales[role]!.min, metric.scales[role]!.max]}
                axisLine={false} tickLine={false} />)}
              <Tooltip filterNull={false} content={({active,payload})=>{
                const row = payload?.[0]?.payload;
                return active && row ? <div className="chart-tooltip"><strong>{row.label}</strong>
                  {activeRoles.map((role)=><div key={role}><RoleMark role={role}/>{meta.roles[role]} <b>{row[role] == null ? 'Нет оценки' : number(row[role])}</b><span>{answers(row[`${role}Count`])}</span></div>)}
                </div> : null;
              }} />
              {activeRoles.map((role) => <Line key={role} dataKey={role} name={meta.roles[role]} yAxisId={role}
                type="linear" connectNulls={false} stroke={`var(--${role})`} strokeWidth={2.5}
                strokeDasharray={role === 'mentor' ? '4 4' : undefined} dot={{r:2.5,strokeWidth:1.5,fill:'var(--surface)'}}
                activeDot={{r:4}} isAnimationActive={false} />)}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </> : <p className={`widget-state ${result.status === 'error' && !denied ? 'widget-error' : ''}`}>
        {denied ? 'Данные недоступны' : result.status === 'error' ? 'Не удалось загрузить' : 'Нет оценок за период'}
      </p>}
    </section>
  );
}

export function OverviewDashboard({ client, meta, metric, slice, onSelect, onReset }: {
  client: DataClient; meta: Meta; metric: Metric; slice: Slice; onSelect: (metricId: string) => void; onReset: () => void;
}) {
  const load = useCallback((signal: AbortSignal) => loadDashboardMetrics(client, meta.metrics, slice, signal), [client, meta.metrics, slice]);
  const request = useRequest(load);
  const detail = useRef<HTMLDivElement>(null);
  if (request.status === 'loading') return <Loading label="Загружаем показатели…" />;
  if (request.status === 'error') return <StatePanel title="Не удалось загрузить показатели" type="error"
    action={<button className="button button--primary" onClick={request.retry}>Повторить</button>}>Повторите запрос.</StatePanel>;
  const selected = request.data.find(({ metricId }) => metricId === metric.id)!;
  const data = selected.status === 'ready' ? selected.data : undefined;
  const denied = data?.status === 'unavailable' || (selected.status === 'error' && selected.error instanceof ApiError && selected.error.status === 403);
  const allEmpty = request.data.every((result) => result.status === 'ready' && result.data.status === 'empty');
  const empty = data?.status === 'empty';
  const visibleMetrics = meta.metrics.slice(0, 5);
  if (!visibleMetrics.some(({id}) => id === metric.id) && visibleMetrics.length) visibleMetrics[visibleMetrics.length - 1] = metric;
  const select = (metricId: string) => {
    onSelect(metricId);
    detail.current?.focus({preventScroll:true});
    detail.current?.scrollIntoView({block:'start',behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});
  };
  return <>
    {data && !denied && <CoverageStrip coverage={data.coverage} meta={meta} />}
    {!allEmpty && <section className="metric-catalog" aria-label="Все показатели программы">
      <div className="catalog-heading">
        <h2>Показатели программы</h2>
        <div className="catalog-context">
          <span>{meta.cycles.find(({month}) => month === slice.toMonth)?.label}</span>
          <ul className="legend">{roles.map((role)=><li key={role}><RoleMark role={role}/>{meta.roles[role]}</li>)}</ul>
        </div>
      </div>
      <div className="metric-grid">
        {visibleMetrics.map((item) => <MetricWidget key={item.id} meta={meta} metric={item}
          result={request.data.find(({metricId})=>metricId===item.id)!} slice={slice}
          selected={metric.id===item.id} onSelect={()=>select(item.id)} />)}
      </div>
    </section>}
    <div id="metric-detail" ref={detail} className="metric-detail" tabIndex={-1} aria-label={`Детали: ${metric.label}`}>
      {denied ? <StatePanel title="Показатели недоступны" type="locked">Доступ к этому срезу ограничен.</StatePanel>
        : selected.status === 'error' ? <StatePanel title="Не удалось загрузить показатели" type="error"
          action={<button className="button button--primary" onClick={request.retry}>Повторить</button>}>Повторите запрос или выберите другой показатель.</StatePanel>
        : empty ? <StatePanel title="Нет ответов в выбранном срезе"
          action={<button className="button button--subtle" onClick={onReset}>Сбросить фильтры</button>}>Выберите другой период или измените фильтры.</StatePanel>
        : data && <>
          <div className="charts-grid">
            <TrendChart meta={meta} metric={metric} series={data.series} slice={slice} />
            <DistributionChart meta={meta} metric={metric} distribution={data.distribution} />
          </div>
          <ComparisonPanel comparison={data.comparison} meta={meta} />
        </>}
    </div>
  </>;
}
