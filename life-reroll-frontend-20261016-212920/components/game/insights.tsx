'use client';
import { useEffect, useRef, useState } from 'react';
import { GameApiError, type GameClient, type RequestPlan } from '@/lib/game-client';
import type { Radar, BranchJob, BranchResult, BranchVariant } from '@/lib/insight-types';
import { money } from '@/lib/dashboard';
import './insights.css';
const levels = { LOW: '緩衝尚可', WATCH: '留意緩衝', HIGH: '收支壓力較高' };
const active = (j: BranchJob | null) => !!j && ['QUEUED', 'RUNNING'].includes(j.status);

export function RiskRadar({
  api,
  runId,
  version,
  onAssets,
  onEvents,
}: {
  api: GameClient;
  runId: string;
  version: number;
  onAssets: () => void;
  onEvents: () => void;
}) {
  const [value, setValue] = useState<Radar | null>(null),
    [error, setError] = useState(''),
    [revision, setRevision] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    setValue(null);
    setError('');
    void api
      .send<Radar>(api.insightPlan(`/api/v1/runs/${runId}/radar`), abort.signal)
      .then(v => {
        if (!abort.signal.aborted) setValue(v);
      })
      .catch(() => {
        if (!abort.signal.aborted) setError('暫時無法讀取雷達，仍可查看遊戲資料。');
      });
    return () => abort.abort();
  }, [api, runId, version, revision]);
  return (
    <section className="insight-card risk-radar" aria-label="危機雷達">
      <div className="insight-heading">
        <h3>危機雷達</h3>
        {value && (
          <span className={`radar-level radar-${value.level.toLowerCase()}`}>{levels[value.level]}</span>
        )}
      </div>
      {value ? (
        <>
          <p className="insight-muted">
            接下來一年 · {value.method === 'MODEL' ? '情境模型判讀' : '目前資料檢查'} · {value.as_of}
          </p>
          <ul className="radar-facts">
            {value.facts.map(f => (
              <li key={f}>{f}</li>
            ))}
          </ul>
          <div className="radar-metrics">
            <div>
              <span>可用資金</span>
              <strong>{money(value.metrics.liquidity_minor)} 元</strong>
            </div>
            <div>
              <span>每月固定支出估算</span>
              <strong>{money(value.metrics.monthly_burden_minor)} 元</strong>
            </div>
          </div>
          <details className="insight-details">
            <summary>判讀依據</summary>
            <p>
              固定支出含生活、扶養、貸款應繳與年保費的月平均；不含突發事件。依目前安排估計資金是否需額外籌措，並未讀取未來事件。
            </p>
            {value.method === 'MODEL' && value.validation ? (
              <p>
                模型由 {value.validation.training_samples.toLocaleString()} 組遊戲情境訓練，以另外{' '}
                {value.validation.validation_samples.toLocaleString()}{' '}
                組情境驗證。判讀可能有誤；低風險也不代表不會遇到危機。
              </p>
            ) : (
              <p>模型目前無法使用，先依目前帳單與收支顯示提醒。</p>
            )}
          </details>
        </>
      ) : (
        <p role="status">{error || '正在讀取目前收支…'}</p>
      )}
      <div className="insight-actions">
        {error && (
          <button className="secondary" onClick={() => setRevision(v => v + 1)}>
            重試讀取
          </button>
        )}
        <button className="secondary" onClick={onAssets}>
          查看資產與收支
        </button>
        {value?.level === 'HIGH' && (
          <button className="secondary" onClick={onEvents}>
            查看事件與理賠
          </button>
        )}
      </div>
    </section>
  );
}

export function useBranches(
  api: GameClient,
  runId: string,
  version: number,
  campaignVersion: number,
  enabled: boolean,
) {
  const [job, setJob] = useState<BranchJob | null>(null),
    [error, setError] = useState(''),
    [posting, setPosting] = useState(false),
    [revision, setRevision] = useState(0);
  const pending = useRef<RequestPlan | null>(null),
    scope = JSON.stringify([runId, version, campaignVersion, enabled]),
    scopeRef = useRef(scope);
  scopeRef.current = scope;
  const alive = useRef(false),
    lock = useRef(false);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  function plan() {
    return api.insightPlan(`/api/v1/runs/${runId}/branches`, 'POST', {
      expected_version: version,
      expected_campaign_version: campaignVersion,
    });
  }
  async function start() {
    if (lock.current) return;
    lock.current = true;
    setPosting(true);
    setError('');
    const current = scope;
    const request = pending.current ?? plan();
    pending.current = request;
    try {
      const value = await api.send<BranchJob>(request);
      if (alive.current && current === scopeRef.current) {
        pending.current = null;
        setJob(value);
      }
    } catch (e) {
      if (alive.current && current === scopeRef.current) {
        setError(e instanceof Error ? e.message : '暫時無法開始分析。');
        if (!(e instanceof GameApiError && e.code === 'CONNECTION_UNCERTAIN')) pending.current = null;
      }
    } finally {
      lock.current = false;
      if (alive.current && current === scopeRef.current) setPosting(false);
    }
  }
  useEffect(() => {
    const abort = new AbortController();
    setJob(null);
    setError('');
    pending.current = null;
    setPosting(false);
    if (!enabled) return;
    void (async () => {
      try {
        const value = await api.send<BranchJob | null>(
          api.insightPlan(`/api/v1/runs/${runId}/branches`),
          abort.signal,
        );
        if (abort.signal.aborted) return;
        if (value) setJob(value);
        else void start();
      } catch (e) {
        if (!abort.signal.aborted) setError(e instanceof Error ? e.message : '暫時無法讀取分析。');
      }
    })();
    return () => abort.abort();
  }, [scope, api, revision]);
  useEffect(() => {
    if (!enabled || !job || !active(job)) return;
    const abort = new AbortController();
    const id = job.id;
    void (async () => {
      try {
        while (!abort.signal.aborted) {
          await new Promise<void>((resolve, reject) => {
            const t = setTimeout(done, 1000);
            function done() {
              abort.signal.removeEventListener('abort', stop);
              resolve();
            }
            function stop() {
              clearTimeout(t);
              reject(new DOMException('Aborted', 'AbortError'));
            }
            abort.signal.addEventListener('abort', stop, { once: true });
          });
          const v = await api.send<BranchJob>(api.insightPlan(`/api/v1/insights/jobs/${id}`), abort.signal);
          if (abort.signal.aborted) return;
          setJob(v);
          if (!active(v)) return;
        }
      } catch {
        if (!abort.signal.aborted) setError('連線中斷，分析可能仍在進行。重新連線會接回同一筆結果。');
      }
    })();
    return () => abort.abort();
  }, [api, scope, job?.id, job?.status, revision]);
  async function cancel() {
    if (!job || lock.current) return;
    lock.current = true;
    setPosting(true);
    setError('');
    const current = scope;
    try {
      const v = await api.send<BranchJob>(
        api.insightPlan(`/api/v1/insights/jobs/${job.id}/cancel`, 'POST', {}),
      );
      if (alive.current && current === scopeRef.current) setJob(v);
    } catch {
      if (alive.current && current === scopeRef.current) setError('尚未確認停止結果，請重新連線查看。');
    } finally {
      lock.current = false;
      if (alive.current && current === scopeRef.current) setPosting(false);
    }
  }
  return {
    job,
    error,
    posting,
    pending: !!pending.current,
    start,
    cancel,
    reconnect: () => setRevision(v => v + 1),
  };
}
export function BranchProgress({
  analysis,
  onCompare,
}: {
  analysis: ReturnType<typeof useBranches>;
  onCompare?: () => void;
}) {
  const { job, error, posting, pending, start, cancel, reconnect } = analysis;
  return (
    <section className="insight-card branch-progress" aria-label="人生分岔預演">
      <div className="insight-heading">
        <h3>人生分岔預演</h3>
        {job && (
          <span className="insight-muted">
            {job.completed_points}／{job.total_points} 個日期
          </span>
        )}
      </div>
      <p>比較回溯後五年的資金壓力與生活品質，幫你挑選下一輪起點。</p>
      {job && active(job) && (
        <progress max={job.total_points} value={job.completed_points} aria-label="日期分析進度" />
      )}
      <p className="insight-muted" role="status">
        {job?.notice ?? (posting ? '已送出分析，仍可先選擇日期。' : '正在讀取分析紀錄…')}
      </p>
      {error && <p role="alert">{error}</p>}
      <div className="insight-actions">
        {onCompare && (
          <button className="secondary" onClick={onCompare}>
            比較回溯日期
          </button>
        )}
        {job && active(job) && (
          <button className="secondary" disabled={posting} onClick={() => void cancel()}>
            停止分析
          </button>
        )}
        {(!job || ['FAILED', 'CANCELLED'].includes(job.status)) && (
          <button className="secondary" disabled={posting} onClick={() => void start()}>
            {pending ? '確認原分析／安全重試' : job ? '繼續分析' : '開始比較'}
          </button>
        )}
        {error && (
          <button className="secondary" disabled={posting} onClick={reconnect}>
            重新連線
          </button>
        )}
      </div>
      <details className="insight-details">
        <summary>這些結果怎麼看？</summary>
        <p>
          每個日期、每種安排各跑 {job?.samples ?? 24}{' '}
          組相同的假設情境。重要事件固定，其他事件與市場重新抽樣，不使用原人生的未來亂數。
        </p>
        <p>
          統一選擇費用較低的事件選項、申請可用理賠；治療不足時依序等待理賠、賣股、解定存、借款。未新增保單或投資。精簡生活會減少生活費，也影響生活品質。
        </p>
        <p>
          區間取樣本的第 10～90
          百分位；少量情境無法涵蓋所有可能。提早結束時截至當時；理賠等待可能延長最多三個月。借款不是收入，跨日期的差異也不代表因果效果。實際遊玩與選擇可能不同。
        </p>
      </details>
    </section>
  );
}
function compactAmount(value: number) {
  return `${value >= 0 ? '＋' : '−'}${(Math.abs(value) / 1000000).toLocaleString('zh-TW', { maximumFractionDigits: 1 })} 萬`;
}
function VariantRange({ value, label }: { value: BranchVariant; label: string }) {
  return (
    <div className="branch-range">
      <h4>{label}</h4>
      <p>
        淨資產變化：{money(value.net_change_minor.low)}～{money(value.net_change_minor.high)} 元
      </p>
      <p>
        最低可用資金：{money(value.minimum_liquidity_minor.low)}～{money(value.minimum_liquidity_minor.high)}{' '}
        元
      </p>
      <p>
        提早結束 {value.ended_early_count}／{value.samples} 組 · 實際推演 {value.duration_months.min}～
        {value.duration_months.max} 個月
      </p>
    </div>
  );
}
export function BranchOutlook({ result, pending }: { result?: BranchResult; pending: boolean }) {
  const a = result?.variants.CURRENT,
    b = result?.variants.BASIC;
  return (
    <section className="branch-outlook" aria-label="此日期的分岔預演">
      {a && b ? (
        <>
          <table className="branch-table">
            <caption>接下來五年 · {a.samples} 組情境</caption>
            <thead>
              <tr>
                <th scope="col">生活方案</th>
                <th scope="col">維持原方案</th>
                <th scope="col">改採精簡</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <th scope="row">需籌資／欠款</th>
                <td>
                  {a.shortage_count}／{a.samples}
                </td>
                <td>
                  {b.shortage_count}／{b.samples}
                </td>
              </tr>
              <tr>
                <th scope="row">淨資產變化</th>
                <td>{compactAmount(a.net_change_minor.median)}</td>
                <td>{compactAmount(b.net_change_minor.median)}</td>
              </tr>
              <tr>
                <th scope="row">生活品質</th>
                <td>{a.quality.median}／100</td>
                <td>{b.quality.median}／100</td>
              </tr>
            </tbody>
          </table>
          <p className="insight-muted">資產與品質顯示中位數；實際選擇可能不同。</p>
          <details className="insight-details">
            <summary>查看金額與情境範圍</summary>
            <VariantRange label="維持原生活方案" value={a} />
            <VariantRange label="改採精簡生活" value={b} />
          </details>
        </>
      ) : (
        <p className="insight-muted">
          {pending ? '這個日期仍在背景分析，可先選擇起點。' : '尚無這個日期的預演，仍可直接選擇起點。'}
        </p>
      )}
    </section>
  );
}
