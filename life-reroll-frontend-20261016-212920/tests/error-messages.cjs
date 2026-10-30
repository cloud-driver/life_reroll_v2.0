const fs = require('node:fs'),
  path = require('node:path'),
  ts = require('typescript'),
  Module = require('node:module'),
  assert = require('node:assert/strict');
function load(file) {
  const filename = path.resolve(__dirname, '..', file),
    m = new Module(filename, module);
  m.filename = filename;
  m.paths = Module._nodeModulePaths(path.dirname(filename));
  m._compile(
    ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        target: ts.ScriptTarget.ES2022,
        esModuleInterop: true,
      },
    }).outputText,
    filename,
  );
  return m.exports;
}
const { GameClient, GameApiError, errorMessage, requestKey } = load('lib/game-client.ts'),
  { validateTrainingDraft, sourceIssue } = load('lib/training-validation.ts');
let checks = 0;
function check(v, label) {
  assert.ok(v, label);
  checks++;
}
const response = (code, message, status, details) =>
  new Response(JSON.stringify({ data: null, error: { code, message, details } }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
(async () => {
  const cryptoDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'crypto'),
    nativeCrypto = globalThis.crypto;
  Object.defineProperty(globalThis, 'crypto', {
    configurable: true,
    value: { getRandomValues: v => nativeCrypto.getRandomValues(v) },
  });
  const privateHttpKeys = Array.from({ length: 100 }, () => requestKey());
  check(
    new Set(privateHttpKeys).size === 100 && privateHttpKeys.every(k => /^[0-9a-f]{48}$/.test(k)),
    'private HTTP origin uses secure random fallback without randomUUID',
  );
  Object.defineProperty(globalThis, 'crypto', cryptoDescriptor);
  check(
    new GameApiError('STALE_VERSION', 409, '保留未儲存教案後再同步。').message === '保留未儲存教案後再同步。',
    'server contextual text has priority',
  );
  check(!errorMessage('NEW_UNKNOWN_CODE').includes('NEW_UNKNOWN_CODE'), 'unknown code has friendly fallback');
  const net = new GameClient(async () => {
    throw Error('network lost');
  }, '');
  await assert.rejects(
    () => net.send({ method: 'GET', path: '/api/v1/training/courses', key: 'test' }),
    e => e.code === 'BACKEND_UNAVAILABLE' && !e.message.includes('提交'),
  );
  checks++;
  const key = 'keep-original-key',
    plan = { method: 'POST', path: '/api/v1/training/admin/courses', key, body: {} };
  await assert.rejects(
    () => net.send(plan),
    e => e.code === 'CONNECTION_UNCERTAIN',
  );
  check(plan.key === key, 'write uncertainty retains original retry identity');
  const api = new GameClient(
    async () =>
      response('SOURCE_LIMIT_EXCEEDED', '第 1 則情境「路口」已選 11 項，最多 8 項。', 422, {
        event_index: 0,
        count: 11,
        max: 8,
      }),
    '',
  );
  await assert.rejects(
    () => api.send(plan),
    e => e.code === 'SOURCE_LIMIT_EXCEEDED' && e.details.count === 11 && e.message.includes('路口'),
  );
  checks++;
  for (const [code, message, status] of [
    ['UNAUTHENTICATED', '請重新登入。', 401],
    ['NOT_FOUND', '找不到這份報告。', 404],
    ['SERVICE_UNAVAILABLE', '報告服務暫時無法使用。', 503],
  ]) {
    const client = new GameClient(async () => response(code, message, status), '');
    await assert.rejects(
      () => client.download('/api/v1/reports/report.pdf'),
      e => e.code === code && e.message === message,
    );
    checks++;
  }
  await assert.rejects(
    () => net.download('/api/v1/reports/report.pdf'),
    e => e.code === 'BACKEND_UNAVAILABLE' && !e.message.includes('登入'),
  );
  checks++;
  const badPdf = new GameClient(
    async () => new Response('not-pdf', { headers: { 'Content-Type': 'text/html' } }),
    '',
  );
  await assert.rejects(
    () => badPdf.download('/api/v1/reports/report.pdf'),
    e => e.code === 'INVALID_RESPONSE',
  );
  checks++;
  const sources = Object.fromEntries(
    Array.from({ length: 11 }, (_, i) => [
      's' + i,
      { id: 's' + i, title: '教材', locator: '第 ' + i + ' 頁', url: '' },
    ]),
  );
  const event = {
    id: 'e',
    title: '路口的碰撞',
    topic: 'LIABILITY',
    lesson: '教學',
    prompt: '提問',
    explanation: '回饋',
    choices: [
      { id: 'a', label: '選項一' },
      { id: 'b', label: '選項二' },
    ],
    correct_id: 'a',
    source_ids: [],
    loss_minor: 0,
    loss_kind: 'NONE',
  };
  for (const [refs, phrase] of [
    [[], '至少'],
    [Object.keys(sources), '已選 11 項'],
    [['old'], '不在目前教案內'],
    [['s0', 's0'], '重複'],
  ]) {
    const v = { ...event, source_ids: refs },
      before = JSON.stringify(v);
    check(sourceIssue(v, 0, sources).message.includes(phrase), 'source error explains actual condition');
    check(JSON.stringify(v) === before, 'validation preserves selections');
  }
  check(
    sourceIssue({ ...event, source_ids: Object.keys(sources).slice(0, 8) }, 0, sources) === null,
    'eight references accepted',
  );
  const course = {
    title: '課程',
    audience: '學員',
    instructions: '說明',
    product_ids: ['p'],
    material_ids: [],
    rules: {
      horizon_months: 12,
      salary_minor: 5000000,
      living_bps: 7500,
      reserve_months: 3,
      drop_bps: 5000,
      stress_start: 6,
      stress_end: 12,
      emphasis_topic: 'NONE',
      emphasis_multiplier: 1,
      guaranteed_topic: false,
    },
    events: [{ ...event, source_ids: ['s0'] }],
    unresolved: [],
  };
  check(validateTrainingDraft(course, sources) === null, 'valid course accepted');
  check(
    validateTrainingDraft(
      { ...course, rules: { ...course.rules, salary_minor: 0 } },
      sources,
    ).message.includes('10000 至 200000'),
    'salary range displayed in dollars',
  );
  check(
    validateTrainingDraft(
      { ...course, rules: { ...course.rules, stress_start: 12 } },
      sources,
    ).message.includes('起始月'),
    'stress period error',
  );
  check(
    validateTrainingDraft({ ...course, events: [{ ...event, source_ids: [] }] }, sources).eventIndex === 0,
    'error identifies event to open',
  );
  console.log(`${checks} error-message client checks passed`);
})().catch(e => {
  console.error(e);
  process.exitCode = 1;
});
