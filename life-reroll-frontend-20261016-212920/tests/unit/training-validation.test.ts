import { describe, expect, it } from 'vitest';
import type { Course, Lesson, Source } from '@/lib/training';
import { MAX_EVENT_SOURCES, sourceIssue, validateTrainingDraft } from '@/lib/training-validation';

const source = (id: string): Source => ({ id, title: id, locator: '', url: '', text: '' });
const sources = Object.fromEntries(['s1', 's2', 's3'].map(id => [id, source(id)]));

function lesson(patch: Partial<Lesson> = {}): Lesson {
  return {
    id: 'e1',
    topic: 'NEEDS',
    title: '路口的碰撞',
    lesson: '先確認保障需求。',
    prompt: '你會怎麼做？',
    choices: [
      { id: 'a', label: '先看保障' },
      { id: 'b', label: '先投資' },
    ],
    correct_id: 'a',
    explanation: '保障需求優先。',
    source_ids: ['s1'],
    loss_minor: 0,
    loss_kind: 'NONE',
    ...patch,
  };
}

function course(patch: Partial<Course> = {}): Course {
  return {
    id: '',
    title: '車禍測試',
    audience: '銀行理專',
    instructions: '用短情境教保障。',
    product_ids: ['p1'],
    products: [],
    material_ids: [],
    sources,
    events: [lesson()],
    rules: {
      horizon_months: 24,
      salary_minor: 5_000_000,
      living_bps: 6000,
      reserve_months: 2,
      market: 'NORMAL',
      drop_bps: 2000,
      stress_start: 3,
      stress_end: 9,
      emphasis_topic: 'NEEDS',
      emphasis_multiplier: 2,
      guaranteed_topic: false,
    },
    reviewed: false,
    unresolved: [],
    status: 'DRAFT',
    version: 0,
    revision: '',
    ...patch,
  };
}

describe('validateTrainingDraft', () => {
  it('accepts a complete draft', () => {
    expect(validateTrainingDraft(course(), sources)).toBeNull();
  });

  it('counts characters, not UTF-16 units, for length limits', () => {
    expect(validateTrainingDraft(course({ title: '😀'.repeat(100) }), sources)).toBeNull();
    expect(validateTrainingDraft(course({ title: '😀'.repeat(101) }), sources)?.message).toContain(
      '教案名稱',
    );
  });

  it('points at the offending rule field', () => {
    const c = course();
    c.rules.stress_end = 30;
    expect(validateTrainingDraft(c, sources)).toMatchObject({ ruleKey: 'stress_start' });
    c.rules.living_bps = 9000;
    expect(validateTrainingDraft(c, sources)).toMatchObject({ ruleKey: 'living_bps' });
  });

  it('requires a matching scenario for a guaranteed topic', () => {
    const c = course();
    c.rules.guaranteed_topic = true;
    c.rules.emphasis_topic = 'MARKET';
    expect(validateTrainingDraft(c, sources)?.message).toContain('保證的主題');
  });

  it('reports the event index for event problems', () => {
    const events = [lesson(), lesson({ id: 'e2', loss_minor: 100, loss_kind: 'NONE' })];
    expect(validateTrainingDraft(course({ events }), sources)).toMatchObject({ eventIndex: 1 });
  });
});

describe('sourceIssue', () => {
  it('flags missing, too many, unknown and duplicate sources separately', () => {
    expect(sourceIssue(lesson({ source_ids: [] }), 0, sources)?.message).toContain('至少要選擇 1 項');
    const many = Array.from({ length: MAX_EVENT_SOURCES + 1 }, (_, i) => 's' + i);
    expect(sourceIssue(lesson({ source_ids: many }), 0, sources)?.message).toContain(
      `最多 ${MAX_EVENT_SOURCES} 項`,
    );
    expect(sourceIssue(lesson({ source_ids: ['gone'] }), 0, sources)?.message).toContain('不在目前教案內');
    expect(sourceIssue(lesson({ source_ids: ['s1', 's1'] }), 2, sources)).toEqual({
      message: expect.stringContaining('重複引用'),
      eventIndex: 2,
    });
    expect(sourceIssue(lesson({ source_ids: ['s1', 's2'] }), 0, sources)).toBeNull();
  });
});
