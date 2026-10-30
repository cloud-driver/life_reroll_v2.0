'use client';
import { useEffect, useId, useRef, useState } from 'react';
import { GameApiError, type GameClient, type RequestPlan } from '@/lib/game-client';
import type { CoachJob, CoachTopic, DemoCoachSnapshot } from '@/lib/coach-types';
import './coach.css';
const suggestions: Record<CoachTopic, string[]> = {
  overview: ['我目前的資金安排，有什麼需要留意？', '生活品質與預算可以怎麼取捨？'],
  event: ['目前這些選項，各有什麼取捨？', '有保險，為什麼仍需要準備可用資金？'],
  finance: ['可用資金與淨資產有什麼不同？', '定存、股票與保費，會怎麼影響可用資金？'],
  insurance: ['核准理賠與實際入帳，有什麼不同？', '目前的保障與等待期，有什麼需要留意？'],
  review: ['這次的資產變化，有什麼值得留意？', '下一段人生可以先注意什麼？'],
};
const waiting = (job: CoachJob | null) => !!job && ['QUEUED', 'RUNNING'].includes(job.status);
function answerExcerpt(lines: string[]) {
  const first = lines[0] ?? '';
  if (first.length <= 80) return first + '…';
  const head = first.slice(0, 80),
    boundary = Math.max(...['。', '！', '？', '；', '，'].map(mark => head.lastIndexOf(mark)));
  // Prefer a complete clause; never leave a cut number at the end of the excerpt.
  const excerpt = first
    .slice(0, boundary >= 32 ? boundary + 1 : 80)
    .replace(/[，；]\s*$/, '')
    .replace(/\s*[+-]?\d[\d,.]*\s*$/, '');
  return excerpt.trimEnd() + '…';
}
function pause(signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const timer = setTimeout(done, 1200);
    function done() {
      signal.removeEventListener('abort', abort);
      resolve();
    }
    function abort() {
      clearTimeout(timer);
      reject(new DOMException('Aborted', 'AbortError'));
    }
    signal.addEventListener('abort', abort, { once: true });
    if (signal.aborted) abort();
  });
}
export function CoachWidget({
  api,
  runId,
  version,
  topic = 'overview',
  review = false,
  demo,
  autoOpen = false,
}: {
  api: GameClient;
  runId?: string;
  version: number;
  topic?: CoachTopic;
  review?: boolean;
  demo?: DemoCoachSnapshot;
  autoOpen?: boolean;
}) {
  const id = useId(),
    [open, setOpen] = useState(autoOpen),
    [job, setJob] = useState<CoachJob | null>(null),
    [input, setInput] = useState(''),
    [posting, setPosting] = useState(false),
    [loading, setLoading] = useState(false),
    [error, setError] = useState(''),
    [pollError, setPollError] = useState(''),
    [pollRevision, setPollRevision] = useState(0),
    [answerExpanded, setAnswerExpanded] = useState(false);
  const mounted = useRef(false),
    pending = useRef<RequestPlan | null>(null),
    scopeRef = useRef(''),
    lock = useRef(false),
    cardRef = useRef<HTMLElement>(null),
    inputRef = useRef<HTMLTextAreaElement>(null);
  const kind = review ? 'REVIEW' : 'COACH',
    scope = JSON.stringify([api.apiBase, runId, version, topic, kind, demo]);
  scopeRef.current = scope;
  const cacheKey = 'life-reroll:coach-job:' + scope,
    active = waiting(job),
    stale =
      !!job &&
      (job.run_version !== version ||
        job.run_id !== (demo ? 'demo' : runId) ||
        job.kind !== kind ||
        job.topic !== topic);
  const answerLines = job?.text.split(/\n+/).filter(Boolean) ?? [],
    longAnswer = (job?.text.length ?? 0) > 120 || answerLines.length > 3;
  useEffect(() => setAnswerExpanded(false), [job?.id]);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  function apply(value: CoachJob) {
    setJob(value);
    if (demo)
      try {
        sessionStorage.setItem(cacheKey, value.id);
      } catch {}
  }
  function plan(question: string, retry = false) {
    return api.coachPlan(
      demo ? '/api/v1/coach/demo' : `/api/v1/runs/${encodeURIComponent(runId!)}/coach`,
      'POST',
      { kind, topic, question, retry, ...(demo ? { snapshot: demo } : { expected_version: version }) },
      !!demo,
    );
  }
  async function send(question: string, retry = false, original?: RequestPlan, reveal = true) {
    if (lock.current || (!question.trim() && !review && !original)) return;
    if (reveal) {
      inputRef.current?.blur();
      cardRef.current?.scrollIntoView({ block: 'start' });
    }
    lock.current = true;
    setPosting(true);
    setError('');
    setPollError('');
    const currentScope = scope,
      request = original ?? plan(question, retry);
    pending.current = request;
    try {
      const value = await api.send<CoachJob>(request);
      if (mounted.current && scopeRef.current === currentScope) {
        apply(value);
        setInput('');
        pending.current = null;
      }
    } catch (e) {
      if (mounted.current && scopeRef.current === currentScope) {
        setError(e instanceof Error ? e.message : '暫時無法詢問教練。');
        if (!(e instanceof GameApiError && e.code === 'CONNECTION_UNCERTAIN')) pending.current = null;
      }
    } finally {
      lock.current = false;
      if (mounted.current && scopeRef.current === currentScope) setPosting(false);
    }
  }
  useEffect(() => {
    setJob(null);
    setInput('');
    setError('');
    setPollError('');
    setPosting(false);
    pending.current = null;
    if (!open) return;
    const abort = new AbortController();
    setLoading(true);
    void (async () => {
      try {
        let value: CoachJob | null = null;
        if (demo) {
          let saved = '';
          try {
            saved = sessionStorage.getItem(cacheKey) ?? '';
          } catch {}
          if (saved)
            try {
              value = await api.send<CoachJob>(
                api.coachPlan(`/api/v1/coach/jobs/${saved}`, 'GET', undefined, true),
                abort.signal,
              );
            } catch (e) {
              if (abort.signal.aborted) throw e;
              try {
                sessionStorage.removeItem(cacheKey);
              } catch {}
            }
          if (!value)
            value = await api.send<CoachJob | null>(
              api.coachPlan('/api/v1/coach/demo/latest', 'GET', undefined, true),
              abort.signal,
            );
        } else
          value = await api.send<CoachJob | null>(
            api.coachPlan(`/api/v1/runs/${encodeURIComponent(runId!)}/coach?kind=${kind}&topic=${topic}`),
            abort.signal,
          );
        if (abort.signal.aborted) return;
        if (value) apply(value);
        else if (review) void send('', false, undefined, false);
      } catch (e) {
        if (!abort.signal.aborted) setError(e instanceof Error ? e.message : '暫時無法讀取教練回覆。');
      } finally {
        if (!abort.signal.aborted) setLoading(false);
      }
    })();
    return () => abort.abort();
  }, [scope, open]);
  useEffect(() => {
    if (!open || !job || !waiting(job)) return;
    const abort = new AbortController(),
      jobId = job.id;
    setPollError('');
    void (async () => {
      try {
        while (!abort.signal.aborted) {
          await pause(abort.signal);
          const value = await api.send<CoachJob>(
            api.coachPlan(`/api/v1/coach/jobs/${jobId}`, 'GET', undefined, !!demo),
            abort.signal,
          );
          if (abort.signal.aborted) return;
          apply(value);
          if (!waiting(value)) return;
        }
      } catch {
        if (!abort.signal.aborted) setPollError('連線暫時中斷，回答可能仍在進行。重新連線會讀取同一筆回答。');
      }
    })();
    return () => abort.abort();
  }, [open, job?.id, job?.status, pollRevision, scope]);
  async function stop() {
    if (!job || lock.current) return;
    lock.current = true;
    setPosting(true);
    setError('');
    const currentScope = scope;
    try {
      const value = await api.send<CoachJob>(
        api.coachPlan(`/api/v1/coach/jobs/${job.id}/cancel`, 'POST', {}, !!demo),
      );
      if (mounted.current && scopeRef.current === currentScope) apply(value);
    } catch {
      if (mounted.current && scopeRef.current === currentScope)
        setError('尚未確認停止結果，請重新連線查看。');
    } finally {
      lock.current = false;
      if (mounted.current && scopeRef.current === currentScope) setPosting(false);
    }
  }
  function toggleAnswer() {
    if (answerExpanded)
      requestAnimationFrame(() =>
        cardRef.current?.querySelector('.coach-answer')?.scrollIntoView({ block: 'nearest' }),
      );
    setAnswerExpanded(value => !value);
  }
  return (
    <section
      ref={cardRef}
      className={`coach-card ${open ? 'coach-is-open' : ''}`}
      aria-label={review ? 'AI 人生回顧' : 'AI 人生教練'}
    >
      <button
        type="button"
        className="secondary coach-toggle"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
      >
        <span className="coach-mark" aria-hidden="true">
          ✧
        </span>
        <span>
          <strong>{review ? 'AI 人生回顧' : '問問人生教練'}</strong>
          <small>{review ? '回看選擇與學習收穫' : '依目前進度，聊聊選擇與取捨'}</small>
        </span>
        <span aria-hidden="true">{open ? '−' : '＋'}</span>
      </button>
      {open && (
        <div className="coach-content" id={id}>
          {active && (
            <div className="coach-actions coach-running-actions">
              <button type="button" className="secondary" disabled={posting} onClick={() => void stop()}>
                停止回答
              </button>
              <small>收合後仍會繼續，稍後可再查看。</small>
            </div>
          )}
          {(loading || posting || active) && (
            <p className="coach-progress" role="status">
              {loading ? '正在讀取教練紀錄…' : posting ? '正在確認請求…' : job?.progress}{' '}
              {active && '可以先繼續遊玩。'}
            </p>
          )}
          {job && (
            <>
              <p className="coach-context">
                {job.context_label} ·{' '}
                {job.status === 'COMPLETE'
                  ? 'Qwen 人生教練'
                  : job.status === 'FALLBACK'
                    ? '遊戲資料說明'
                    : job.status === 'CANCELLED'
                      ? '已停止'
                      : '正在準備'}
              </p>
              {stale && <p className="coach-notice">這是先前進度的回答；完成後可重新詢問目前的情況。</p>}
              {job.kind === 'COACH' && <p className="coach-question">{job.question}</p>}
              {job.notice && (
                <p className="coach-notice" role="status">
                  {job.notice}
                </p>
              )}
              {job.text && (
                <>
                  <div
                    id={`${id}-answer`}
                    className={`coach-answer ${longAnswer && !answerExpanded ? 'coach-answer-brief' : ''}`}
                    role="region"
                    aria-label="教練回覆"
                    tabIndex={0}
                  >
                    {longAnswer && !answerExpanded ? (
                      <p>{answerExcerpt(answerLines)}</p>
                    ) : (
                      answerLines.map((line, i) => <p key={i}>{line}</p>)
                    )}
                  </div>
                  {longAnswer && (
                    <button
                      type="button"
                      className="secondary coach-answer-more"
                      aria-expanded={answerExpanded}
                      aria-controls={`${id}-answer`}
                      onClick={toggleAnswer}
                    >
                      {answerExpanded ? '收合完整說明' : '展開完整說明'}
                    </button>
                  )}
                </>
              )}
              {job.sources.length > 0 && (
                <details key={job.id} className="coach-sources">
                  <summary>查看本次參考資料（{job.sources.length}）</summary>
                  <ol>
                    {job.sources.map((source, i) => (
                      <li key={i}>
                        <strong>{source.label}</strong>
                        <p>{source.text}</p>
                      </li>
                    ))}
                  </ol>
                </details>
              )}
            </>
          )}
          {error && (
            <p className="coach-notice" role="alert">
              {error}
            </p>
          )}
          {pollError && (
            <p className="coach-notice" role="alert">
              {pollError}
            </p>
          )}
          {pollError && (
            <button type="button" className="secondary" onClick={() => setPollRevision(v => v + 1)}>
              重新連線
            </button>
          )}
          {pending.current && error && (
            <button
              type="button"
              className="secondary"
              disabled={posting}
              onClick={() => void send('', false, pending.current!)}
            >
              確認原詢問／安全重試
            </button>
          )}
          {!active &&
            (review ? (
              <div className="coach-actions">
                <button
                  type="button"
                  className="secondary"
                  disabled={posting || loading}
                  onClick={() => void send('', true)}
                >
                  {job ? '重新產生回顧' : '產生本輪回顧'}
                </button>
              </div>
            ) : (
              <>
                <div className="coach-suggestions">
                  {suggestions[topic].map(question => (
                    <button
                      type="button"
                      className="secondary"
                      key={question}
                      disabled={posting || loading || !!pending.current}
                      onClick={() => void send(question, job?.status === 'FALLBACK')}
                    >
                      {question}
                    </button>
                  ))}
                </div>
                <form
                  className="coach-form"
                  onSubmit={e => {
                    e.preventDefault();
                    void send(input, true);
                  }}
                >
                  <label htmlFor={`${id}-question`}>
                    想問什麼？
                    <textarea
                      ref={inputRef}
                      id={`${id}-question`}
                      value={input}
                      maxLength={240}
                      rows={2}
                      placeholder="例如：這次選擇會占用哪些資金？"
                      disabled={posting || loading}
                      onChange={e => setInput(e.target.value)}
                    />
                  </label>
                  <div className="coach-actions">
                    <small>{input.length}／240</small>
                    <button type="submit" disabled={!input.trim() || posting || loading || !!pending.current}>
                      詢問教練
                    </button>
                  </div>
                </form>
              </>
            ))}
          <p className="coach-footnote">解釋供學習參考，請核對遊戲資料；操作仍由你確認。</p>
        </div>
      )}
    </section>
  );
}
