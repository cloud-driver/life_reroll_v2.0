import registry from './contracts/operations.json';
import type { Campaign, RunState, Session, Job, MutationReceipt } from './game-types';
export { registry };
export type RequestPlan = {
  method: string;
  path: string;
  body?: unknown;
  key: string;
  headers?: Record<string, string>;
};
const messages: Record<string, string> = {
  STALE_VERSION: '進度已在其他頁面更新，請重讀後重新確認。',
  QUOTE_STALE: '資產已改變，請重新取得確認單。',
  QUOTE_EXPIRED: '確認單已過期，請重新預覽。',
  UNAUTHENTICATED: '登入已失效，請重新登入。',
  CSRF_INVALID: '登入狀態已改變，請重讀後再操作。',
  INVALID_CREDENTIALS: '信箱或密碼不正確。',
  FORBIDDEN: '目前帳號不符合此操作條件，請確認服務設定與帳號狀態。',
  ACTIVE_CAMPAIGN_EXISTS: '已有進行中的人生，請繼續目前遊戲。',
  ACTION_NOT_ALLOWED: '目前狀態不允許這項操作。',
  STATE_CONFLICT: '目前人生狀態已改變，請重新讀取。',
  CLAIM_DUPLICATE: '這份保障已申請過本事件理賠。',
  INSUFFICIENT_FUNDS: '本次操作可用的帳戶餘額不足，請檢查使用的帳戶與金額。',
  RATE_LIMITED: '操作太頻繁，請稍後再試。',
};
Object.assign(messages, {
  NOT_FOUND: '找不到可操作的這筆資料，請重新選擇。',
  INSUFFICIENT_SHARES: '持有股數不足，請調低出售股數。',
  LOAN_LIMIT_EXCEEDED: '貸款金額超過目前收入可承擔的上限。',
  AMOUNT_EXCEEDS_DUE: '付款金額超過尚未清償的金額。',
  AGE_NOT_ELIGIBLE: '目前年齡不符合這項保障的投保條件。',
  DUPLICATE_COVERAGE: '已有生效中的同類保障，不能重複投保。',
});
export const errorMessage = (code: string, detail?: string) =>
  (typeof detail === 'string' ? detail.trim() : '') ||
  messages[code] ||
  '操作未能完成，請稍後再試；若持續發生，請聯絡專案團隊。';
export class GameApiError extends Error {
  constructor(
    public code: string,
    public status: number,
    detail?: string,
    public details?: Record<string, unknown>,
  ) {
    super(errorMessage(code, detail));
  }
}
declare global {
  interface Window {
    LIFE_CONFIG?: { apiBase?: string };
  }
}
export function configuredApiBase(): string {
  const raw = typeof window === 'undefined' ? '' : (window.LIFE_CONFIG?.apiBase?.trim() ?? '');
  if (!raw) return '';
  const url = new URL(raw);
  if (
    !['https:', 'http:'].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    !['', '/', '/api/v1', '/api/v1/'].includes(url.pathname)
  )
    throw Error('config.js 的 apiBase 須為後端的 http(s) 網址，可含 /api/v1。');
  return url.origin;
}
export function requestKey() {
  return typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : Array.from(crypto.getRandomValues(new Uint8Array(24)), b => b.toString(16).padStart(2, '0')).join('');
}
export class GameClient {
  csrf = '';
  devToken = '';
  private token = '';
  readonly apiBase: string;
  private storageKey: string;
  private configurationError = '';
  constructor(
    private transport: typeof fetch = (input, init) => globalThis.fetch(input, init),
    apiBase?: string,
  ) {
    try {
      this.apiBase = (apiBase ?? configuredApiBase()).replace(/\/$/, '');
    } catch (e) {
      this.apiBase = '';
      this.configurationError = e instanceof Error ? e.message : 'API 網址設定錯誤';
    }
    this.storageKey = 'life-reroll:session:' + this.apiBase;
    try {
      this.token = sessionStorage.getItem(this.storageKey) ?? '';
    } catch {
      /* cookie fallback on same origin */
    }
  }
  private rememberToken(value: string) {
    this.token = value;
    try {
      if (value) sessionStorage.setItem(this.storageKey, value);
      else sessionStorage.removeItem(this.storageKey);
    } catch {}
  }
  url(path: string) {
    if (!path.startsWith('/api/v1/') || path.includes('://') || path.includes('..'))
      throw Error('無效的 API 路徑');
    return this.apiBase + path;
  }
  async download(path: string): Promise<Blob> {
    if (this.configurationError) throw new GameApiError('API_CONFIG_INVALID', 400, this.configurationError);
    let res: Response;
    try {
      res = await this.transport(this.url(path), {
        headers: this.token ? { Authorization: 'Bearer ' + this.token } : {},
        credentials: this.apiBase ? 'omit' : 'same-origin',
        signal: AbortSignal.timeout(30000),
      });
    } catch {
      throw new GameApiError('BACKEND_UNAVAILABLE', 0, '報告下載連線中斷，請確認網路後重新下載。');
    }
    if (res.status === 401) this.rememberToken('');
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      throw new GameApiError(
        body?.error?.code ?? 'HTTP_ERROR',
        res.status,
        body?.error?.message ??
          (res.status === 401 ? '登入已失效，請重新登入後下載。' : '報告下載失敗，請稍後重試。'),
      );
    }
    if (!res.headers.get('content-type')?.includes('application/pdf'))
      throw new GameApiError('INVALID_RESPONSE', 502, '報告格式不正確，請稍後重新下載。');
    try {
      return await res.blob();
    } catch {
      throw new GameApiError('BACKEND_UNAVAILABLE', 0, '報告下載未完成，請重新下載。');
    }
  }
  // Keep native fetch bound to the browser global, not this GameClient instance.

  plan(
    id: string,
    params: Record<string, string> = {},
    body?: unknown,
    query: Record<string, string> = {},
  ): RequestPlan {
    const op = registry.find(x => x.id === id);
    if (!op) throw Error('Unknown operation ' + id);
    const path = op.path.replace(/\{([^}]+)\}/g, (_, key: string) => {
      if (!params[key]) throw Error('Missing ' + key);
      return encodeURIComponent(params[key]);
    });
    const search = new URLSearchParams(query).toString();
    return { method: op.method, path: path + (search ? '?' + search : ''), body, key: requestKey() };
  }
  async send<T>(plan: RequestPlan, signal?: AbortSignal): Promise<T> {
    if (this.configurationError) throw new GameApiError('API_CONFIG_INVALID', 400, this.configurationError);
    const headers: Record<string, string> = { Accept: 'application/json', ...plan.headers };
    if (this.token) headers.Authorization = 'Bearer ' + this.token;
    if (plan.method !== 'GET') {
      headers['Idempotency-Key'] = plan.key;
      if (this.csrf) headers['X-CSRF-Token'] = this.csrf;
      if (plan.body !== undefined) headers['Content-Type'] = 'application/json';
    }
    let response: Response;
    try {
      response = await this.transport(this.url(plan.path), {
        method: plan.method,
        headers,
        credentials: this.apiBase ? 'omit' : 'same-origin',
        body: plan.body === undefined ? undefined : JSON.stringify(plan.body),
        signal: signal ?? AbortSignal.timeout(20000),
      });
    } catch (e) {
      if (signal?.aborted) throw e;
      throw new GameApiError(
        plan.method === 'GET' ? 'BACKEND_UNAVAILABLE' : 'CONNECTION_UNCERTAIN',
        0,
        plan.method === 'GET'
          ? '讀取資料時連線中斷，請確認網路後重試。'
          : '連線中斷。操作可能已提交，請先重讀進度；重試會沿用原請求識別。',
      );
    }
    const sessionToken = response.headers.get('X-Session-Token');
    if (sessionToken) this.rememberToken(sessionToken);
    if (response.status === 401) this.rememberToken('');
    if (response.status === 204 && plan.path === '/api/v1/auth/logout') this.rememberToken('');
    const token = response.headers.get('X-Dev-Verification-Token');
    if (token) this.devToken = token;
    if (response.status === 204) return undefined as T;
    const envelope = (await response.json().catch(() => null)) as {
      data: T;
      error?: { code: string; message: string; details?: Record<string, unknown> };
    } | null;
    // This explicit preflight error rolls back account creation before any email is queued.
    if (
      !response.ok &&
      response.status >= 500 &&
      plan.method !== 'GET' &&
      envelope?.error?.code !== 'MAIL_NOT_CONFIGURED'
    )
      throw new GameApiError('CONNECTION_UNCERTAIN', 0, '伺服器未能確認操作結果，請使用原操作安全重試。');
    if (!response.ok)
      throw new GameApiError(
        envelope?.error?.code ?? 'HTTP_ERROR',
        response.status,
        envelope?.error?.message ?? '後端暫時無法使用',
        envelope?.error?.details,
      );
    if (!envelope || !Object.hasOwn(envelope, 'data'))
      throw new GameApiError(
        plan.method === 'GET' ? 'BACKEND_UNAVAILABLE' : 'CONNECTION_UNCERTAIN',
        0,
        plan.method === 'GET'
          ? '資料回應格式不正確，請稍後重新讀取。'
          : '目前無法確認操作結果，請沿用原操作安全重試。',
      );
    if (plan.path === '/api/v1/auth/logout') this.rememberToken('');
    return envelope.data;
  }
  call<T>(
    id: string,
    params: Record<string, string> = {},
    body?: unknown,
    query: Record<string, string> = {},
    signal?: AbortSignal,
  ) {
    return this.send<T>(this.plan(id, params, body, query), signal);
  }
  insightPlan(path: string, method = 'GET', body?: unknown): RequestPlan {
    if (!/^\/api\/v1\/(runs\/[a-z0-9]+\/(radar|branches)|insights\/jobs\/[a-z0-9]+(?:\/cancel)?)$/.test(path))
      throw Error('無效的分析路徑');
    return { path, method, body, key: requestKey() };
  }
  private demoCoachToken = '';
  coachPlan(path: string, method = 'GET', body?: unknown, demo = false): RequestPlan {
    if (
      !/^\/api\/v1\/(runs\/[^/]+\/coach|coach\/(demo(?:\/latest)?|jobs\/[a-z0-9]+(?:\/cancel)?))(?:\?|$)/.test(
        path,
      )
    )
      throw Error('無效的教練路徑');
    let headers: Record<string, string> | undefined;
    if (demo) {
      const storageKey = 'life-reroll:coach-demo:' + this.apiBase;
      let token = '';
      try {
        token = sessionStorage.getItem(storageKey) ?? '';
      } catch {}
      if (!/^[0-9a-f]{64}$/.test(token)) {
        token = Array.from(crypto.getRandomValues(new Uint8Array(32)), x =>
          x.toString(16).padStart(2, '0'),
        ).join('');
        try {
          sessionStorage.setItem(storageKey, token);
        } catch {}
      }
      this.demoCoachToken = this.demoCoachToken || token;
      headers = { 'X-Demo-Coach-Token': this.demoCoachToken };
    }
    return { path, method, body, key: requestKey(), headers };
  }
  async session(signal?: AbortSignal) {
    const session = await this.call<Session>('A03', {}, undefined, {}, signal);
    this.csrf = session.csrf_token;
    return session;
  }
  async current(
    signal?: AbortSignal,
  ): Promise<{ session: Session; campaign: Campaign | null; run: RunState | null }> {
    const session = await this.session(signal);
    if (!session.user) return { session, campaign: null, run: null };
    let campaign = await this.call<Campaign | null>('C02', {}, undefined, {}, signal);
    if (!campaign) {
      const history = await this.call<{ items: Campaign[] }>('C03', {}, undefined, {}, signal);
      campaign = history.items[0] ?? null;
    }
    const run = campaign?.current_run_id
      ? await this.call<RunState>('C06', { run_id: campaign.current_run_id }, undefined, {}, signal)
      : null;
    return { session, campaign, run };
  }
  async waitJob(job: Job, onProgress: (job: Job) => void, signal?: AbortSignal): Promise<Job> {
    let current = job;
    while (!['SUCCEEDED', 'FAILED'].includes(current.status)) {
      onProgress(current);
      await new Promise<void>((resolve, reject) => {
        const timer = setTimeout(done, Math.max(500, Math.min(current.poll_after_ms || 2000, 10000)));
        function done() {
          signal?.removeEventListener('abort', abort);
          resolve();
        }
        function abort() {
          clearTimeout(timer);
          reject(new DOMException('Aborted', 'AbortError'));
        }
        signal?.addEventListener('abort', abort, { once: true });
        if (signal?.aborted) abort();
      });
      current = await this.call<Job>('C12', { job_id: current.id }, undefined, {}, signal);
    }
    onProgress(current);
    return current;
  }
}
export const allowed = (run: RunState | null, action: string) =>
  !!run?.allowed_actions.some(a => a.action === action && a.enabled);
export function receiptRun(value: unknown): RunState | null {
  const v = value as Partial<MutationReceipt> | null;
  return v?.run?.id ? v.run : null;
}

export type Page<T> = { items: T[]; next_cursor: string | null; total: number };
