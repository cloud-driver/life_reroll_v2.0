'use client';
import { useState } from 'react';
import { allowed, type Page } from '@/lib/game-client';
import { money } from '@/lib/dashboard';
import type { Event, Funding, ClaimAssessment, Claim } from '@/lib/game-types';
import { useResource, type GameModel } from './use-game';
import { EventMedia } from './event-media';
import { FinancePanel } from './finance-panel';
export function EventPanel({ game }: { game: GameModel; onRewind?: () => void }) {
  const r = game.run!,
    params = { run_id: r.id };
  const [pastEvent, setPastEvent] = useState('');
  const activeEvent = r.pending_event_id || pastEvent;
  const history = useResource<Page<Event>>(game, 'D04', params, !r.pending_event_id);
  const event = useResource<Event>(game, 'D05', { ...params, event_id: activeEvent }, !!activeEvent);
  const e = activeEvent ? event.value : history.value?.items.at(-1);
  const choosing = r.status === 'EVENT_PENDING' && e?.id === r.pending_event_id;
  async function act(id: string, body: unknown = {}) {
    await game.perform(async () => {
      await game.write(id, { ...params, event_id: r.pending_event_id! }, body, true);
      await game.refresh();
    });
  }
  return (
    <section
      className={`event-presentation ${e?.hospital_visit ? 'event-medical' : ''}`}
      aria-busy={game.busy || event.loading}
    >
      {!r.pending_event_id && !!history.value?.items.length && (
        <label className="event-history-select">
          事件紀錄
          <select value={pastEvent} onChange={ev => setPastEvent(ev.target.value)}>
            <option value="">最近的事件</option>
            {history.value.items.map(item => (
              <option key={item.id} value={item.id}>
                {item.title}
              </option>
            ))}
          </select>
        </label>
      )}
      {[event.error, history.error].filter(Boolean).map(error => (
        <p role="alert" key={error}>
          {error}
        </p>
      ))}
      {e ? (
        <article key={e.id} className="event-presentation-content">
          <EventMedia event={e} runId={r.id} />
          {e.hospital_visit && (
            <div className="event-medical-speaker">
              醫院服務專員 · {e.hospital_visit.department} · {e.hospital_visit.service}
            </div>
          )}
          <div className="event-presentation-copy">
            <h2>{e.title}</h2>
            <p>{e.narrative}</p>
            {e.outcome && <p>{e.outcome.summary}</p>}
          </div>
          <div className="event-balance-pair" aria-label="事件前後可用資金">
            <div>
              <span>事件前可用資金</span>
              <strong>
                {e.balance_before_minor == null ? (
                  '未記錄'
                ) : (
                  <>
                    {money(e.balance_before_minor)}
                    <small> 元</small>
                  </>
                )}
              </strong>
            </div>
            <span className="event-balance-arrow" aria-hidden="true">
              →
            </span>
            <div>
              <span>事件處理後可用資金</span>
              <strong>
                {e.balance_after_minor == null ? (
                  '尚未決定'
                ) : (
                  <>
                    {money(e.balance_after_minor)}
                    <small> 元</small>
                  </>
                )}
              </strong>
            </div>
          </div>
        </article>
      ) : (
        <p role="status">{event.loading || history.loading ? '正在整理事件…' : '目前沒有事件。'}</p>
      )}
      {choosing && (
        <div className="event-choices" aria-label="事件選擇">
          {e.choices.map(choice => (
            <button
              className="choice-button"
              key={choice.id}
              disabled={game.busy || !!game.retry || !choice.enabled}
              onClick={() => void act('D06', { choice_id: choice.id, confirmed: true })}
            >
              <strong>{choice.label}</strong>
              <span>{choice.description}</span>
              {choice.estimated_cash_cost_minor != null && (
                <small>預估支出 {money(choice.estimated_cash_cost_minor)} 元</small>
              )}
            </button>
          ))}
        </div>
      )}
      {e?.outcome && r.pending_event_id === e.id && <EventClaims game={game} event={e} />}
      {r.status === 'FUNDING' && <FundingActions game={game} />}
      {r.status === 'EVENT_RESULT' && (
        <div className="event-continue">
          <button
            disabled={game.busy || !!game.retry || !allowed(r, 'ACK_EVENT')}
            onClick={() => void act('D07')}
          >
            繼續原本的人生行程 →
          </button>
        </div>
      )}
    </section>
  );
}
function EventClaims({ game, event: e }: { game: GameModel; event: Event }) {
  const r = game.run!,
    params = { run_id: r.id };
  const assessment = useResource<ClaimAssessment>(game, 'F07', { ...params, event_id: e.id });
  const claims = useResource<Page<Claim>>(game, 'F09', params, true, { event_id: e.id });
  const eligible =
    assessment.value?.items.filter(
      i => i.eligible && !claims.value?.items.some(c => c.policy_id === i.policy_id),
    ) ?? [];
  const existing = claims.value?.items ?? [];
  return (
    <section className="play-inline-note">
      <h3>保障與理賠</h3>
      {(assessment.error || claims.error) && <p role="alert">{assessment.error || claims.error}</p>}
      {assessment.loading || claims.loading ? (
        <p>正在核對事故當時的保障…</p>
      ) : (
        <>
          {!eligible.length && !existing.length && <p>這次事件沒有符合條件的保障，費用需自行準備。</p>}
          {eligible.map(item => (
            <div className="resource-row" key={item.policy_id}>
              <span>
                {item.benefit_code} · 預估 {money(item.estimated_minor)} 元
              </span>
              <button
                disabled={game.busy || !!game.retry}
                onClick={() =>
                  void game.perform(async () => {
                    await game.write(
                      'F08',
                      params,
                      {
                        event_id: e.id,
                        policy_id: item.policy_id,
                        benefit_code: item.benefit_code,
                        evidence_ids: item.evidence_ids,
                      },
                      true,
                    );
                    await game.refresh();
                  })
                }
              >
                申請這份保障
              </button>
            </div>
          ))}
          {existing.map(c => (
            <div className="resource-row" key={c.id}>
              <span>
                {c.benefit_code} ·{' '}
                {
                  (
                    {
                      PAID: '已入帳',
                      APPROVED: '核准未入帳',
                      NEEDS_INFO: '待補件',
                      REJECTED: '未核准',
                      SUBMITTED: '審查中',
                    } as Record<string, string>
                  )[c.status]
                }{' '}
                · 已入帳 {money(c.paid_minor)} 元{c.payable_on && ` · 給付日 ${c.payable_on}`}
              </span>
              {c.status === 'NEEDS_INFO' && (
                <button
                  disabled={game.busy}
                  onClick={() =>
                    void game.perform(async () => {
                      await game.write(
                        'F11',
                        { ...params, claim_id: c.id },
                        { evidence_ids: e.evidence.map(x => x.id) },
                        true,
                      );
                      await game.refresh();
                    })
                  }
                >
                  補齊事件證明
                </button>
              )}
            </div>
          ))}
          <p className="muted">核准不等於已入帳。等待期間仍會結算生活費與保費。</p>
        </>
      )}
    </section>
  );
}
function FundingActions({ game }: { game: GameModel }) {
  const r = game.run!,
    params = { run_id: r.id, event_id: r.pending_event_id! };
  const funding = useResource<Funding>(game, 'D08', params);
  async function act(id: string) {
    await game.perform(async () => {
      await game.write(id, params, {}, true);
      await game.refresh();
    });
  }
  return (
    <section className="play-inline-note">
      <h3>準備必要治療費</h3>
      {funding.error && <p role="alert">{funding.error}</p>}
      {funding.value && (
        <>
          <p>
            尚需支付 {money(funding.value.remaining_minor)} 元 · 目前可用{' '}
            {money(funding.value.available_now_minor)} 元
          </p>
          <div className="play-actions">
            <button
              disabled={game.busy || !!game.retry || !funding.value.can_pay}
              onClick={() => void act('D09')}
            >
              支付治療費
            </button>
            {funding.value.can_wait && (
              <button disabled={game.busy || !!game.retry} onClick={() => void act('D10')}>
                等待理賠入帳
              </button>
            )}
            {funding.value.can_confirm_failure && (
              <button
                className="secondary"
                disabled={game.busy || !!game.retry}
                onClick={() => void act('D11')}
              >
                確認無法籌足・結束本輪
              </button>
            )}
          </div>
          <details className="play-details">
            <summary>出售資產、解定存或申請借款</summary>
            <FinancePanel game={game} funding />
          </details>
        </>
      )}
    </section>
  );
}
