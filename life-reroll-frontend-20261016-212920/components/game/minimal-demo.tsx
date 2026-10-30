'use client';
import { Brand } from '@/components/brand';
import './game.css';
import './workspace.css';
import { useEffect, useRef, useState } from 'react';
import { DESTINATIONS, HOME, type DestinationId, type Point } from '@/lib/map-data';
import {
  advanceDemo,
  demoSnapshot,
  initialDemo,
  readDemoSave,
  DEMO_SAVE_KEY,
  type DemoState,
  type DemoTurn,
} from '@/lib/minimal-demo';
import { money } from '@/lib/dashboard';
import { buildTrip, sampleAtTime } from '@/lib/travel';
import { CoachWidget } from './coach';
import { GameClient } from '@/lib/game-client';
import { GameMap, type MapTrip } from './game-map';
import { DiceInteraction } from './dice-interaction';
import { AdvanceReview } from './advance-review';
import { EventMedia } from './event-media';
import { GameDialog } from './game-dialog';
import { TutorialCoach, TutorialLaunch, useGuidedTour } from './tutorial';
import { demoTutorialSteps } from '@/lib/tutorial';
export function MinimalDemo() {
  const coachApi = useRef(new GameClient()).current;
  const [state, setState] = useState<DemoState>(initialDemo),
    [ready, setReady] = useState(false),
    [turn, setTurn] = useState<DemoTurn | null>(null),
    [trip, setTrip] = useState<MapTrip | null>(null),
    [location, setLocation] = useState<DestinationId | 'home'>('home'),
    [parked, setParked] = useState<Point>(HOME),
    [heading, setHeading] = useState(-30),
    [rolling, setRolling] = useState(false),
    [roll, setRoll] = useState<number | null>(null),
    [message, setMessage] = useState(''),
    [panelRequest, setPanel] = useState(''),
    [tab, setTab] = useState('summary'),
    [pending, setPending] = useState(false);
  const locked = useRef(false),
    alive = useRef(false),
    stateRef = useRef(state),
    lastRoll = useRef<{ before: DemoState; years: number } | null>(null);
  stateRef.current = state;
  useEffect(() => {
    alive.current = true;
    try {
      const raw = localStorage.getItem(DEMO_SAVE_KEY),
        parsed = JSON.parse(raw ?? 'null');
      const saved = readDemoSave(JSON.stringify(parsed?.state ?? parsed));
      setState(saved);
      stateRef.current = saved;
      if (parsed?.lastRoll) {
        const before = readDemoSave(JSON.stringify(parsed.lastRoll.before)),
          next = advanceDemo(before, parsed.lastRoll.years);
        if (JSON.stringify(next.state) === JSON.stringify(saved)) {
          lastRoll.current = { before, years: parsed.lastRoll.years };
          setTurn(next);
          setRoll(parsed.lastRoll.years);
          if (parsed.pending) {
            setPending(true);
            setPanel('review');
          }
        }
      }
    } catch {
      setMessage('無法恢復上次結算，本次仍可展示。');
    }
    setReady(true);
    return () => {
      alive.current = false;
    };
  }, []);
  function save(next: DemoState, needsReview: boolean) {
    try {
      localStorage.setItem(
        DEMO_SAVE_KEY,
        JSON.stringify({ state: next, lastRoll: lastRoll.current, pending: needsReview }),
      );
    } catch {
      setMessage('本次操作已完成，但瀏覽器無法保存進度。');
    }
  }
  const snapshot = demoSnapshot(state),
    busy = rolling || !!trip;
  const tour = useGuidedTour({
    ready: ready && !busy,
    completed: false,
    storageKey: 'life-reroll:tutorial:demo:v1',
    buildSteps: () => demoTutorialSteps(!pending),
  });
  const panel = tour.active ? (trip ? '' : (tour.step?.panel ?? '')) : panelRequest;
  useEffect(() => {
    const target =
      tour.step?.scene === 'FINANCE' ? 'finance' : tour.step?.scene === 'HOME' ? 'home' : undefined;
    if (!tour.active || !target || target === location || busy || pending || !ready) return;
    if (location !== 'home') move(location, 'return');
    else if (target === 'finance') move('finance', 'outbound');
  }, [tour.active, tour.step?.id, location, busy, pending, ready]);
  function finishTutorial() {
    if (busy) return;
    tour.stop();
    setPanel(pending ? 'review' : '');
    if (location !== 'home' && !pending) move(location, 'return');
  }
  const tutorialWaiting = !!(
    tour.step?.scene && location !== (tour.step.scene === 'FINANCE' ? 'finance' : 'home')
  );
  const tutorialGuide =
    tour.active && tour.step ? (
      <TutorialCoach
        key={tour.step.id}
        step={tour.step}
        index={tour.index}
        total={tour.total}
        busy={busy || tutorialWaiting}
        onBack={() => tour.go(-1)}
        onNext={() => (tour.index === tour.total - 1 ? finishTutorial() : tour.go(1))}
        onExit={finishTutorial}
      />
    ) : undefined;
  async function dice() {
    if (locked.current || pending || location !== 'home' || !ready) return;
    locked.current = true;
    setPanel('');
    setRolling(true);
    setRoll(null);
    setMessage('');
    try {
      const years = 1 + Math.floor(Math.random() * 6),
        duration = matchMedia('(prefers-reduced-motion: reduce)').matches ? 100 : 650;
      await new Promise(resolve => setTimeout(resolve, duration));
      if (!alive.current) return;
      setRoll(years);
      await new Promise(resolve => setTimeout(resolve, duration));
      if (!alive.current) return;
      const before = stateRef.current,
        next = advanceDemo(before, years);
      lastRoll.current = { before, years };
      setState(next.state);
      stateRef.current = next.state;
      setTurn(next);
      setPending(true);
      save(next.state, true);
      setTab('summary');
      setPanel('review');
    } finally {
      locked.current = false;
      if (alive.current) setRolling(false);
    }
  }
  function move(id: DestinationId, direction: 'outbound' | 'return') {
    if (locked.current || pending || !ready) return;
    locked.current = true;
    setPanel('');
    setTrip({ id, direction, nonce: Date.now() });
    setMessage('');
  }
  function arrive() {
    if (!trip) return;
    const last = sampleAtTime(buildTrip(trip.id, trip.direction), 1);
    setParked(last.position);
    setHeading(last.heading);
    setLocation(trip.direction === 'return' ? 'home' : trip.id);
    setTrip(null);
    locked.current = false;
  }
  const titles: Record<string, string> = {
    overview: '人生總覽',
    assets: '資產與收支',
    events: '事件紀錄',
    review: '上次結算',
    settings: '設定與教學',
  };
  return (
    <main className="play-shell game-workspace">
      {rolling && <DiceInteraction value={roll} />}
      <header className="workspace-header">
        <strong>
          <Brand />
        </strong>
        <span>
          {state.age} 歲 · {state.year} 年
        </span>
        <span>免登入展示資料</span>
        <a href="/full">後端整合版</a>
      </header>
      <div className="workspace-body">
        <nav className="workspace-nav" aria-label="查閱儀表板">
          {Object.entries(titles).map(([id, title], i) => (
            <button
              key={id}
              title={title}
              aria-label={title}
              disabled={rolling}
              onClick={() => {
                setTab('summary');
                setPanel(id);
              }}
            >
              {['◉', '▤', '▧', '▦', '⚙'][i]}
            </button>
          ))}
        </nav>
        <section className="workspace-stage">
          <div className="workspace-hud">
            <div>
              <span>可用資金</span>
              <strong>{money(snapshot.balances.immediate_liquidity_minor)} 元</strong>
            </div>
            <div>
              <span>淨資產</span>
              <strong>{money(snapshot.balances.net_worth_minor)} 元</strong>
            </div>
            <div>
              <span>已完成擲骰</span>
              <strong>{state.rolls} 次</strong>
            </div>
          </div>
          <div className="workspace-map-viewport">
            {trip || location === 'home' ? (
              <GameMap
                trip={trip}
                parked={parked}
                parkedHeading={heading}
                onArrive={arrive}
                reducedMotion={tour.active}
              />
            ) : (
              <section key={location} className="workspace-scene minimal-destination">
                <img src={DESTINATIONS[location].scene} alt={DESTINATIONS[location].label} />
                <div>
                  <h2>已抵達{DESTINATIONS[location].label}</h2>
                  <p>此版本展示場域與車輛移動。完整業務操作請使用後端整合版。</p>
                </div>
              </section>
            )}
          </div>
          <p className="workspace-caption">
            {trip ? '車輛正在沿道路行駛。' : '從選單查看資料，在家擲骰或選擇目的地。重新整理後從家恢復。'}
          </p>
        </section>
        <aside className="workspace-controls">
          <section className="play-card">
            <span className="eyebrow">01 · DICE</span>
            <h2>推進人生</h2>
            <button
              className="roll-button"
              disabled={!ready || busy || pending || location !== 'home'}
              onClick={() => void dice()}
            >
              ⚄ 擲骰
            </button>
            <p>
              {pending
                ? '請先確認上次結算。'
                : location !== 'home'
                  ? '請先回家再擲骰。'
                  : '骰出 1～6 年，完成後自動開啟結算。'}
            </p>
            {pending && (
              <button className="secondary" onClick={() => setPanel('review')}>
                查看待確認結算
              </button>
            )}
          </section>
          <section className="play-card travel-controls">
            <span className="eyebrow">02 · MOVE</span>
            <h2>選擇目的地</h2>
            {location === 'home' ? (
              (Object.keys(DESTINATIONS) as DestinationId[]).map(id => (
                <button key={id} disabled={!ready || busy || pending} onClick={() => move(id, 'outbound')}>
                  {DESTINATIONS[id].action}
                </button>
              ))
            ) : (
              <button disabled={!ready || busy || pending} onClick={() => move(location, 'return')}>
                開車回家
              </button>
            )}
          </section>
        </aside>
      </div>
      {message && (
        <div className="workspace-notice" role="status">
          {message}
        </div>
      )}
      {tour.active && !panel && (
        <GameDialog title="遊玩教學" coachOnly guide={tutorialGuide} onClose={finishTutorial} />
      )}
      {panel && !rolling && (
        <GameDialog
          key={panel}
          title={titles[panel]}
          drawer={panel !== 'review'}
          wide={panel === 'review'}
          guide={tutorialGuide}
          onClose={tour.active ? finishTutorial : () => setPanel('')}
        >
          {!tour.active && panel !== 'settings' && (
            <CoachWidget
              key={panel}
              api={coachApi}
              version={state.rolls}
              topic={
                panel === 'assets'
                  ? 'finance'
                  : panel === 'events'
                    ? 'event'
                    : panel === 'review'
                      ? 'review'
                      : 'overview'
              }
              demo={{
                age: state.age,
                year: state.year,
                rolls: state.rolls,
                cash: state.cash,
                savings: state.savings,
                stocks: snapshot.balances.stocks_market_value_minor,
              }}
            />
          )}
          {panel === 'settings' && (
            <>
              <p>Demo 進度保存在目前瀏覽器。</p>
              <TutorialLaunch demo onStart={tour.start} disabled={busy} />
            </>
          )}
          {panel === 'overview' && (
            <>
              <h2>下一段人生，從這裡出發</h2>
              <p>
                {state.age} 歲 · {state.year} 年 · 已擲骰 {state.rolls} 次
              </p>
              <p>這是純展示模式，資料保存在目前瀏覽器。</p>
              <p>
                固定假設：月收入 50,000 元、月生活費 30,000 元、年保費 12,000 元。投資與事故均為模擬規則。
              </p>
            </>
          )}
          {panel === 'assets' && (
            <>
              <dl className="play-data-list">
                {[
                  ['現金', snapshot.balances.cash_minor],
                  ['活存', snapshot.balances.savings_minor],
                  ['投資市值', snapshot.balances.stocks_market_value_minor],
                  ['淨資產', snapshot.balances.net_worth_minor],
                ].map(([label, value]) => (
                  <div key={label}>
                    <dt>{label}</dt>
                    <dd>{money(value as number)} 元</dd>
                  </div>
                ))}
              </dl>
              {snapshot.holdings.map(h => (
                <p key={h.stock_id}>
                  {h.stock_id} · {h.quantity} 股 · 市值 {money(h.market_value_minor)} 元
                </p>
              ))}
              <p>展示版提供最近一次結算；完整收支明細請使用後端版。</p>
            </>
          )}
          {panel === 'events' && (
            <>
              {turn?.events.length ? (
                turn.events.map(e => (
                  <div key={e.id}>
                    <EventMedia event={e} runId="minimal-demo" />
                    <h3>{e.title}</h3>
                    <p>{e.narrative}</p>
                    <p>{e.outcome?.summary}</p>
                  </div>
                ))
              ) : (
                <p>最近一次擲骰沒有事件，或尚未擲骰。</p>
              )}
            </>
          )}
          {panel === 'review' &&
            (turn ? (
              <>
                <div className="play-actions">
                  {[
                    ['summary', '本次摘要'],
                    ['details', '資產與事件明細'],
                  ].map(([id, label]) => (
                    <button key={id} className={tab === id ? '' : 'secondary'} onClick={() => setTab(id)}>
                      {label}
                    </button>
                  ))}
                </div>
                {tab === 'summary' ? (
                  <>
                    <h2>人生前進了 {turn.advance.roll_value} 年</h2>
                    <p>
                      {turn.advance.from_date} → {turn.advance.current_date}
                    </p>
                    <div className="review-flow-grid">
                      <div>
                        <span>淨資產變化</span>
                        <strong>{money(turn.advance.summary!.net_worth_change_minor)} 元</strong>
                      </div>
                      <div>
                        <span>目前可用資金</span>
                        <strong>{money(snapshot.balances.immediate_liquidity_minor)} 元</strong>
                      </div>
                      <div>
                        <span>期間事件</span>
                        <strong>{turn.events.length} 件</strong>
                      </div>
                      <div>
                        <span>其中理賠入帳</span>
                        <strong>{money(turn.advance.summary!.claims_paid_minor)} 元</strong>
                      </div>
                    </div>
                    <p>固定展示範例，非真實帳務或實際理賠。</p>
                  </>
                ) : (
                  <AdvanceReview
                    advance={turn.advance}
                    events={turn.events}
                    claims={turn.claims}
                    onEvent={() => setPanel('events')}
                    canRewind={false}
                    showRewind={false}
                    sourceLabel="本機展示資料"
                  />
                )}
                <div className="settlement-actions">
                  <button
                    onClick={() => {
                      setPending(false);
                      save(stateRef.current, false);
                      setPanel('');
                    }}
                  >
                    {pending ? '確認結算並回到地圖' : '回到地圖'}
                  </button>
                </div>
              </>
            ) : (
              <p>尚未擲骰。在家擲骰後會顯示結算。</p>
            ))}
        </GameDialog>
      )}
    </main>
  );
}
