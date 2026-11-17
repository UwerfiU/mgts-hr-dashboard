export type Role = 'intern' | 'mentor';
export type DataMode = 'demo' | 'live';

export interface Cycle {
  month: number;
  label: string;
  shortLabel: string;
}

export interface Scale {
  min: number;
  max: number;
  step: number;
}

export interface Metric {
  id: string;
  label: string;
  scales: Partial<Record<Role, Scale>>;
}

export interface Person {
  id: string;
  label: string;
}

export interface Intern extends Person {
  mentorId?: string;
  detailAvailable: boolean;
}

export interface Meta {
  dataMode: DataMode;
  programLabel: string;
  cycles: Cycle[];
  metrics: Metric[];
  defaultMetricId: string;
  roles: Record<Role, string>;
  interns: Intern[];
  mentors: Person[];
  categories: Person[];
  filters: { intern: boolean; mentor: boolean; role: boolean; category: boolean };
  detailAvailable: boolean;
  aiAvailable: boolean;
  sync: { status: 'current' | 'stale' | 'unknown'; updatedAt: string | null };
}

export interface Slice {
  fromMonth: number;
  toMonth: number;
  internId?: string;
  mentorId?: string;
}

export interface MetricsQuery extends Slice {
  metricId: string;
}

export interface FeedbackQuery extends Slice {
  role?: Role;
  categoryId?: string;
}

export interface Coverage {
  submitted: number;
  expected: number | null;
  percent?: number | null;
}

export interface Point {
  month: number;
  value: number | null;
  n: number;
}

export interface Series {
  role: Role;
  points: Point[];
}

export interface Distribution {
  role: Role;
  buckets: { score: number; count: number }[];
}

export interface ComparisonPoint {
  month: number;
  value: number | null;
  nPairs: number;
}

export type Comparison =
  | { status: 'available'; direction: 'intern_minus_mentor' | 'mentor_minus_intern'; points: ComparisonPoint[] }
  | { status: 'no_pairs' | 'incompatible' | 'unavailable'; message?: string };

export interface Metrics {
  dataMode: DataMode;
  metricId: string;
  status?: 'ok' | 'empty' | 'unavailable';
  message?: string;
  coverage: Record<Role, Coverage>;
  series: Series[];
  distribution: Distribution[];
  comparison: Comparison;
}

export interface FeedbackItem {
  id: string;
  month: number;
  role: Role;
  categoryId?: string;
  text: string;
}

export interface Feedback {
  dataMode: DataMode;
  status: 'ok' | 'empty' | 'unavailable';
  items: FeedbackItem[];
  message?: string;
}

export interface DataClient {
  meta(signal?: AbortSignal): Promise<Meta>;
  metrics(query: MetricsQuery, signal?: AbortSignal): Promise<Metrics>;
  feedback(query: FeedbackQuery, signal?: AbortSignal): Promise<Feedback>;
}

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}
