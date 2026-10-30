'use client';
import { allowed } from '@/lib/game-client';
import { DESTINATIONS, type DestinationId } from '@/lib/map-data';
import type { GameModel } from './use-game';
export function RoutineScene({
  game,
  at,
  onMove,
  onRoll,
  onPanel,
}: {
  game: GameModel;
  at?: DestinationId;
  onMove: (scene: string) => void;
  onRoll: () => void;
  onPanel: (panel: string) => void;
}) {
  const r = game.run!,
    home = r.scene_id === 'HOME',
    phase = r.daily_phase ?? (home ? 'HOME_READY' : 'FREE_TIME');
  const initial = r.status === 'INITIAL_ALLOCATION';
  const eventPending = ['EVENT_PENDING', 'FUNDING', 'EVENT_RESULT', 'ADVANCING'].includes(r.status);
  const review = r.status === 'TURN_REVIEW',
    ended = r.status === 'ENDED';
  const outdated = !r.daily_phase;
  async function homeAction() {
    if (eventPending) {
      onPanel('event');
      return;
    }
    if (review) {
      onPanel('review');
      return;
    }
    if (ended) {
      onPanel('reports');
      return;
    }
    if (initial) {
      await game.perform(async () => {
        await game.write('C07', { run_id: r.id }, {}, true);
        await game.refresh();
      }, '配置已確認，現在可以在家擲骰');
      return;
    }
    if (phase === 'WORK_REQUIRED') {
      onMove('WORK');
      return;
    }
    onRoll();
  }
  const homeLabel = outdated
    ? '請先重新啟動後端'
    : initial
      ? '確認配置・開始人生'
      : eventPending
        ? '查看事件・繼續行程'
        : review
          ? '查看本次結算'
          : ended
            ? '查看人生回顧'
            : phase === 'WORK_REQUIRED'
              ? '出發上班 →'
              : '⚄ 擲骰';
  const homeDisabled =
    game.busy ||
    outdated ||
    (!initial &&
      !eventPending &&
      !review &&
      !ended &&
      !allowed(r, phase === 'WORK_REQUIRED' ? 'SCENE_TRANSITION' : 'ROLL'));
  const homeFree = home && r.status === 'EXPLORING' && phase === 'HOME_READY' && !outdated;
  async function finishWork() {
    const ok = await game.perform(async () => {
      await game.write('C08', { run_id: r.id }, { scene_id: 'WORK', complete_work: true }, true);
      await game.refresh();
    }, '下班了，先回家再安排自由時間');
    if (ok) onMove('HOME');
  }
  return (
    <section
      key={home ? 'home' : at}
      className={`workspace-scene routine-scene ${home ? 'routine-home' : ''}`}
    >
      <img
        src={home ? '/scene-home.webp' : DESTINATIONS[at!].scene}
        alt={home ? '陽光灑入的溫暖房間' : DESTINATIONS[at!].label}
      />
      <div className="routine-scene-shade" />
      <div className="routine-scene-copy">
        <span className="eyebrow">
          {home ? 'HOME · 歡迎回家' : at === 'work' ? 'WORK · 工作場域' : 'FREE TIME · 自由時間'}
        </span>
        <h2>
          {home
            ? phase === 'WORK_REQUIRED'
              ? '準備出門上班'
              : '回到自己的步調'
            : at === 'work'
              ? phase === 'WORKING'
                ? '專心完成今天的工作'
                : '辛苦了，下班時間'
              : DESTINATIONS[at!].label}
        </h2>
        <p>
          {outdated
            ? '目前 8000 仍是舊版後端。請在後端視窗按 Ctrl+C，再重新執行啟動指令，接著重新整理網頁。'
            : home
              ? r.status === 'ENDED'
                ? '本輪已結束，回看這次選擇，再決定下一段人生。'
                : initial
                  ? '確認目前的資產配置，就能開始第一段人生。'
                  : eventPending
                    ? '這段人生還有事件待確認，繼續查看後再出門。'
                    : review
                      ? '確認這段人生的資產結算後，就可以出發上班。'
                      : phase === 'WORK_REQUIRED'
                        ? '這段人生的事件與結算已確認，先去上班吧。'
                        : '可以直接擲骰，或前往金融大樓安排資產。'
              : at === 'work'
                ? phase === 'WORKING'
                  ? '完成工作後，就能自由安排接下來的時間。'
                  : '先回家，再決定要擲骰或安排投資。'
                : at === 'hospital'
                  ? '就醫事件、費用與理賠紀錄，在這裡整理清楚。'
                  : at === 'finance'
                    ? '讓資金與保障，配合你的人生步調。'
                    : '把下班後的時間，留一點給自己。'}
        </p>
        <div className="routine-scene-actions">
          {home ? (
            <>
              <button disabled={homeDisabled} onClick={() => void homeAction()}>
                {homeLabel}
              </button>
              {(initial || homeFree) && (
                <>
                  <button
                    disabled={game.busy || !allowed(r, 'SCENE_TRANSITION')}
                    onClick={() => onMove('FINANCE')}
                  >
                    前往金融大樓
                  </button>
                </>
              )}
            </>
          ) : at === 'work' && phase === 'WORKING' ? (
            <button disabled={game.busy || outdated} onClick={() => void finishWork()}>
              完成工作・下班 →
            </button>
          ) : at === 'work' && phase === 'RETURN_HOME' ? (
            <button disabled={game.busy} onClick={() => onMove('HOME')}>
              下班回家 →
            </button>
          ) : at === 'hospital' ? (
            <button disabled={game.busy} onClick={() => onPanel('hospital')}>
              進入醫院服務 →
            </button>
          ) : at === 'finance' ? (
            <button disabled={game.busy} onClick={() => onPanel('finance')}>
              進入金融大樓 →
            </button>
          ) : (
            <button disabled={game.busy} onClick={() => onPanel(at === 'work' ? 'assets' : 'event')}>
              {at === 'work' ? '查看資產' : '查看人生紀錄'} →
            </button>
          )}
        </div>
      </div>
      <span className="routine-scene-location">{home ? '我的房間' : DESTINATIONS[at!].label}</span>
    </section>
  );
}

export function RoutineTravel({
  game,
  canMove,
  onMove,
  error,
}: {
  game: GameModel;
  canMove: boolean;
  onMove: (scene: string) => void;
  error?: string;
}) {
  const r = game.run!,
    phase = r.daily_phase ?? (r.scene_id === 'HOME' ? 'HOME_READY' : 'FREE_TIME');
  const initial = r.status === 'INITIAL_ALLOCATION';
  const targets =
    phase === 'WORK_REQUIRED'
      ? [{ id: 'WORK', label: '出發上班' }]
      : initial
        ? [{ id: 'FINANCE', label: '前往金融大樓' }]
        : phase === 'HOME_READY' && r.scene_id === 'HOME'
          ? [{ id: 'FINANCE', label: '前往金融大樓' }]
          : [];
  return (
    <section className="play-card travel-controls">
      <span className="eyebrow">02 · ROUTINE</span>
      <h2>{game.busy ? '行程進行中' : '接下來的安排'}</h2>
      <p className="routine-progress">
        <strong>
          {initial
            ? '初始資產配置'
            : (
                {
                  HOME_READY: '在家休息',
                  WORK_REQUIRED: '先去上班',
                  WORKING: '工作時間',
                  FREE_TIME: '外出自由活動',
                  RETURN_HOME: '下班回家',
                } as Record<string, string>
              )[phase]}
        </strong>
        {initial
          ? '配置完成後回家，開始第一段人生。'
          : phase === 'WORK_REQUIRED'
            ? '上班完成後，才能安排自由活動。'
            : phase === 'WORKING'
              ? '在工作場域按「完成工作・下班」。'
              : phase === 'RETURN_HOME'
                ? '先乘車回家，再安排下班後的自由時間。'
                : phase === 'FREE_TIME'
                  ? '活動結束後回家，再選擇下一個行程。'
                  : '回家後可擲骰或前往金融大樓。'}
      </p>
      {targets
        .filter(t => t.id !== r.scene_id)
        .map(t => (
          <button
            key={t.id}
            className={phase === 'WORK_REQUIRED' ? 'routine-required' : ''}
            disabled={!canMove}
            onClick={() => onMove(t.id)}
          >
            {t.label}
          </button>
        ))}
      {r.scene_id !== 'HOME' &&
        (initial || phase === 'FREE_TIME' || phase === 'HOME_READY' || phase === 'RETURN_HOME') && (
          <button disabled={!canMove} onClick={() => onMove('HOME')}>
            回家休息
          </button>
        )}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
