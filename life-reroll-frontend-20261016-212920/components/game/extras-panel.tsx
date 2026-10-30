'use client';
import { useEffect, useRef, useState } from 'react';
import type {
  Settings,
  User,
  DeviceSession,
  Lesson,
  Notice,
  AssetReceipt,
  ContentRelease,
  Job,
  AuditEntry,
} from '@/lib/game-types';
import type { Page } from '@/lib/game-client';
import { useResource, type GameModel } from './use-game';
import { TutorialLaunch } from './tutorial';
import { MotionSwitch } from './motion-switch';
export function ExtrasPanel({
  game,
  onTutorial,
  onMotionChange,
}: {
  game: GameModel;
  onTutorial?: () => void;
  onMotionChange?: (value: boolean) => void;
}) {
  const logged = !!game.session?.user;
  const settings = useResource<Settings>(game, 'A14', {}, logged),
    me = useResource<User>(game, 'A10', {}, logged),
    sessions = useResource<Page<DeviceSession>>(game, 'A12', {}, logged),
    lessons = useResource<Page<Lesson>>(game, 'B03', {}, logged),
    notices = useResource<Page<Notice>>(game, 'B06', {}, logged),
    campaigns = useResource<Page<import('@/lib/game-types').Campaign>>(game, 'C03', {}, logged);
  const [name, setName] = useState(game.session?.user?.display_name ?? ''),
    [currentPassword, setCurrentPassword] = useState(''),
    [newPassword, setNewPassword] = useState(''),
    [deleting, setDeleting] = useState(false),
    [lesson, setLesson] = useState<Lesson | null>(null),
    [motion, setMotion] = useState(false),
    [textScale, setTextScale] = useState(1),
    [health, setHealth] = useState<string | null>(null);
  const serverScale = useRef<number | null>(null);
  useEffect(() => {
    if (settings.value) {
      setMotion(settings.value.reduced_motion);
      if (serverScale.current !== settings.value.text_scale) {
        serverScale.current = settings.value.text_scale;
        setTextScale(settings.value.text_scale);
      }
    }
  }, [settings.value]);
  async function changeMotion(next: boolean) {
    const previous = motion;
    setMotion(next);
    onMotionChange?.(next);
    const ok = await game.perform(async () => {
      await game.write('A15', {}, { reduced_motion: next });
      settings.reload();
    }, '動畫偏好已儲存');
    if (!ok) {
      setMotion(previous);
      onMotionChange?.(previous);
    }
  }

  return (
    <section className="play-card">
      <div className="play-section-title">
        <span className="eyebrow">SETTINGS & LEARNING</span>
        <h2>設定、教學與提醒</h2>
      </div>
      {onTutorial && <TutorialLaunch onStart={onTutorial} disabled={game.busy} />}
      <div className="play-actions">
        <a className="legal-link-button" href="/training">
          通路情境訓練 ↗
        </a>
        <a className="legal-link-button" href="/teach">
          講師工作室 ↗
        </a>
        <a className="legal-link-button" href="/terms" target="_blank" rel="noopener noreferrer">
          服務條款 ↗
        </a>
        <a className="legal-link-button" href="/privacy" target="_blank" rel="noopener noreferrer">
          隱私政策 ↗
        </a>
      </div>
      <details className="play-details">
        <summary>服務連線檢查</summary>
        <div className="play-actions">
          <button
            className="secondary"
            disabled={game.busy}
            onClick={() =>
              void game.perform(async () => {
                await game.api.call('H09');
                setHealth('後端程式正在運行');
              })
            }
          >
            檢查程式存活
          </button>
          <button
            className="secondary"
            disabled={game.busy}
            onClick={() =>
              void game.perform(async () => {
                await game.api.call('H10');
                setHealth('後端資料庫已就緒');
              })
            }
          >
            檢查服務就緒
          </button>
        </div>
        {health && <p>{health}</p>}
      </details>
      {[settings.error, me.error, sessions.error, lessons.error, notices.error, campaigns.error]
        .filter(Boolean)
        .map((e, i) => (
          <p role="alert" key={i}>
            {e}
          </p>
        ))}
      {logged && (
        <>
          <details className="play-details" open>
            <summary>帳號與閱讀偏好</summary>
            <p>
              {me.value?.email} · {me.value?.email_verified ? '已驗證' : '未驗證'}
            </p>
            <label>
              暱稱
              <input minLength={2} maxLength={30} value={name} onChange={e => setName(e.target.value)} />
            </label>
            <button
              disabled={game.busy || name.length < 2 || name.length > 30}
              onClick={() =>
                void game.perform(async () => {
                  await game.write('A11', {}, { display_name: name });
                  await game.refresh();
                }, '暱稱已更新')
              }
            >
              更新暱稱
            </button>
            {settings.value && (
              <>
                <MotionSwitch
                  checked={motion}
                  disabled={game.busy}
                  onChange={next => void changeMotion(next)}
                />
                <label>
                  文字大小
                  <select value={textScale} onChange={e => setTextScale(Number(e.target.value))}>
                    <option value={1}>標準</option>
                    <option value={1.2}>放大 20%</option>
                    <option value={1.5}>放大 50%</option>
                  </select>
                </label>
                <button
                  disabled={game.busy || textScale === settings.value.text_scale}
                  onClick={() =>
                    void game.perform(async () => {
                      await game.write('A15', {}, { text_scale: textScale });
                      await game.refresh();
                    }, '文字大小已儲存')
                  }
                >
                  儲存文字大小
                </button>
              </>
            )}
            <h3>登入裝置</h3>
            {sessions.value?.items.map(s => (
              <div className="resource-row" key={s.id}>
                <span>
                  {s.device_label} · {new Date(s.last_seen_at).toLocaleString('zh-TW')}
                </span>
                <button
                  className="secondary"
                  disabled={game.busy}
                  onClick={() =>
                    void game.perform(async () => {
                      await game.write('A13', { session_id: s.id }, {});
                      await game.refresh();
                    }, '指定裝置已登出')
                  }
                >
                  {s.is_current ? '登出目前裝置' : '撤銷登入'}
                </button>
              </div>
            ))}
          </details>
          <details className="play-details">
            <summary>變更密碼</summary>
            <label>
              目前密碼
              <input
                type="password"
                autoComplete="current-password"
                value={currentPassword}
                onChange={e => setCurrentPassword(e.target.value)}
              />
            </label>
            <label>
              新密碼（至少 12 字）
              <input
                type="password"
                minLength={12}
                maxLength={128}
                autoComplete="new-password"
                value={newPassword}
                onChange={e => setNewPassword(e.target.value)}
              />
            </label>
            <button
              disabled={game.busy || !currentPassword || newPassword.length < 12}
              onClick={() =>
                void game.perform(async () => {
                  await game.write(
                    'A09',
                    {},
                    { current_password: currentPassword, new_password: newPassword },
                  );
                  setCurrentPassword('');
                  setNewPassword('');
                  await game.refresh();
                }, '密碼已更新')
              }
            >
              更新密碼
            </button>
          </details>
          <details className="play-details">
            <summary>保險與人生短教學</summary>
            {lessons.value?.items.map(l => (
              <button
                key={l.id}
                className="history-event"
                disabled={game.busy}
                onClick={() =>
                  void game.perform(async () => {
                    setLesson(await game.api.call<Lesson>('B04', { lesson_id: l.id }));
                  })
                }
              >
                {l.title}
              </button>
            ))}
          </details>
          {lesson && (
            <div className="play-inline-note">
              <h3>{lesson.title}</h3>
              <p>{lesson.short_text}</p>
              <p>{lesson.detail_text}</p>
              <button
                disabled={game.busy}
                onClick={() =>
                  void game.perform(() => game.write('B05', { lesson_id: lesson.id }, {}), '已記錄閱讀')
                }
              >
                標記已閱讀
              </button>
              {lesson.source_urls
                .filter(url => url.startsWith('https://'))
                .map(url => (
                  <a key={url} href={url} target="_blank" rel="noreferrer">
                    參考資料
                  </a>
                ))}
            </div>
          )}
          <details className="play-details">
            <summary>提醒</summary>
            {notices.value?.items.length === 0 && <p>目前沒有提醒。</p>}
            {notices.value?.items.map(n => (
              <div className="resource-row" key={n.id}>
                <p>{n.text}</p>
                <button
                  disabled={game.busy || !!n.read_at}
                  onClick={() =>
                    void game.perform(async () => {
                      await game.write('B07', { notice_id: n.id }, {});
                      notices.reload();
                    }, '提醒已讀')
                  }
                >
                  {n.read_at ? '已讀' : '標記已讀'}
                </button>
              </div>
            ))}
          </details>
          <details className="play-details">
            <summary>歷史遊戲</summary>
            {campaigns.value?.items.map(c => (
              <div className="resource-row" key={c.id}>
                <span>
                  {new Date(c.created_at).toLocaleDateString('zh-TW')} · {c.run_count} 輪 ·{' '}
                  {c.status === 'COMPLETED' ? '已完成' : '進行中'}
                </span>
                <button
                  className="secondary"
                  disabled={game.busy}
                  onClick={() =>
                    void game.perform(async () => {
                      const current = await game.api.call<import('@/lib/game-types').Campaign>('C04', {
                        campaign_id: c.id,
                      });
                      game.setNotice(
                        `本場共 ${current.run_count} 輪，剩餘重生 ${current.rebirths_remaining} 次。`,
                      );
                    })
                  }
                >
                  查看紀錄摘要
                </button>
              </div>
            ))}
          </details>
          <details className="play-details">
            <summary>刪除帳號與遊戲紀錄</summary>
            <p>此操作會刪除目前帳號及其所有人生紀錄，無法復原。</p>
            <label>
              目前密碼
              <input
                type="password"
                autoComplete="current-password"
                value={currentPassword}
                onChange={e => setCurrentPassword(e.target.value)}
              />
            </label>
            <label className="check-label">
              <input type="checkbox" checked={deleting} onChange={e => setDeleting(e.target.checked)} />
              確認永久刪除帳號與紀錄
            </label>
            <button
              className="danger"
              disabled={game.busy || !deleting || !currentPassword}
              onClick={() =>
                void game.perform(async () => {
                  await game.write(
                    'A16',
                    {},
                    { current_password: currentPassword, confirmation: 'DELETE_MY_ACCOUNT' },
                  );
                  setCurrentPassword('');
                  setDeleting(false);
                  await game.refresh();
                }, '帳號與紀錄已刪除')
              }
            >
              永久刪除
            </button>
          </details>
        </>
      )}
    </section>
  );
}
export function AdminPanel({ game }: { game: GameModel }) {
  const isAdmin = !!game.session?.user?.roles.includes('CONTENT_ADMIN');
  const releases = useResource<Page<ContentRelease>>(game, 'H03', {}, isAdmin),
    jobs = useResource<Page<Job>>(game, 'H07', {}, isAdmin),
    audit = useResource<Page<AuditEntry>>(game, 'H08', {}, isAdmin);
  const [kind, setKind] = useState('PERSONAS'),
    [content, setContent] = useState(''),
    [assets, setAssets] = useState<Record<string, string>>({}),
    [version, setVersion] = useState(''),
    [release, setRelease] = useState<ContentRelease | null>(null),
    [publish, setPublish] = useState(false);
  if (!isAdmin) return null;
  return (
    <section className="play-card">
      <span className="eyebrow">CONTENT ADMIN</span>
      <h2>內容管理</h2>
      <p>本版只允許更換人設池。其他資料須與後端已審核內容一致；發布僅影響新遊戲。</p>
      <div className="play-form-grid">
        <label>
          內容類型
          <select value={kind} onChange={e => setKind(e.target.value)}>
            {['PERSONAS', 'EVENTS', 'PRODUCTS', 'RULESET'].map(k => (
              <option key={k}>{k}</option>
            ))}
          </select>
        </label>
        <label>
          內容 JSON
          <textarea rows={8} value={content} onChange={e => setContent(e.target.value)} />
        </label>
      </div>
      <button
        disabled={game.busy || !content}
        onClick={() =>
          void game.perform(async () => {
            JSON.parse(content);
            const asset = await game.write<AssetReceipt>('H01', {}, { kind, content_json: content });
            setAssets(old => ({ ...old, [kind]: asset.id }));
            setContent('');
          }, '內容已上傳')
        }
      >
        上傳內容資料
      </button>
      <p>已取得：{Object.keys(assets).join('、') || '尚無資料'}</p>
      <label>
        發行版本
        <input value={version} onChange={e => setVersion(e.target.value)} />
      </label>
      <button
        disabled={game.busy || !version || Object.keys(assets).length !== 4}
        onClick={() =>
          void game.perform(async () => {
            setRelease(
              await game.write<ContentRelease>(
                'H02',
                {},
                {
                  version,
                  persona_asset_id: assets.PERSONAS,
                  event_asset_id: assets.EVENTS,
                  product_asset_id: assets.PRODUCTS,
                  ruleset_asset_id: assets.RULESET,
                },
              ),
            );
            releases.reload();
          }, '發行草稿已建立')
        }
      >
        建立發行草稿
      </button>
      <h3>內容版本</h3>
      {releases.value?.items.map(v => (
        <button
          className="history-event"
          key={v.id}
          disabled={game.busy}
          onClick={() =>
            void game.perform(async () => {
              setRelease(await game.api.call<ContentRelease>('H04', { release_id: v.id }));
              setPublish(false);
            })
          }
        >
          {v.version} · {v.status}
        </button>
      ))}
      {release && (
        <div className="quote-panel">
          <h3>
            {release.version} · {release.status}
          </h3>
          {release.validation_errors.map(t => (
            <p key={t}>{t}</p>
          ))}
          <button
            disabled={game.busy || !['DRAFT', 'VALIDATED'].includes(release.status)}
            onClick={() =>
              void game.perform(async () => {
                setRelease(await game.write<ContentRelease>('H05', { release_id: release.id }, {}));
                releases.reload();
              })
            }
          >
            驗證發行內容
          </button>
          <label className="check-label">
            <input type="checkbox" checked={publish} onChange={e => setPublish(e.target.checked)} />
            確認供新人生使用此版本
          </label>
          <button
            disabled={game.busy || release.status !== 'VALIDATED' || !publish}
            onClick={() =>
              void game.perform(async () => {
                setRelease(await game.write<ContentRelease>('H06', { release_id: release.id }, {}));
                releases.reload();
                audit.reload();
                setPublish(false);
              }, '版本已發布')
            }
          >
            發布內容
          </button>
        </div>
      )}
      <details className="play-details">
        <summary>背景任務</summary>
        {jobs.value?.items.map(j => (
          <div className="resource-row" key={j.id}>
            <span>
              {j.type} · {j.status} · {j.stage}
            </span>
            <button
              disabled={game.busy || j.status !== 'FAILED' || !j.retryable}
              onClick={() =>
                void game.perform(async () => {
                  await game.write('C13', { job_id: j.id }, {});
                  jobs.reload();
                }, '任務已重試')
              }
            >
              重試
            </button>
          </div>
        ))}
      </details>
      <details className="play-details">
        <summary>管理稽核</summary>
        {audit.value?.items.map(a => (
          <p key={a.id}>
            {a.created_at} · {a.action}
          </p>
        ))}
      </details>
    </section>
  );
}
