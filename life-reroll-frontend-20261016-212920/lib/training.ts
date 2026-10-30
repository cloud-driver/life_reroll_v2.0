import { GameClient, requestKey, type RequestPlan } from './game-client';
export type Source = { id: string; title: string; url: string; locator: string; text?: string };
export type Product = {
  id: string;
  name: string;
  kind: string;
  provider: string;
  facts: string[];
  source: Source;
  simulation_notice: string;
  simulation: Record<string, number>;
};
export type Lesson = {
  id: string;
  topic: string;
  title: string;
  lesson: string;
  prompt: string;
  choices: { id: string; label: string }[];
  correct_id: string;
  explanation: string;
  source_ids: string[];
  loss_minor: number;
  loss_kind: string;
};
export type Rules = {
  horizon_months: number;
  salary_minor: number;
  living_bps: number;
  reserve_months: number;
  market: string;
  drop_bps: number;
  stress_start: number;
  stress_end: number;
  emphasis_topic: string;
  emphasis_multiplier: number;
  guaranteed_topic: boolean;
};
export type Course = {
  id: string;
  title: string;
  audience: string;
  instructions: string;
  product_ids: string[];
  products: Product[];
  material_ids: string[];
  sources: Record<string, Source>;
  events: Lesson[];
  rules: Rules;
  reviewed: boolean;
  unresolved: string[];
  status: string;
  version: number;
  revision: string;
  review_notice?: string;
};
export type Material = {
  id: string;
  name: string;
  status: string;
  message: string;
  source_url: string;
  sections: { id: string; label: string; text: string }[];
};
export type ClassRoom = { id: string; code: string; title: string; course_title: string; status: string };
export type Job = {
  id: string;
  course_id: string;
  course_version: number;
  status: string;
  message: string;
  elapsed_seconds?: number;
  progress_chars?: number;
  sources?: Record<string, Source>;
  result?: {
    events: Lesson[];
    unresolved: string[];
    extracted_facts?: { text: string; source_id: string }[];
  } | null;
};
export type Balances = {
  cash_minor: number;
  savings_minor: number;
  liquidity_minor: number;
  stocks_minor: number;
  policy_accounts_minor: number;
  debt_minor: number;
  unpaid_minor: number;
  net_worth_minor: number;
  receivables_minor: number;
};
export type Policy = {
  id: string;
  name: string;
  kind: string;
  status: string;
  account_minor: number;
  equity_bps: number;
  fees_paid_minor: number;
  waiting_months: number;
  issued_month: number;
};
export type History = {
  event_id: string;
  title: string;
  month: number;
  topic: string;
  correct: boolean;
  explanation: string;
  loss_minor: number;
  loss_kind: string;
  source_ids: string[];
  claim_notice: string;
};
export type TrainingState = {
  version: number;
  status: string;
  month: number;
  age: number;
  location: string;
  course_title: string;
  horizon_months: number;
  scenario_notice: string;
  market_notice: string;
  quality: number;
  lifestyle: string;
  living_minor: number;
  salary_minor: number;
  balances: Balances;
  products: Product[];
  policies: Policy[];
  holdings: Record<string, number>;
  stocks: { id: string; name: string; group: string; price_minor: number }[];
  sources: Record<string, Source>;
  event: Lesson | null;
  history: History[];
  claims: { event_id: string; status: string; due_month: number; approved_minor: number }[];
  ledger: { month: number; kind: string; description: string; amount_minor: number }[];
  report: null | {
    score: number;
    correct: number;
    decisions: number;
    notice: string;
    selection_feedback: string;
  };
};
export type RunSummary = {
  id: string;
  class_title: string;
  state: Pick<TrainingState, 'course_title' | 'status' | 'month' | 'horizon_months'>;
};
export type Run = { id: string; state: TrainingState };
export type Quote = {
  action: string;
  params: Record<string, unknown>;
  before: Balances;
  after: Balances;
  result: Record<string, number | string>;
  notice: string;
  run_version: number;
};
export type CourseTemplate = Pick<
  Course,
  | 'title'
  | 'audience'
  | 'instructions'
  | 'product_ids'
  | 'material_ids'
  | 'rules'
  | 'events'
  | 'reviewed'
  | 'unresolved'
>;
export type Catalog = {
  products: Product[];
  sources: Record<string, Source>;
  base_course: CourseTemplate;
  event_templates: Lesson[];
};
export function createCourseDraft(catalog: Catalog): Course {
  return {
    ...structuredClone(catalog.base_course),
    id: '',
    revision: '',
    status: 'DRAFT',
    version: 0,
    products: structuredClone(catalog.products.filter(p => catalog.base_course.product_ids.includes(p.id))),
    sources: structuredClone(catalog.sources),
  };
}
export const api = new GameClient();
export function plan(
  path: string,
  body?: unknown,
  method = body === undefined ? 'GET' : 'POST',
): RequestPlan {
  return { method, path: '/api/v1/training' + path, body, key: requestKey() };
}
export function get<T>(path: string) {
  return api.send<T>(plan(path));
}
export const money = (v: number) =>
  new Intl.NumberFormat('zh-TW', { maximumFractionDigits: 2 }).format(v / 100) + ' 元';
export const topics: Record<string, string> = {
  NONE: '不指定',
  NEEDS: '需求分析',
  FEES: '費用與保障',
  MARKET: '投資風險',
  LIQUIDITY: '資金周轉',
  PROTECTION: '信用保障',
  ANNUITY: '退休年金',
  LIABILITY: '第三人責任',
  MEDICAL: '醫療保障',
};
export const kinds: Record<string, string> = {
  INVESTMENT_LIFE: '投資型壽險',
  ANNUITY: '變額年金',
  TERM_LIFE: '定期壽險',
  MEDICAL: '一般醫療概念',
  LIABILITY: '一般責任險概念',
};
export async function fileBody(file: File) {
  if (!file.size) throw Error('檔案內容為空，請選擇有內容的教材。');
  if (file.size > 8 * 1024 * 1024) throw Error('單檔不能超過 8 MiB，請縮小檔案或分批匯入。');
  const bytes = new Uint8Array(await file.arrayBuffer());
  let data = '';
  for (let i = 0; i < bytes.length; i += 16384) data += String.fromCharCode(...bytes.subarray(i, i + 16384));
  return { name: file.name, data_base64: btoa(data) };
}
