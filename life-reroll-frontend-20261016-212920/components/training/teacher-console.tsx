import { requestKey } from '../../lib/game-client';
import { MAX_EVENT_SOURCES, sourceIssue, validateTrainingDraft } from '../../lib/training-validation';
import { useEffect, useMemo, useRef, useState } from 'react';
import { TeacherTutorial, useTeacherTutorial } from './teacher-tutorial';
import {
  get,
  plan,
  fileBody,
  topics,
  kinds,
  createCourseDraft,
  type Course,
  type Catalog,
  type Product,
  type Material,
  type ClassRoom,
  type Job,
  type Run,
} from '../../lib/training';
import type { Write } from './training-app';
import { TrainingPlay, SourceLinks } from './training-play';
const stages = [
  ['materials', '教材與商品', '準備教學來源'],
  ['courses', '教案工作區', '設定課程內容'],
  ['ai', 'AI 編課與發布', '生成、核對與發布'],
  ['classes', '班次與成效', '開班並追蹤學習'],
] as const;
const emptyProduct = {
  name: '',
  provider: '',
  kind: 'INVESTMENT_LIFE',
  source_title: '',
  source_url: '',
  source_locator: '',
  material_id: '',
  facts: '',
  reviewed: false,
};
type Report = {
  class: ClassRoom;
  learners: { id: string; name: string; status: string; month: number; score: number; decisions: number }[];
  completed: number;
  topics: Record<string, { answered: number; incorrect: number }>;
  notice: string;
};
export function TeacherConsole({
  write,
  llmEnabled,
  setNotice,
  userId,
}: {
  write: Write;
  llmEnabled: boolean;
  setNotice: (s: string) => void;
  userId: string;
}) {
  const [tab, setTab] = useState('materials'),
    [catalog, setCatalog] = useState<Catalog | null>(null),
    [courses, setCourses] = useState<Course[]>([]),
    [products, setProducts] = useState<Product[]>([]),
    [materials, setMaterials] = useState<Material[]>([]),
    [classes, setClasses] = useState<ClassRoom[]>([]),
    [jobs, setJobs] = useState<Job[]>([]);
  const [selectedCourse, setCourse] = useState<Course | null>(null),
    [dirty, setDirty] = useState(false),
    [error, setError] = useState(''),
    [trial, setTrial] = useState<Run | null>(null),
    [preview, setPreview] = useState(''),
    [report, setReport] = useState<Report | null>(null);
  const [uploadKey, setUploadKey] = useState(0),
    [file, setFile] = useState<File | null>(null),
    [sourceUrl, setSourceUrl] = useState(''),
    [classTitle, setClassTitle] = useState(''),
    [publishedId, setPublishedId] = useState(''),
    [template, setTemplate] = useState('needs');
  const [custom, setCustom] = useState({ ...emptyProduct });
  const loadVersion = useRef(0);
  const tour = useTeacherTutorial(!!catalog, userId);
  const example = useMemo(
    () => (catalog ? { ...createCourseDraft(catalog), title: '教學範本｜保障、投資與現金流' } : null),
    [catalog],
  );
  const course = tour.step?.example ? example : selectedCourse,
    page = tour.step?.tab ?? tab;
  async function load() {
    const version = ++loadVersion.current;
    try {
      const [a, b, c, d, e, f] = await Promise.all([
        get<Catalog>('/catalog'),
        get<Course[]>('/courses'),
        get<Product[]>('/admin/products'),
        get<Material[]>('/admin/materials'),
        get<ClassRoom[]>('/admin/classes'),
        get<Job[]>('/admin/ai-jobs'),
      ]);
      if (version !== loadVersion.current) return;
      setCatalog(a);
      setCourses(b);
      setProducts(c);
      setMaterials(d);
      setClasses(e);
      setJobs(f);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    void load();
  }, []);
  useEffect(() => {
    if (report)
      document.getElementById('tr-class-report')?.scrollIntoView({ block: 'start', behavior: 'instant' });
  }, [report]);
  const activeMaterial = materials.some(x => x.status === 'PARSING'),
    activeAI = jobs.some(x => ['QUEUED', 'RUNNING'].includes(x.status));
  useEffect(() => {
    if (!activeMaterial && !activeAI) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        if (activeMaterial) {
          const m = await get<Material[]>('/admin/materials');
          if (!stopped) setMaterials(m);
        }
        if (activeAI) {
          const j = await get<Job[]>('/admin/ai-jobs');
          if (!stopped) setJobs(j);
        }
      } catch (e) {
        if (!stopped) setError((e as Error).message);
      } finally {
        if (!stopped) timer = setTimeout(() => void poll(), 3000);
      }
    };
    timer = setTimeout(() => void poll(), 1000);
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [activeMaterial, activeAI]);
  function edit(p: Partial<Course>) {
    if (course) {
      setError('');
      setNotice('');
      setCourse({ ...course, ...p, reviewed: p.reviewed ?? false });
      setDirty(true);
      setPreview('');
    }
  }
  function editRules(patch: Partial<Course['rules']>) {
    if (!course) return;
    const r = { ...course.rules, ...patch };
    if (patch.horizon_months !== undefined && r.horizon_months >= 12 && r.horizon_months <= 120) {
      r.stress_end = Math.min(r.stress_end, r.horizon_months);
      r.stress_start = Math.min(r.stress_start, r.stress_end - 1);
    }
    edit({ rules: r });
  }
  function switchCourse(c: Course) {
    if (dirty && !window.confirm('目前有尚未儲存的編輯，確定切換教案？')) return;
    setError('');
    setNotice('');
    setCourse(structuredClone(c));
    setDirty(false);
    setPreview('');
  }
  function accepted(c: Course) {
    setCourse(c);
    setDirty(false);
    void load();
    setNotice(c.status === 'PUBLISHED' ? '教案已發布，現在可以建立班次。' : '教案草稿已儲存。');
  }
  async function save() {
    if (!course) return null;
    const issue = validateTrainingDraft(course, sourceOptions);
    if (issue) {
      setError(issue.message);
      setTab('courses');
      requestAnimationFrame(() => {
        const target =
          issue.eventIndex !== undefined
            ? document.getElementById('tr-event-' + issue.eventIndex)
            : issue.ruleKey
              ? document.querySelector('[data-rule-key="' + issue.ruleKey + '"]')
              : document.querySelector('.tr-studio [role=alert]');
        const group = target?.closest('details');
        if (group) group.open = true;
        if (target instanceof HTMLDetailsElement) target.open = true;
        (target?.querySelector('[role=alert]') ?? target)?.scrollIntoView({
          block: 'center',
          behavior: 'instant',
        });
      });
      return null;
    }
    setError('');
    return await write<Course>(
      plan(
        course.id ? '/admin/courses/' + course.id : '/admin/courses',
        { ...course, expected_version: course.version },
        course.id ? 'PUT' : 'POST',
      ),
      accepted,
    );
  }
  function navigate(id: string) {
    setTab(id);
    setError('');
    requestAnimationFrame(() => {
      const panel = document.getElementById('tr-studio-page');
      panel?.focus({ preventScroll: true });
      panel?.scrollIntoView({ block: 'start', behavior: 'instant' });
    });
  }
  async function nextFromCourse() {
    if (!course) return;
    if (course.status === 'DRAFT' && (dirty || !course.id) && !(await save())) return;
    navigate('ai');
  }
  const runningAI =
    !!course && jobs.some(j => j.course_id === course.id && ['QUEUED', 'RUNNING'].includes(j.status));
  const publishReason = !course
    ? '請先選擇教案。'
    : course.status === 'PUBLISHED'
      ? ''
      : runningAI
        ? 'AI 正在編課，請等待完成或先取消。'
        : course.unresolved.length
          ? '請先處理所有待核對事項。'
          : !course.reviewed
            ? '請核對教案並勾選審核。'
            : '';
  async function publishNext() {
    if (!course || publishReason) return;
    let current = course;
    if (current.status === 'DRAFT') {
      if (dirty || !current.id) {
        const saved = await save();
        if (!saved) return;
        current = saved;
      }
      const published = await write<Course>(
        plan('/admin/courses/' + current.id + '/publish', { expected_version: current.version }),
        accepted,
      );
      if (!published) return;
      current = published;
    }
    setPublishedId(current.id);
    navigate('classes');
  }
  const readyMaterials = materials.filter(m => m.status === 'READY');
  const eventEdit = (i: number, patch: Partial<Course['events'][number]>) =>
    edit({ events: course!.events.map((e, n) => (n === i ? { ...e, ...patch } : e)) });
  const sourceOptions = {
    ...catalog?.sources,
    ...Object.fromEntries(
      products.filter(p => course?.product_ids.includes(p.id)).map(p => [p.source.id, p.source]),
    ),
    ...Object.fromEntries(
      readyMaterials
        .filter(m => course?.material_ids.includes(m.id))
        .flatMap(m =>
          m.sections.map(s => [
            s.id,
            { id: s.id, title: m.name, locator: s.label, url: m.source_url, text: s.text },
          ]),
        ),
    ),
  };
  if (trial)
    return (
      <TrainingPlay
        exitLabel="返回教案工作區"
        run={trial}
        write={write}
        onRun={setTrial}
        onExit={() => setTrial(null)}
      />
    );
  return (
    <div className="tr-studio">
      <div className="tr-heading">
        <div>
          <p className="tr-eyebrow">INSTRUCTOR STUDIO</p>
          <h1>把教材變成一次次選擇</h1>
          <p>準備教材 → 建立教案 → AI 編課與發布 → 開班回顧</p>
        </div>
        <button data-teach-launch disabled={!catalog} onClick={tour.start}>
          工作室教學
        </button>
      </div>
      <div data-teach-target="tabs" className="tr-tabs tr-stages" role="tablist" aria-label="講師授課流程">
        {stages.map(([id, label, description], i) => (
          <button
            id={'tr-tab-' + id}
            key={id}
            role="tab"
            aria-selected={page === id}
            aria-controls="tr-studio-page"
            tabIndex={page === id ? 0 : -1}
            className={page === id ? 'tr-selected' : ''}
            onClick={() => {
              setNotice('');
              navigate(id);
            }}
            onKeyDown={e => {
              const delta = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
              if (!delta && e.key !== 'Home' && e.key !== 'End') return;
              e.preventDefault();
              const n =
                e.key === 'Home'
                  ? 0
                  : e.key === 'End'
                    ? stages.length - 1
                    : (i + delta + stages.length) % stages.length;
              setTab(stages[n][0]);
              document.getElementById('tr-tab-' + stages[n][0])?.focus();
            }}
          >
            <span className="tr-stage-number">{i + 1}</span>
            <span>
              {label}
              <small>{description}</small>
            </span>
          </button>
        ))}
      </div>
      <section id="tr-studio-page" role="tabpanel" aria-labelledby={'tr-tab-' + page} tabIndex={-1}>
        {dirty && selectedCourse && !tour.active && (
          <p className="tr-warning">
            「{selectedCourse.title || '未命名教案'}」有未儲存的編輯，切換步驟仍會保留。
            {page !== 'courses' && (
              <button className="tr-inline-save" onClick={() => void save()}>
                儲存目前草稿
              </button>
            )}
          </p>
        )}
        {tour.active && tour.step?.example && (
          <p className="tr-tutorial-example">教學範本 · 僅供導覽，尚未建立或儲存教案。</p>
        )}
        {error && (
          <p role="alert" className="tr-error">
            {error}
          </p>
        )}
        {!catalog ? (
          <p role="status">正在載入講師資料…</p>
        ) : page === 'courses' ? (
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
                      {c.status === 'PUBLISHED' ? '已發布 · 固定版本' : '草稿'} · {c.events?.length ?? 0}{' '}
                      則情境
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
                    <input
                      maxLength={100}
                      value={course.title}
                      onChange={e => edit({ title: e.target.value })}
                    />
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
                            onChange={e =>
                              edit({ rules: { ...course.rules, stress_end: Number(e.target.value) } })
                            }
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
                              emphasis_multiplier:
                                e.target.value === 'NONE' ? 1 : course.rules.emphasis_multiplier,
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
                        onChange={e =>
                          edit({ rules: { ...course.rules, guaranteed_topic: e.target.checked } })
                        }
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
                              onChange={() =>
                                eventEdit(i, { source_ids: event.source_ids.filter(x => x !== id) })
                              }
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
                            onChange={e =>
                              eventEdit(i, { loss_minor: Math.round(Number(e.target.value) * 100) })
                            }
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
                      onClick={() =>
                        void write<Run>(plan('/admin/courses/' + course.id + '/trial', {}), setTrial)
                      }
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
        ) : page === 'materials' ? (
          <div className="tr-stack">
            <section className="tr-card">
              <h2 data-teach-target="upload">匯入授課教材</h2>
              <p>
                支援 PDF、DOCX、PPTX、TXT、Markdown，每檔 8 MiB；PDF／PPTX 最多 100
                頁或投影片。背景解析期間可以繼續編課。
              </p>
              <p>
                掃描圖片目前無法辨識文字，請先轉為可選取文字的文件。已有內建商品可直接編課，匯入教材不是必填步驟。
              </p>
              <form
                onSubmit={e => {
                  e.preventDefault();
                  if (file)
                    void fileBody(file)
                      .then(b =>
                        write(plan('/admin/materials', { ...b, source_url: sourceUrl }), () => {
                          setFile(null);
                          setUploadKey(k => k + 1);
                          setNotice('教材已接收，正在背景解析。');
                          void load();
                        }),
                      )
                      .catch(e => setError(e.message));
                }}
              >
                <label>
                  教材檔案
                  <input
                    key={uploadKey}
                    required={!file}
                    type="file"
                    accept=".pdf,.docx,.pptx,.txt,.md"
                    onChange={e => setFile(e.target.files?.[0] ?? null)}
                  />
                </label>
                {file && (
                  <div className="tr-inline">
                    <small>已選擇：{file.name}</small>
                    <button
                      type="button"
                      onClick={() => {
                        setFile(null);
                        setUploadKey(k => k + 1);
                      }}
                    >
                      移除選取
                    </button>
                  </div>
                )}
                <label>
                  原始來源網址（選填）
                  <input type="url" value={sourceUrl} onChange={e => setSourceUrl(e.target.value)} />
                </label>
                <button className="tr-primary" disabled={!file}>
                  上傳並解析
                </button>
              </form>
            </section>
            <section className="tr-card">
              <h2 data-teach-target="materials">教材資料庫</h2>
              {materials.length === 0 && <p>尚未匯入教材。</p>}
              {materials.map(m => (
                <article key={m.id} className="tr-tile">
                  <h3>{m.name}</h3>
                  <p>
                    {
                      (
                        {
                          READY: '可編課',
                          PARSING: '解析中',
                          NEEDS_OCR: '需要文字辨識',
                          FAILED: '解析失敗',
                        } as Record<string, string>
                      )[m.status]
                    }{' '}
                    · {m.message}
                  </p>
                  {['FAILED', 'NEEDS_OCR'].includes(m.status) && (
                    <button
                      onClick={() =>
                        void write(plan('/admin/materials/' + m.id + '/retry', {}), () => void load())
                      }
                    >
                      重新解析
                    </button>
                  )}
                  <details>
                    <summary>核對擷取內容（{m.sections.length} 段）</summary>
                    {m.sections.map(s => (
                      <article key={s.id}>
                        <strong>{s.label}</strong>
                        <p className="tr-pre">{s.text}</p>
                        <small>引用識別：{s.id}</small>
                      </article>
                    ))}
                  </details>
                </article>
              ))}
            </section>
            <section className="tr-card">
              <h2>可選用的商品與概念</h2>
              <p>以下商品已可在教案中勾選，不需要重複新增。</p>
              <div className="tr-grid">
                {products.map(p => (
                  <article key={p.id} className="tr-tile">
                    <h3>{p.name}</h3>
                    <small>
                      {kinds[p.kind]} · {p.provider}
                    </small>
                  </article>
                ))}
              </div>
              <details className="tr-rule-box">
                <summary>新增自訂商品（選填）</summary>
                <h3>加入講師核對的商品</h3>
                <p>保留商品原始來源，套用既有模擬機制。此處不會自動推定真實保費或完整理賠公式。</p>
                <form
                  onSubmit={e => {
                    e.preventDefault();
                    void write<Product>(
                      plan('/admin/products', { ...custom, facts: custom.facts.split('\n').filter(Boolean) }),
                      () => {
                        setCustom({ ...emptyProduct });
                        setNotice('商品已加入，可在教案中選用。');
                        void load();
                      },
                    );
                  }}
                >
                  <div className="tr-grid">
                    {(
                      [
                        ['name', '商品名稱'],
                        ['provider', '保險公司／來源單位'],
                        ['source_title', '來源文件名稱'],
                        ['source_locator', '頁碼／條號'],
                      ] as const
                    ).map(([key, label]) => (
                      <label key={key}>
                        {label}
                        <input
                          required
                          maxLength={key === 'source_title' ? 160 : 100}
                          value={custom[key]}
                          onChange={e => setCustom({ ...custom, [key]: e.target.value })}
                        />
                      </label>
                    ))}
                  </div>
                  <label>
                    模擬機制
                    <select
                      value={custom.kind}
                      onChange={e => setCustom({ ...custom, kind: e.target.value })}
                    >
                      {Object.entries(kinds).map(([id, label]) => (
                        <option key={id} value={id}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    來源網址
                    <input
                      type="url"
                      required={!custom.material_id}
                      value={custom.source_url}
                      onChange={e => setCustom({ ...custom, source_url: e.target.value })}
                    />
                  </label>
                  <label>
                    或引用自己的教材
                    <select
                      value={custom.material_id}
                      onChange={e => setCustom({ ...custom, material_id: e.target.value })}
                    >
                      <option value="">不引用匯入檔案</option>
                      {materials
                        .filter(m => m.status === 'READY')
                        .map(m => (
                          <option key={m.id} value={m.id}>
                            {m.name}
                          </option>
                        ))}
                    </select>
                  </label>
                  <label>
                    核對後的重點（每行一項，最多 8 項，每項 200 字）
                    <textarea
                      required
                      rows={4}
                      value={custom.facts}
                      onChange={e => setCustom({ ...custom, facts: e.target.value })}
                    />
                  </label>
                  <label className="tr-check">
                    <input
                      required
                      type="checkbox"
                      checked={custom.reviewed}
                      onChange={e => setCustom({ ...custom, reviewed: e.target.checked })}
                    />
                    已核對商品內容與引用權限。
                  </label>
                  <button className="tr-primary">加入商品</button>
                </form>
              </details>
            </section>
          </div>
        ) : page === 'classes' ? (
          <div className="tr-stack">
            <section className="tr-card">
              <h2 data-teach-target="class-create">建立授課班次</h2>
              <p>班次固定使用發布當下的教案與共同市場情境。新版本不會悄悄改動學員進度。</p>
              <form
                onSubmit={e => {
                  e.preventDefault();
                  void write<ClassRoom>(
                    plan('/admin/classes', { course_id: publishedId, title: classTitle }),
                    v => {
                      setClassTitle('');
                      setNotice('班次已建立，加入代碼：' + v.code);
                      void load();
                    },
                  );
                }}
              >
                <label>
                  班次名稱
                  <input
                    required
                    placeholder="例如：新進理專保障與投資訓練"
                    maxLength={100}
                    value={classTitle}
                    onChange={e => setClassTitle(e.target.value)}
                  />
                </label>
                <label>
                  已發布教案
                  <select required value={publishedId} onChange={e => setPublishedId(e.target.value)}>
                    <option value="">請選擇已發布教案</option>
                    {courses
                      .filter(c => c.status === 'PUBLISHED')
                      .map(c => (
                        <option key={c.id} value={c.id}>
                          {c.title} · v{c.version}
                        </option>
                      ))}
                  </select>
                </label>
                <button className="tr-primary" disabled={!publishedId || !classTitle.trim()}>
                  建立班次與加入代碼
                </button>
              </form>
            </section>
            <section className="tr-card">
              <h2 data-teach-target="class-list">班次列表</h2>
              {classes.length === 0 && <p>尚未建立班次。請先發布教案，再使用上方表單開班。</p>}
              {classes.map(c => (
                <article className="tr-tile" key={c.id}>
                  <h3>{c.title}</h3>
                  <p>
                    {c.course_title} · {c.status === 'OPEN' ? '開放加入' : '已關閉新加入'}
                  </p>
                  <p className="tr-code">{c.code}</p>
                  <div className="tr-actions">
                    <button
                      onClick={() =>
                        void (navigator.clipboard?.writeText(c.code) ?? Promise.reject(Error('手動複製')))
                          .then(() => setNotice('班次代碼已複製。'))
                          .catch(() => setNotice('請直接選取上方代碼複製。'))
                      }
                    >
                      複製代碼
                    </button>
                    <button
                      onClick={() => {
                        setNotice('');
                        void get<Report>('/admin/classes/' + c.id + '/report')
                          .then(setReport)
                          .catch(e => setError(e.message));
                      }}
                    >
                      查看學習成效
                    </button>
                    {c.status === 'OPEN' && (
                      <button
                        onClick={() =>
                          void write(plan('/admin/classes/' + c.id + '/close', {}), () => void load())
                        }
                      >
                        關閉新加入
                      </button>
                    )}
                  </div>
                </article>
              ))}
            </section>
            {report && (
              <section id="tr-class-report" className="tr-card">
                <h2>班次學習成效</h2>
                <p>{report.class.title}</p>
                <p>
                  已完成 {report.completed}／{report.learners.length} 位學員
                </p>
                <div className="tr-table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>學員</th>
                        <th>進度</th>
                        <th>判斷次數</th>
                        <th>學習分數</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.learners.map(l => (
                        <tr key={l.id}>
                          <td>{l.name}</td>
                          <td>{l.status === 'ENDED' ? '已完成' : '第 ' + l.month + ' 月'}</td>
                          <td>{l.decisions}</td>
                          <td>{l.score}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <h3>適合一起討論的重點</h3>
                {Object.entries(report.topics).map(([key, v]) => (
                  <p key={key}>
                    {topics[key]}：{v.incorrect}／{v.answered} 次判斷需要再釐清。
                  </p>
                ))}
                <small>{report.notice}</small>
              </section>
            )}
          </div>
        ) : (
          <section className="tr-card">
            <h2 data-teach-target="ai">AI 編課與發布</h2>
            <label>
              選擇要編課或發布的教案
              <select
                value={course?.id ?? ''}
                onChange={e => {
                  const c = courses.find(c => c.id === e.target.value);
                  if (c) switchCourse(c);
                }}
              >
                <option value="" disabled>
                  請選擇已儲存的教案
                </option>
                {courses.map(c => (
                  <option key={c.id} value={c.id}>
                    {c.title} · {c.status === 'DRAFT' ? '草稿' : '已發布'} · v{c.version}
                  </option>
                ))}
              </select>
            </label>
            <p>AI 編課是選用功能；也可以直接核對下方現有教案，再發布開班。</p>
            {!course && <button onClick={() => navigate('courses')}>前往教案工作區，建立或選擇教案</button>}
            {course?.status === 'PUBLISHED' && (
              <p className="tr-warning">
                此版本已發布，內容已固定。可直接前往開班；要修改內容，請回教案工作區複製為新草稿。
              </p>
            )}
            {dirty && <p>請先儲存目前編輯，再產生 AI 草稿。</p>}
            <p className="tr-warning">
              {llmEnabled
                ? '模型接口已啟用；生成結果仍須講師核對。'
                : 'AI 編課目前未啟用。可以先保存編課需求，服務啟用後再重試。'}
            </p>
            <p>
              先在教案工作區選擇草稿，加入教材與「希望怎麼教」，並儲存。模型會在背景整理帶來源的短劇情草稿；不會直接發布或變更商品價格。
            </p>
            <p>目前教案：{course?.title ?? '尚未選擇'}</p>
            <button
              className="tr-primary"
              disabled={
                !course?.id ||
                course.status !== 'DRAFT' ||
                dirty ||
                jobs.some(j => j.course_id === course.id && ['QUEUED', 'RUNNING'].includes(j.status))
              }
              onClick={() =>
                void write<Job>(plan('/admin/ai-jobs', { course_id: course!.id }), () => void load())
              }
            >
              {llmEnabled ? '背景產生劇情草稿' : '保存編課需求，等待模型開啟'}
            </button>
            <div className="tr-stack">
              {jobs
                .filter(j => course && j.course_id === course.id)
                .map(j => (
                  <article className="tr-tile" key={j.id}>
                    <p>
                      {courses.find(c => c.id === j.course_id)?.title ?? '教案'} · 版本 {j.course_version} ·
                      工作 {j.id.slice(0, 8)}
                    </p>
                    <strong>
                      {(
                        {
                          WAITING_PROVIDER: '等待模型開啟',
                          QUEUED: '等待背景處理',
                          RUNNING: '編課中',
                          COMPLETE: '草稿待審核',
                          APPLIED: '已套用草稿',
                          CANCELLED: '已取消',
                          FAILED: '未完成',
                          INTERRUPTED: '處理中斷',
                        } as Record<string, string>
                      )[j.status] ?? j.status}
                    </strong>
                    <p
                      role={j.status === 'FAILED' ? 'alert' : undefined}
                      className={j.status === 'FAILED' ? 'tr-error' : undefined}
                    >
                      {j.message}
                    </p>
                    {j.elapsed_seconds !== undefined && (
                      <small>
                        經過 {j.elapsed_seconds} 秒
                        {j.progress_chars ? ` · 已接收 ${j.progress_chars} 字` : null}
                        {['QUEUED', 'RUNNING'].includes(j.status) ? ' · 可繼續編課或離開本頁。' : null}
                      </small>
                    )}
                    {j.result && (
                      <details>
                        <summary>核對生成草稿</summary>
                        {j.result.events.map(e => (
                          <article key={e.id}>
                            <h3>{e.title}</h3>
                            <p>{e.lesson}</p>
                            <p>{e.prompt}</p>
                            <ul>
                              {e.choices.map(c => (
                                <li key={c.id}>
                                  {c.label}
                                  {c.id === e.correct_id ? '（教學答案）' : ''}
                                </li>
                              ))}
                            </ul>
                            <p>{e.explanation}</p>
                            <SourceLinks ids={e.source_ids} sources={j.sources ?? {}} />
                          </article>
                        ))}
                        {j.result.extracted_facts?.map((f, i) => (
                          <article key={i}>
                            <strong>擷取重點</strong>
                            <p>{f.text}</p>
                            <SourceLinks ids={[f.source_id]} sources={j.sources ?? {}} />
                          </article>
                        ))}
                        {j.result.unresolved.map(x => (
                          <p key={x}>{x}</p>
                        ))}
                      </details>
                    )}
                    <div className="tr-actions">
                      {llmEnabled &&
                        ['WAITING_PROVIDER', 'FAILED', 'INTERRUPTED'].includes(j.status) &&
                        courses.some(
                          c => c.id === j.course_id && c.status === 'DRAFT' && c.version === j.course_version,
                        ) && (
                          <button
                            onClick={() =>
                              void write(plan('/admin/ai-jobs/' + j.id + '/retry', {}), () => void load())
                            }
                          >
                            重新排入編課
                          </button>
                        )}
                      {['COMPLETE', 'WAITING_PROVIDER', 'FAILED', 'INTERRUPTED'].includes(j.status) &&
                        !courses.some(
                          c => c.id === j.course_id && c.status === 'DRAFT' && c.version === j.course_version,
                        ) && <small>教案已更新或發布，這份舊需求不能重試或覆寫目前版本。</small>}
                      {j.status === 'COMPLETE' &&
                        courses.some(
                          c => c.id === j.course_id && c.status === 'DRAFT' && c.version === j.course_version,
                        ) && (
                          <button
                            disabled={dirty}
                            onClick={() =>
                              void write<Course>(plan('/admin/ai-jobs/' + j.id + '/apply', {}), c => {
                                accepted(c);
                                setNotice('AI 草稿已套用。請核對下方教案與待核對事項，重新審核後發布。');
                              })
                            }
                          >
                            套用到目前教案
                          </button>
                        )}
                      {['WAITING_PROVIDER', 'QUEUED', 'RUNNING'].includes(j.status) && (
                        <button
                          onClick={() =>
                            void write(plan('/admin/ai-jobs/' + j.id + '/cancel', {}), () => void load())
                          }
                        >
                          取消需求
                        </button>
                      )}
                    </div>
                  </article>
                ))}
            </div>
            {course && (
              <section className="tr-final-review">
                <h3>核對教案並發布</h3>
                <p>
                  目前版本：{course.title} · {course.events.length} 則情境。發布前請核對實際要交給學員的內容。
                </p>
                <details className="tr-rule-box">
                  <summary>查看完整教案、答案與引用</summary>
                  {course.events.map(e => (
                    <article className="tr-tile" key={e.id}>
                      <h3>{e.title}</h3>
                      <p>{e.lesson}</p>
                      <p>{e.prompt}</p>
                      <ul>
                        {e.choices.map(c => (
                          <li key={c.id}>
                            {c.label}
                            {c.id === e.correct_id ? '（教學答案）' : ''}
                          </li>
                        ))}
                      </ul>
                      <p>{e.explanation}</p>
                      <SourceLinks ids={e.source_ids} sources={course.sources} />
                    </article>
                  ))}
                </details>
                <fieldset className="tr-workspace" disabled={course.status === 'PUBLISHED'}>
                  {course.unresolved.length > 0 && (
                    <label>
                      待核對事項（每行一項；核對後刪除）
                      <textarea
                        rows={4}
                        value={course.unresolved.join('\n')}
                        onChange={e => edit({ unresolved: e.target.value.split('\n').filter(Boolean) })}
                      />
                    </label>
                  )}
                  <label data-teach-target="review" className="tr-check">
                    <input
                      type="checkbox"
                      checked={course.reviewed}
                      onChange={e => edit({ reviewed: e.target.checked })}
                    />
                    我已核對來源、商品範圍、教學答案與遊戲假設。
                  </label>
                </fieldset>
                {course.id && (
                  <div data-teach-target="publish" className="tr-actions tr-publish">
                    <button
                      disabled={dirty}
                      onClick={() =>
                        void write<Run>(plan('/admin/courses/' + course.id + '/trial', {}), setTrial)
                      }
                    >
                      實際試玩
                    </button>
                    <button onClick={() => navigate('courses')}>返回編輯情境</button>
                  </div>
                )}
              </section>
            )}
          </section>
        )}
      </section>
      {catalog && (
        <nav data-teach-target="workflow" className="tr-workflow-footer" aria-label="步驟導覽">
          <div>
            <small>
              步驟 {stages.findIndex(([id]) => id === page) + 1}／{stages.length}
            </small>
            <strong>{stages.find(([id]) => id === page)?.[1]}</strong>
            {page === 'courses' && !course && <p>先選擇教案或從範本建立草稿。</p>}
            {page === 'ai' && publishReason && <p>{publishReason}</p>}
          </div>
          <div className="tr-actions">
            {page !== 'materials' && (
              <button onClick={() => navigate(stages[stages.findIndex(([id]) => id === page) - 1][0])}>
                上一步：{stages[stages.findIndex(([id]) => id === page) - 1][1]}
              </button>
            )}
            {page === 'materials' && (
              <button className="tr-primary" onClick={() => navigate('courses')}>
                下一步：建立教案
              </button>
            )}
            {page === 'courses' && (
              <button className="tr-primary" disabled={!course} onClick={() => void nextFromCourse()}>
                {course?.status === 'DRAFT' && (dirty || !course.id)
                  ? '儲存草稿並前往 AI 編課'
                  : '下一步：AI 編課與發布'}
              </button>
            )}
            {page === 'ai' && (
              <button
                data-teach-target="publish-next"
                className="tr-primary"
                disabled={!!publishReason}
                onClick={() => void publishNext()}
              >
                {course?.status === 'PUBLISHED' ? '下一步：建立班次' : '核對後發布，前往開班'}
              </button>
            )}
            {page === 'classes' && <button onClick={() => navigate('materials')}>準備下一堂課</button>}
          </div>
        </nav>
      )}
      {tour.active && <TeacherTutorial tour={tour} />}
    </div>
  );
}
