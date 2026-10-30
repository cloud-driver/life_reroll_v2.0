import { validateTrainingDraft } from '../../lib/training-validation';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useTeacherTutorial } from './teacher-tutorial';
import {
  get,
  plan,
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

// Shared by the studio shell and its four stage components.
export const stages = [
  ['materials', '教材與商品', '準備教學來源'],
  ['courses', '教案工作區', '設定課程內容'],
  ['ai', 'AI 編課與發布', '生成、核對與發布'],
  ['classes', '班次與成效', '開班並追蹤學習'],
] as const;
export const emptyProduct = {
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
export type Report = {
  class: ClassRoom;
  learners: { id: string; name: string; status: string; month: number; score: number; decisions: number }[];
  completed: number;
  topics: Record<string, { answered: number; incorrect: number }>;
  notice: string;
};

export type StudioProps = {
  write: Write;
  llmEnabled: boolean;
  setNotice: (s: string) => void;
  userId: string;
};

/** All instructor-studio state and actions; stage components receive the result as `s`. */
export function useTeacherStudio({ write, llmEnabled, setNotice, userId }: StudioProps) {
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
  return {
    write,
    llmEnabled,
    setNotice,
    userId,
    tab,
    setTab,
    catalog,
    setCatalog,
    courses,
    setCourses,
    products,
    setProducts,
    materials,
    setMaterials,
    classes,
    setClasses,
    jobs,
    setJobs,
    selectedCourse,
    setCourse,
    dirty,
    setDirty,
    error,
    setError,
    trial,
    setTrial,
    preview,
    setPreview,
    report,
    setReport,
    uploadKey,
    setUploadKey,
    file,
    setFile,
    sourceUrl,
    setSourceUrl,
    classTitle,
    setClassTitle,
    publishedId,
    setPublishedId,
    template,
    setTemplate,
    custom,
    setCustom,
    loadVersion,
    tour,
    example,
    course,
    page,
    load,
    activeMaterial,
    activeAI,
    edit,
    editRules,
    switchCourse,
    accepted,
    save,
    navigate,
    nextFromCourse,
    runningAI,
    publishReason,
    publishNext,
    readyMaterials,
    eventEdit,
    sourceOptions,
  };
}

export type Studio = ReturnType<typeof useTeacherStudio>;
