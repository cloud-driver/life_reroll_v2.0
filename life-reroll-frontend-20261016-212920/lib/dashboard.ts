import { requestKey } from './game-client';
// Public RunState subset from backend/data/schema_reference.json. Monetary
// fields are integer minor units (分); finance calculations stay on the backend.
export type Balances = {
  cash_minor: number;
  savings_minor: number;
  term_principal_minor: number;
  stocks_market_value_minor: number;
  policy_cash_value_minor: number;
  receivables_minor: number;
  liabilities_minor: number;
  net_worth_minor: number;
  immediate_liquidity_minor: number;
  negative_years: number;
};
export type DashboardRun = {
  id: string;
  run_index: number;
  age: number;
  sim_date: string;
  status: string;
  quality?: number;
  pending_event_id: string | null;
  character: { name: string; occupation: string; employment_status: string; monthly_salary_minor: number };
  balances: Balances;
};
export const DEMO_RUN: DashboardRun = {
  id: 'demo',
  run_index: 1,
  age: 27,
  sim_date: '2026-01-01',
  status: 'EXPLORING',
  quality: 72,
  pending_event_id: null,
  character: {
    name: '城市生活的第一天',
    occupation: '上班族',
    employment_status: 'EMPLOYED',
    monthly_salary_minor: 4500000,
  },
  balances: {
    cash_minor: 8000000,
    savings_minor: 12000000,
    term_principal_minor: 0,
    stocks_market_value_minor: 6000000,
    policy_cash_value_minor: 0,
    receivables_minor: 0,
    liabilities_minor: 3000000,
    net_worth_minor: 23000000,
    immediate_liquidity_minor: 20000000,
    negative_years: 0,
  },
};
export const STATUS_LABELS: Record<string, string> = {
  INITIAL_ALLOCATION: '初始資產配置',
  EXPLORING: '自由探索',
  ADVANCING: '人生推進中',
  EVENT_PENDING: '事件等待處理',
  FUNDING: '籌資中',
  EVENT_RESULT: '確認事件結果',
  TURN_REVIEW: '回顧本輪人生',
  ENDED: '本輪已結束',
};
export const money = (minor: number) =>
  Number.isFinite(minor)
    ? new Intl.NumberFormat('zh-TW', { maximumFractionDigits: 2 }).format(minor / 100)
    : '—';
export function parseRun(value: unknown): DashboardRun {
  const r = value as DashboardRun;
  if (
    !r ||
    typeof r.id !== 'string' ||
    !Number.isInteger(r.age) ||
    !Number.isInteger(r.run_index) ||
    typeof r.sim_date !== 'string' ||
    typeof r.status !== 'string' ||
    !r.character ||
    typeof r.character.name !== 'string' ||
    typeof r.character.occupation !== 'string' ||
    !Number.isFinite(r.character.monthly_salary_minor) ||
    !r.balances
  )
    throw Error('後端人生資料格式不符');
  for (const key of Object.keys(DEMO_RUN.balances) as (keyof Balances)[])
    if (!Number.isSafeInteger(r.balances[key])) throw Error('後端資產資料格式不符');
  if (r.quality !== undefined && (!Number.isFinite(r.quality) || r.quality < 0 || r.quality > 100))
    throw Error('生活品質數值格式不符');
  return r;
}
export async function backendRequest<T>(
  path: string,
  options: { method?: string; body?: unknown; csrf?: string; signal?: AbortSignal } = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';
  if (options.method && options.method !== 'GET') {
    headers['Idempotency-Key'] = requestKey();
    if (options.csrf) headers['X-CSRF-Token'] = options.csrf;
  }
  const response = await fetch(`/api/v1${path}`, {
    method: options.method ?? 'GET',
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    credentials: 'same-origin',
    signal: options.signal ?? AbortSignal.timeout(10000),
  });
  const payload = (await response.json().catch(() => null)) as {
    data?: T;
    error?: { message?: string };
  } | null;
  if (!response.ok) throw Error(payload?.error?.message ?? `後端回應 ${response.status}`);
  if (!payload || !('data' in payload)) throw Error('無法讀取遊戲 API，請確認本地後端已啟動');
  return payload.data as T;
}
