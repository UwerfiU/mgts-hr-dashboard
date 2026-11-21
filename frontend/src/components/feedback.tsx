import { useCallback } from 'react';
import { ApiError } from '../data/types.ts';
import type { DataClient, FeedbackQuery, Meta } from '../data/types.ts';
import { useRequest } from '../data/use-request.ts';
import { comments } from '../format.ts';
import { Loading, RoleMark, SectionTitle, StatePanel } from './ui.tsx';

export function FeedbackSection({ client, meta, query, title, showAnalysis = false }: {
  client: DataClient;
  meta: Meta;
  query: FeedbackQuery;
  title: string;
  showAnalysis?: boolean;
}) {
  const load = useCallback((signal: AbortSignal) => client.feedback(query, signal), [client, query]);
  const result = useRequest(load);
  const data = result.status === 'ready' ? result.data : undefined;
  const error = result.status === 'error' ? result.error : undefined;
  const denied = data?.status === 'unavailable' || (error instanceof ApiError && error.status === 403);

  return (
    <div className={showAnalysis ? 'feedback-layout' : undefined}>
      <section className="feedback-list">
        <SectionTitle title={title} extra={data?.status === 'ok' && <span className="neutral-chip">{comments(data.items.length)}</span>} />
        {result.status === 'loading' && <Loading label="Загружаем отзывы…" />}
        {denied ? (
          <StatePanel title="Отзывы недоступны" type="locked">{data?.message ?? 'Тексты отзывов скрыты для этого среза.'}</StatePanel>
        ) : result.status === 'error' ? (
          <StatePanel title="Не удалось загрузить отзывы" type="error"
            action={<button className="button button--primary" onClick={result.retry}>Повторить</button>}>
            {error instanceof ApiError ? error.message : 'Проверьте подключение и повторите запрос.'}
          </StatePanel>
        ) : data?.status === 'empty' || (data?.status === 'ok' && data.items.length === 0) ? (
          <StatePanel title="Нет отзывов в выбранном срезе">Измените период или фильтры.</StatePanel>
        ) : data?.status === 'ok' && (
          <ul className="comment-list">
            {data.items.map((item) => {
              const category = meta.categories.find(({ id }) => id === item.categoryId)?.label;
              return (
                <li className="panel comment" key={item.id}>
                  <div className="comment-top">
                    <span className={`role-chip ${item.role}`}><RoleMark role={item.role} variant="dot" />{meta.roles[item.role]}</span>
                    <span className="comment-date">{meta.cycles.find(({ month }) => month === item.month)?.label ?? `Цикл ${item.month}`}</span>
                  </div>
                  <p>{item.text}</p>
                  {category && <span className="category-chip">{category}</span>}
                </li>
              );
            })}
          </ul>
        )}
      </section>
      {showAnalysis && (
        <aside className="panel analysis-panel" aria-labelledby="analysis-title">
          <h2 id="analysis-title">AI-анализ</h2>
          <p>Анализ пока недоступен.</p>
        </aside>
      )}
    </div>
  );
}
