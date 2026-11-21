import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, NavLink, Route, Routes, useLocation, useParams, useSearchParams } from 'react-router-dom';
import { createDataClient, isHttp } from './data/client.ts';
import { demoScenarios } from './data/fixtures.ts';
import { ApiError } from './data/types.ts';
import type { DataClient, Intern, Meta, Metric, MetricsQuery, Slice } from './data/types.ts';
import { useRequest } from './data/use-request.ts';
import { dateTime, periodLabel } from './format.ts';
import { FilterBar } from './components/filters.tsx';
import type { FiltersValue } from './components/filters.tsx';
import { ComparisonPanel, CoverageStrip, DistributionChart, ScoresTable, TrendChart } from './components/metrics.tsx';
import { FeedbackSection } from './components/feedback.tsx';
import { Loading, SectionTitle, StatePanel } from './components/ui.tsx';
import { GlassEnabled } from './components/glass.tsx';
import { OverviewDashboard } from './components/dashboard.tsx';

export function App() {
  const [search] = useSearchParams();
  const location = useLocation();
  const scenario = demoScenarios.find(({ id }) => id === search.get('demo'))?.id ?? 'normal';
  const client = useMemo(() => createDataClient(scenario), [scenario]);
  const loadMeta = useCallback((signal: AbortSignal) => client.meta(signal), [client]);
  const request = useRequest(loadMeta);
  const meta = request.status === 'ready' ? request.data : undefined;
  const main = useRef<HTMLElement>(null);
  const previousPath = useRef(location.pathname);

  useEffect(() => {
    if (previousPath.current === location.pathname) return;
    previousPath.current = location.pathname;
    window.scrollTo(0, 0);
    main.current?.focus({ preventScroll: true });
  }, [location.pathname]);

  return (
    <GlassEnabled value={true}>
    <div className="app" data-theme="b">
      <a className="skip-link" href="#main">К содержанию</a>
      <header className="topbar">
        <div className="topbar-inner">
          <Link className="brand" to={{ pathname: '/', search: location.search }} aria-label="МГТС, на обзор программы">
            <span className="brand-mark">МГТС</span>
            <span className="brand-label">{meta?.programLabel ?? 'Программа стажировок'}</span>
          </Link>
          <nav className="main-nav" aria-label="Основная навигация">
            <NavLink to={{ pathname: '/', search: location.search }} end>Обзор</NavLink>
            <NavLink to={{ pathname: '/feedback', search: location.search }}>Обратная связь</NavLink>
          </nav>
          <div className="topbar-tools">
            {(!isHttp || meta?.dataMode === 'demo') && <span className="demo-badge">Демо</span>}
          </div>
        </div>
      </header>
      <main ref={main} id="main" className="main" tabIndex={-1}>
        {request.status === 'loading' && <Loading label="Загружаем программу…" />}
        {request.status === 'error' && (
          <StatePanel type="error" title="Не удалось загрузить программу"
            action={<button className="button button--primary" onClick={request.retry}>Повторить</button>}>
            {request.error instanceof ApiError ? request.error.message : 'Проверьте подключение и повторите запрос.'}
          </StatePanel>
        )}
        {meta && (
          meta.cycles.length === 0 || meta.metrics.length === 0
            ? <StatePanel title="Справочники пока пусты">Циклы и показатели появятся после обновления данных.</StatePanel>
            : <Workspace key={scenario} client={client} meta={meta} search={location.search} />
        )}
      </main>
    </div>
    </GlassEnabled>
  );
}

function Workspace({ client, meta, search }: { client: DataClient; meta: Meta; search: string }) {
  const initial: FiltersValue = useMemo(() => ({
    fromMonth: meta.cycles[0].month,
    toMonth: meta.cycles[meta.cycles.length - 1].month,
    metricId: meta.metrics.some(({ id }) => id === meta.defaultMetricId) ? meta.defaultMetricId : meta.metrics[0].id,
  }), [meta]);
  const [value, setValue] = useState(initial);
  const change = (patch: Partial<FiltersValue>) => setValue((current) => ({ ...current, ...patch }));
  const reset = () => setValue(initial);
  const { fromMonth, toMonth, internId, mentorId, metricId, role, categoryId } = value;
  const slice = useMemo(() => ({ fromMonth, toMonth, internId, mentorId }), [fromMonth, toMonth, internId, mentorId]);
  const feedbackQuery = useMemo(() => ({ ...slice, role, categoryId }), [slice, role, categoryId]);
  const metric = meta.metrics.find(({ id }) => id === metricId)!;

  return (
    <Routes>
      <Route path="/" element={
        <div className="page-stack">
          <PageHeading meta={meta} slice={slice} title="Обзор программы" showSync />
          <FilterBar meta={meta} value={value} screen="overview" onChange={change} onReset={reset} />
          <OverviewDashboard client={client} meta={meta} metric={metric} slice={slice} onReset={reset} onSelect={(metricId) => change({metricId})} />
          <InternDirectory meta={meta} slice={slice} search={search} />
        </div>
      } />
      <Route path="/interns/:internId" element={
        <InternScreen meta={meta} client={client} metric={metric} value={value} change={change} reset={reset} search={search} />
      } />
      <Route path="/feedback" element={
        <div className="page-stack">
          <PageHeading meta={meta} slice={slice} title="Обратная связь" />
          <FilterBar meta={meta} value={value} screen="feedback" onChange={change} onReset={reset} />
          <FeedbackSection client={client} meta={meta} query={feedbackQuery} title="Отзывы участников" showAnalysis />
        </div>
      } />
      <Route path="*" element={
        <StatePanel title="Страница недоступна" action={<Link className="button button--primary" to={{ pathname: '/', search }}>К обзору</Link>}>
          Вернитесь к обзору программы.
        </StatePanel>
      } />
    </Routes>
  );
}

function PageHeading({ meta, slice, title, showSync = false, mentor }: {
  meta: Meta; slice: Slice; title: string; showSync?: boolean; mentor?: string;
}) {
  const syncWarning = showSync && meta.sync.status !== 'current';
  const date = syncWarning && meta.sync.updatedAt ? dateTime(new Date(meta.sync.updatedAt)) : '';
  return (
    <div className="page-heading">
      <div>
        <h1>{title}</h1>
        <div className="period-line" aria-live="polite">
          <span>{periodLabel(meta.cycles, slice)}</span>
          {mentor && <span className="mentor-label">{mentor}</span>}
        </div>
      </div>
      {syncWarning && (
        <div className={`sync sync--${meta.sync.status}`} role="status">
          <span className="sync-dot" aria-hidden="true" />
          <div>
            <strong>{meta.sync.status === 'stale' ? 'Синхронизация устарела' : 'Статус синхронизации неизвестен'}</strong>
            {date && <time dateTime={meta.sync.updatedAt ?? undefined}>{date} МСК</time>}
          </div>
        </div>
      )}
    </div>
  );
}

function MetricsSection({ client, meta, metric, query, onReset, intern = false }: {
  client: DataClient; meta: Meta; metric: Metric; query: MetricsQuery; onReset: () => void; intern?: boolean;
}) {
  const load = useCallback((signal: AbortSignal) => client.metrics(query, signal), [client, query]);
  const request = useRequest(load);
  if (request.status === 'loading') return <Loading label="Загружаем показатели…" />;
  if (request.status === 'error') {
    const error = request.error;
    if (error instanceof ApiError && error.status === 403) {
      return <StatePanel type="locked" title="Показатели недоступны">{error.message}</StatePanel>;
    }
    return (
      <StatePanel type="error" title="Не удалось загрузить показатели"
        action={<button className="button button--primary" onClick={request.retry}>Повторить</button>}>
        {error instanceof ApiError ? error.message : 'Проверьте подключение и повторите запрос.'}
      </StatePanel>
    );
  }
  const data = request.data;
  if (data.status === 'unavailable') {
    return <StatePanel type="locked" title="Показатели недоступны">{data.message ?? 'Доступ к этому срезу ограничен.'}</StatePanel>;
  }
  const empty = data.status === 'empty' || (
    data.coverage.intern.submitted === 0 && data.coverage.mentor.submitted === 0 &&
    !data.series.some((row) => row.points.some(({ value }) => value !== null))
  );
  return (
    <>
      {!intern && <CoverageStrip coverage={data.coverage} meta={meta} />}
      {empty && <StatePanel title="Нет ответов в выбранном срезе"
        action={<button className="button button--subtle" onClick={onReset}>Сбросить фильтры</button>}>
        Выберите другой период или измените фильтры.
      </StatePanel>}
      {intern ? (
        <>
          {!empty && <TrendChart meta={meta} metric={metric} series={data.series} slice={query} showTable={false} />}
          <section className="panel table-panel">
            <SectionTitle title="Оценки по циклам" description={metric.label} />
            <ScoresTable meta={meta} metric={metric} series={data.series} slice={query} label="Оценки по циклам" />
          </section>
        </>
      ) : !empty && (
        <>
          <div className="charts-grid">
            <TrendChart meta={meta} metric={metric} series={data.series} slice={query} />
            <DistributionChart meta={meta} metric={metric} distribution={data.distribution} />
          </div>
          <ComparisonPanel comparison={data.comparison} meta={meta} />
        </>
      )}
    </>
  );
}

function InternDirectory({ meta, slice, search }: { meta: Meta; slice: Slice; search: string }) {
  if (!meta.detailAvailable) {
    return (
      <section className="panel table-panel">
        <SectionTitle title="Карточки стажёров" />
        <p className="inline-state" role="status">Детализация по стажёрам недоступна.</p>
      </section>
    );
  }
  const people = meta.interns.filter(({ id, mentorId }) =>
    (!slice.internId || id === slice.internId) && (!slice.mentorId || mentorId === slice.mentorId));
  return (
    <details className="panel table-panel people-panel">
      <summary>Карточки стажёров</summary>
      {people.length ? (
        <table className="data-table people-table" aria-label="Стажёры программы">
          <thead><tr><th scope="col">Стажёр</th>{meta.filters.mentor && <th scope="col">Наставник</th>}</tr></thead>
          <tbody>{people.map((person) => (
            <tr key={person.id}>
              <th scope="row">
                {person.detailAvailable
                  ? <Link to={{ pathname: `/interns/${encodeURIComponent(person.id)}`, search }}>{person.label}</Link>
                  : <>{person.label} <span className="muted">(карточка недоступна)</span></>}
              </th>
              {meta.filters.mentor && <td>{meta.mentors.find(({ id }) => id === person.mentorId)?.label ?? 'Связь недоступна'}</td>}
            </tr>
          ))}</tbody>
        </table>
      ) : <p className="inline-state" role="status">Нет доступных участников в выбранном срезе.</p>}
    </details>
  );
}

function InternScreen({ meta, client, metric, value, change, reset, search }: {
  meta: Meta; client: DataClient; metric: Metric; value: FiltersValue;
  change: (patch: Partial<FiltersValue>) => void; reset: () => void; search: string;
}) {
  const { internId } = useParams();
  const person = meta.interns.find(({ id }) => id === internId);
  const allowed = meta.detailAvailable && person?.detailAvailable;
  const back = <Link className="back-link" to={{ pathname: '/', search }}><span aria-hidden="true">‹</span> К обзору</Link>;
  if (!allowed || !person) {
    return (
      <div className="page-stack">
        {back}
        <div className="page-heading"><h1>Карточка недоступна</h1></div>
        <StatePanel title="Доступ к детализации ограничен" type="locked">Для этой карточки история оценок и отзывы недоступны.</StatePanel>
      </div>
    );
  }
  return (
    <div className="page-stack">
      {back}
      <InternContent meta={meta} client={client} metric={metric} person={person} value={value} change={change} reset={reset} />
    </div>
  );
}

function InternContent({ meta, client, metric, person, value, change, reset }: {
  meta: Meta; client: DataClient; metric: Metric; person: Intern; value: FiltersValue;
  change: (patch: Partial<FiltersValue>) => void; reset: () => void;
}) {
  const { fromMonth, toMonth, metricId } = value;
  const internId = person.id;
  const query = useMemo(() => ({ fromMonth, toMonth, internId }), [fromMonth, toMonth, internId]);
  const metricsQuery = useMemo(() => ({ ...query, metricId }), [query, metricId]);
  const mentor = meta.filters.mentor ? meta.mentors.find(({ id }) => id === person.mentorId) : undefined;
  return (
    <>
      <PageHeading meta={meta} slice={query} title={person.label} mentor={mentor?.label} />
      <FilterBar meta={meta} value={value} screen="intern" onChange={change} onReset={reset} />
      <MetricsSection client={client} meta={meta} metric={metric} query={metricsQuery} onReset={reset} intern />
      <FeedbackSection client={client} meta={meta} query={query} title="Обратная связь по стажировке" />
    </>
  );
}
