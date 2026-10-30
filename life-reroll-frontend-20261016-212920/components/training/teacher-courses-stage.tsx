import { requestKey } from '../../lib/game-client';
import { MAX_EVENT_SOURCES, sourceIssue } from '../../lib/training-validation';
import { plan, topics, createCourseDraft, type Course, type Run } from '../../lib/training';
import { type Studio } from './teacher-studio-state';

export function CoursesStage({ s }: { s: Studio }) {
  const {
    write,
    courses,
    products,
    setCourse,
    dirty,
    setDirty,
    setTrial,
    preview,
    setPreview,
    template,
    setTemplate,
    tour,
    course,
    edit,
    editRules,
    switchCourse,
    accepted,
    save,
    readyMaterials,
    eventEdit,
    sourceOptions,
  } = s;
  // The shell renders stages only after the catalog has loaded.
  const catalog = s.catalog!;
  return (
    <div className="tr-editor-grid">
      <aside className="tr-card">
        <h2>我的教案</h2>
        <button
          data-teach-target="new-course"
          onClick={() => {
            if (dirty && !window.confirm('確定放棄未儲存的編輯？')) return;
            setCourse(createCourseDraft(catalog));
            setDirty(true);
          }}
        >
          ＋ 從範本建立教案
        </button>
        <div className="tr-stack">
          {courses.map(c => (
            <button
              className={course?.id === c.id ? 'tr-selected tr-course-item' : 'tr-course-item'}
              key={c.id}
              onClick={() => switchCourse(c)}
            >
              {c.title}
              <small>
                {c.status === 'PUBLISHED' ? '已發布 · 固定版本' : '草稿'} · {c.events?.length ?? 0} 則情境
              </small>
            </button>
          ))}
        </div>
      </aside>
      {!course ? (
        <section className="tr-card">
          <h2>先選擇一份教案</h2>
          <p>內建三項法巴商品的示範課程。可複製後編輯；發布版本不會覆蓋既有班次。</p>
          <p>示範教案由專案整理，尚未經法國巴黎人壽內部核准。</p>
        </section>
      ) : (
        <section className="tr-card">
          <div className="tr-heading">
            <h2>
              {course.status === 'PUBLISHED' ? '已發布版本' : '編輯教案'}
              {dirty ? ' · 未儲存' : ''}
            </h2>
            {course.id && (
              <button
                disabled={dirty}
                onClick={() =>
                  void write<Course>(plan('/admin/courses/' + course.id + '/clone', {}), accepted)
                }
              >
                複製為新草稿
              </button>
            )}
          </div>
          {course.review_notice && <p className="tr-warning">{course.review_notice}</p>}
          <fieldset disabled={course.status === 'PUBLISHED'} className="tr-workspace">
            <label data-teach-target="brief">
              教案名稱
              <input maxLength={100} value={course.title} onChange={e => edit({ title: e.target.value })} />
            </label>
            <label>
              授課對象
              <input
                maxLength={100}
                value={course.audience}
                onChange={e => edit({ audience: e.target.value })}
              />
            </label>
            <label>
              希望怎麼教
              <textarea
                rows={4}
                maxLength={4000}
                value={course.instructions}
                onChange={e => edit({ instructions: e.target.value })}
              />
            </label>
            <h3>商品與教材</h3>
            <p>法巴商品與一般保險概念分開標示。請只上傳已授權的教材，不要上傳真實客戶個資。</p>
            <div className="tr-stack">
              {products.map(p => (
                <label className="tr-check" key={p.id}>
                  <input
                    type="checkbox"
                    checked={course.product_ids.includes(p.id)}
                    onChange={e =>
                      edit({
                        product_ids: e.target.checked
                          ? [...course.product_ids, p.id]
                          : course.product_ids.filter(x => x !== p.id),
                      })
                    }
                  />
                  {p.name}
                </label>
              ))}
            </div>
            <details>
              <summary>選用已解析教材（{course.material_ids.length} 份已選）</summary>
              {readyMaterials.length === 0 && (
                <p>尚無可用教材。請先到第一步匯入並核對，或使用內建商品來源編課。</p>
              )}
              {readyMaterials.map(m => (
                <label key={m.id} className="tr-check">
                  <input
                    type="checkbox"
                    checked={course.material_ids.includes(m.id)}
                    onChange={e =>
                      edit({
                        material_ids: e.target.checked
                          ? [...course.material_ids, m.id]
                          : course.material_ids.filter(x => x !== m.id),
                      })
                    }
                  />
                  {m.name}
                </label>
              ))}
            </details>
            <details className="tr-rule-box">
              <summary data-teach-target="rules">情境與經濟設定</summary>
              <div className="tr-grid">
                {(
                  [
                    ['horizon_months', '課程月份', 12, 120, 1],
                    ['salary_minor', '每月收入（元）', 10000, 200000, 100],
                    ['living_bps', '生活支出占收入（%）', 50, 85, 1],
                    ['reserve_months', '初始預備金（月生活費）', 1, 4, 1],
                  ] as const
                ).map(([key, label, min, max, step]) => (
                  <label key={key}>
                    {label}
                    <input
                      type="number"
                      data-rule-key={key}
                      min={min}
                      max={max}
                      step={step}
                      value={
                        key === 'salary_minor' || key === 'living_bps'
                          ? course.rules[key] / 100
                          : course.rules[key]
                      }
                      onChange={e =>
                        editRules({
                          [key]:
                            Number(e.target.value) *
                            (key === 'salary_minor' || key === 'living_bps' ? 100 : 1),
                        })
                      }
                    />
                  </label>
                ))}
              </div>
              <label>
                市場情境
                <select
                  value={course.rules.market}
                  onChange={e => edit({ rules: { ...course.rules, market: e.target.value } })}
                >
                  <option value="NORMAL">多空波動</option>
                  <option value="DOWNTURN">提高市場下跌壓力</option>
                  <option value="GUARANTEED_DROP">指定期間全部股票累計下跌</option>
                </select>
              </label>
              {course.rules.market !== 'NORMAL' && (
                <p className="tr-warning">
                  {course.rules.market === 'GUARANTEED_DROP'
                    ? '固定下跌僅為教學壓力測試'
                    : '市場下跌壓力為教學情境'}
                  ，會同時影響投資保單的股票連結部位。不得用來暗示保險投資不會虧損。
                </p>
              )}
              {course.rules.market !== 'NORMAL' && (
                <div className="tr-grid">
                  <label>
                    壓力起始月
                    <input
                      data-rule-key="stress_start"
                      type="number"
                      min={1}
                      max={Math.min(100, course.rules.horizon_months - 1)}
                      value={course.rules.stress_start}
                      onChange={e =>
                        edit({ rules: { ...course.rules, stress_start: Number(e.target.value) } })
                      }
                    />
                  </label>
                  <label>
                    壓力結束月
                    <input
                      type="number"
                      min={course.rules.stress_start + 1}
                      max={course.rules.horizon_months}
                      value={course.rules.stress_end}
                      onChange={e => edit({ rules: { ...course.rules, stress_end: Number(e.target.value) } })}
                    />
                  </label>
                  {course.rules.market === 'GUARANTEED_DROP' && (
                    <label>
                      累計跌幅（%）
                      <input
                        type="number"
                        min={10}
                        max={60}
                        value={course.rules.drop_bps / 100}
                        onChange={e =>
                          edit({ rules: { ...course.rules, drop_bps: Number(e.target.value) * 100 } })
                        }
                      />
                    </label>
                  )}
                </div>
              )}
              <label>
                加強主題
                <select
                  value={course.rules.emphasis_topic}
                  onChange={e =>
                    edit({
                      rules: {
                        ...course.rules,
                        emphasis_topic: e.target.value,
                        guaranteed_topic: false,
                        emphasis_multiplier: e.target.value === 'NONE' ? 1 : course.rules.emphasis_multiplier,
                      },
                    })
                  }
                >
                  {Object.entries(topics).map(([k, v]) => (
                    <option value={k} key={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                抽樣權重（1–5 倍）
                <input
                  disabled={course.rules.emphasis_topic === 'NONE'}
                  type="number"
                  min={1}
                  max={5}
                  value={course.rules.emphasis_multiplier}
                  onChange={e =>
                    edit({ rules: { ...course.rules, emphasis_multiplier: Number(e.target.value) } })
                  }
                />
              </label>
              <label className="tr-check">
                <input
                  disabled={
                    course.rules.emphasis_topic === 'NONE' ||
                    !course.events.some(e => e.topic === course.rules.emphasis_topic)
                  }
                  type="checkbox"
                  checked={course.rules.guaranteed_topic}
                  onChange={e => edit({ rules: { ...course.rules, guaranteed_topic: e.target.checked } })}
                />
                保證本課程至少出現一次此主題
              </label>
              <small>
                請先加入相應事件；這是課程排程，並非真實事故機率。每個班次共用一條固定市場與事件路徑。
              </small>
            </details>
            <h3>融合進遊戲的情境（{course.events.length}／12）</h3>
            {course.events.map((event, i) => (
              <details key={i} id={'tr-event-' + i} className="tr-event-editor">
                <summary data-teach-target={i === 0 ? 'event' : undefined}>
                  {i + 1}. {event.title} · {topics[event.topic]}
                </summary>
                <label>
                  事件名稱
                  <input
                    maxLength={70}
                    value={event.title}
                    onChange={e => eventEdit(i, { title: e.target.value })}
                  />
                </label>
                <label>
                  主題
                  <select value={event.topic} onChange={e => eventEdit(i, { topic: e.target.value })}>
                    {Object.entries(topics)
                      .filter(([id]) => id !== 'NONE')
                      .map(([id, label]) => (
                        <option key={id} value={id}>
                          {label}
                        </option>
                      ))}
                  </select>
                </label>
                <label>
                  短教學（最多 300 字）
                  <textarea
                    rows={2}
                    maxLength={300}
                    value={event.lesson}
                    onChange={e => eventEdit(i, { lesson: e.target.value })}
                  />
                </label>
                <label>
                  遊戲劇情與提問
                  <textarea
                    rows={3}
                    maxLength={400}
                    value={event.prompt}
                    onChange={e => eventEdit(i, { prompt: e.target.value })}
                  />
                </label>
                <p>勾選正確判斷，並編輯選項：</p>
                {event.choices.map((c, n) => (
                  <div className="tr-choice-edit" key={c.id}>
                    <input
                      aria-label={'第' + (n + 1) + '項為正確答案'}
                      type="radio"
                      name={'correct-' + i}
                      checked={event.correct_id === c.id}
                      onChange={() => eventEdit(i, { correct_id: c.id })}
                    />
                    <input
                      aria-label={'第' + (n + 1) + '項選項文字'}
                      maxLength={140}
                      value={c.label}
                      onChange={e =>
                        eventEdit(i, {
                          choices: event.choices.map((x, j) =>
                            n === j ? { ...x, label: e.target.value } : x,
                          ),
                        })
                      }
                    />
                  </div>
                ))}
                <label>
                  選擇後的短回饋
                  <textarea
                    rows={3}
                    maxLength={500}
                    value={event.explanation}
                    onChange={e => eventEdit(i, { explanation: e.target.value })}
                  />
                </label>
                <p>
                  教學依據（已選 {event.source_ids.length}／{MAX_EVENT_SOURCES} 項，至少 1 項）：
                </p>
                {sourceIssue(event, i, sourceOptions) && (
                  <p className="tr-error" role="alert">
                    {sourceIssue(event, i, sourceOptions)!.message}
                  </p>
                )}
                {event.source_ids
                  .filter(id => !sourceOptions[id])
                  .map(id => (
                    <label className="tr-check tr-warning" key={id}>
                      <input
                        type="checkbox"
                        checked
                        onChange={() => eventEdit(i, { source_ids: event.source_ids.filter(x => x !== id) })}
                      />
                      <span>
                        {course.sources[id]?.title ?? '先前引用來源'} ·{' '}
                        {course.sources[id]?.locator ?? '來源已無法辨識'} · 目前未選用，取消勾選可移除
                      </span>
                    </label>
                  ))}
                {Object.values(sourceOptions).map(s => (
                  <label className="tr-check" key={s.id}>
                    <input
                      type="checkbox"
                      checked={event.source_ids.includes(s.id)}
                      disabled={
                        !event.source_ids.includes(s.id) && event.source_ids.length >= MAX_EVENT_SOURCES
                      }
                      onChange={e =>
                        eventEdit(i, {
                          source_ids: e.target.checked
                            ? [...event.source_ids, s.id]
                            : event.source_ids.filter(x => x !== s.id),
                        })
                      }
                    />
                    <span>
                      {s.title} · {s.locator}
                    </span>
                  </label>
                ))}
                <details>
                  <summary>事件必要支出（遊戲假設）</summary>
                  <label>
                    金額（元）
                    <input
                      type="number"
                      min={0}
                      max={500000}
                      value={event.loss_minor / 100}
                      onChange={e => eventEdit(i, { loss_minor: Math.round(Number(e.target.value) * 100) })}
                    />
                  </label>
                  <label>
                    支出類型
                    <select
                      value={event.loss_kind}
                      onChange={e => eventEdit(i, { loss_kind: e.target.value })}
                    >
                      {[
                        ['NONE', '無支出'],
                        ['LIVING', '生活支出（不理賠）'],
                        ['MEDICAL', '醫療支出'],
                        ['LIABILITY', '第三人賠償'],
                        ['TERM_LIFE', '完全失能情境支出'],
                      ].map(([id, label]) => (
                        <option value={id} key={id}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <small>只設定固定的情境效果；實際事故、保額、除外責任及給付仍以正式契約為準。</small>
                </details>
                <button
                  className="tr-danger"
                  disabled={course.events.length <= 1}
                  onClick={() => edit({ events: course.events.filter((_, n) => n !== i) })}
                >
                  移除此情境
                </button>
              </details>
            ))}
            <div className="tr-inline">
              <label>
                加入範本
                <select value={template} onChange={e => setTemplate(e.target.value)}>
                  {catalog.event_templates.map(e => (
                    <option value={e.id} key={e.id}>
                      {e.title}
                    </option>
                  ))}
                </select>
              </label>
              <button
                disabled={course.events.length >= 12}
                onClick={() => {
                  const t = catalog.event_templates.find(e => e.id === template)!;
                  edit({
                    events: [
                      ...course.events,
                      { ...structuredClone(t), id: t.id + '-' + requestKey().slice(0, 8) },
                    ],
                  });
                }}
              >
                加入情境
              </button>
            </div>
            <p>完成內容後先儲存。下一步可選用 AI 編課，或直接核對現有教案後發布。</p>
            <button className="tr-primary" onClick={() => void save()}>
              儲存教案草稿
            </button>
          </fieldset>
          {(course.id || tour.active) && (
            <div data-teach-target="publish" className="tr-actions tr-publish">
              <button
                disabled={dirty}
                onClick={() => void write<Run>(plan('/admin/courses/' + course.id + '/trial', {}), setTrial)}
              >
                實際試玩
              </button>
              <button
                disabled={dirty}
                onClick={() =>
                  void write<{
                    samples: number;
                    with_topic: number;
                    mean_occurrences: number;
                    notice: string;
                  }>(plan('/admin/courses/' + course.id + '/preview', {}), v =>
                    setPreview(
                      `${v.samples} 次排程中，${v.with_topic} 次出現加強主題，平均 ${v.mean_occurrences} 次。${v.notice}`,
                    ),
                  )
                }
              >
                檢查事件排程
              </button>
            </div>
          )}
          {dirty && <small>先儲存草稿，即可試玩、檢查排程與請求 AI 編課。</small>}
          {preview && <p role="status">{preview}</p>}
        </section>
      )}
    </div>
  );
}
