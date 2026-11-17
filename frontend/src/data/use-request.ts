import { useEffect, useState } from 'react';

type Load<T> = (signal: AbortSignal) => Promise<T>;
type RequestState<T> =
  | { status: 'loading' }
  | { status: 'ready'; data: T }
  | { status: 'error'; error: unknown };

export function useRequest<T>(load: Load<T>) {
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{ load: Load<T>; attempt: number; state: RequestState<T> }>();

  useEffect(() => {
    const controller = new AbortController();
    const publish = (state: RequestState<T>) => {
      if (!controller.signal.aborted) setResult({ load, attempt, state });
    };
    load(controller.signal).then(
      (data) => publish({ status: 'ready', data }),
      (error: unknown) => publish({ status: 'error', error }),
    );
    return () => controller.abort();
  }, [load, attempt]);

  const state: RequestState<T> = result?.load === load && result.attempt === attempt
    ? result.state
    : { status: 'loading' };
  return { ...state, retry: () => setAttempt((current) => current + 1) };
}
