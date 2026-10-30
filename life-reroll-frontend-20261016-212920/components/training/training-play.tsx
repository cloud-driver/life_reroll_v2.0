import { useEffect, useRef, useState, type ReactNode } from 'react';
import { plan, money, topics, kinds, type Run, type Quote, type Source } from '../../lib/training';
import type { Write } from './training-app';
function ConfirmDialog({ children, onClose }: { children: ReactNode; onClose: () => void }) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    ref.current?.querySelector('button')?.focus();
    return () => {
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, []);
  return (
    <div className="tr-overlay">
      <section
        ref={ref}
        className="tr-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="tr-quote-title"
        onKeyDown={e => {
          if (e.key === 'Escape') {
            e.preventDefault();
            onClose();
          }
          if (e.key === 'Tab') {
            const buttons = Array.from(
              ref.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? [],
            );
            if (!buttons.length) return;
            const first = buttons[0],
              last = buttons.at(-1)!;
            if (e.shiftKey && document.activeElement === first) {
              e.preventDefault();
              last.focus();
            } else if (!e.shiftKey && document.activeElement === last) {
              e.preventDefault();
              first.focus();
            }
          }
        }}
      >
        {children}
      </section>
    </div>
  );
}
export function SourceLinks({ ids, sources }: { ids: string[]; sources: Record<string, Source> }) {
  return (
    <details className="tr-sources">
      <summary>核對教學來源（{ids.length}）</summary>
      {ids.map(id => {
        const s = sources[id];
        return s ? (
          <article key={id}>
            <strong>{s.title}</strong>
            <p>{s.locator}</p>
            {s.text && <p>{s.text}</p>}
            {s.url && (
              <a href={s.url} target="_blank" rel="noopener noreferrer">
                開啟原始資料 ↗
              </a>
            )}
          </article>
        ) : null;
      })}
    </details>
  );
}
export function TrainingPlay({
  run,
  write,
  onRun,
  onExit,
  exitLabel = '返回班次列表',
}: {
  run: Run;
  write: Write;
  onRun: (r: Run) => void;
  onExit: () => void;
  exitLabel?: string;
}) {
  const r = run.state,
    [tab, setTab] = useState('products'),
    [quote, setQuote] = useState<Quote | null>(null),
    [stock, setStock] = useState(r.stocks[0].id),
    [qty, setQty] = useState('10'),
    [amount, setAmount] = useState('10000'),
    [bankAction, setBankAction] = useState('SAVE');
  const [policyId, setPolicyId] = useState(''),
    [equity, setEquity] = useState('60'),
    [productId, setProductId] = useState(r.products[0].id);
  const action = (kind: string, params: Record<string, unknown> = {}) =>
    write<Run>(
      plan('/runs/' + run.id + '/actions', { expected_version: r.version, action: kind, params }),
      onRun,
    );
  const preview = (kind: string, params: Record<string, unknown>) =>
    write<Quote>(
      plan('/runs/' + run.id + '/quotes', { expected_version: r.version, action: kind, params }),
      setQuote,
    );
  const value = () => Math.round(Number(amount) * 100),
    policy = r.policies.find(p => p.id === policyId) ?? r.policies.find(p => p.status === 'ACTIVE');
  const move = (location: string) => void action('MOVE', { location });
  const result = r.history.at(-1);
  const quoteLabels: Record<string, string> = {
    STOCK_BUY: '買進股票',
    STOCK_SELL: '賣出股票',
    SAVE: '存入活存',
    WITHDRAW: '提領活存',
    BORROW: '申請借款',
    REPAY: '償還借款',
    PAY_BILL: '支付帳單',
    POLICY_BUY: '購買模擬保單',
    POLICY_WITHDRAW: '提領保單帳戶',
    POLICY_SURRENDER: '解約模擬保單',
    POLICY_ALLOCATE: '調整投資配置',
    CLAIM: '申請模擬理賠',
  };
  useEffect(() => {
    if (['EVENT', 'RESULT', 'ENDED'].includes(r.status)) {
      const heading = document.querySelector<HTMLElement>('.tr-event h2,.tr-play .tr-card h2');
      heading?.setAttribute('tabindex', '-1');
      heading?.focus({ preventScroll: true });
      heading?.scrollIntoView({ block: 'start', behavior: 'instant' });
    }
  }, [r.status]);
  useEffect(() => {
    if (r.status === 'PLAYING')
      document.querySelector('.tr-play')?.scrollIntoView({ block: 'start', behavior: 'instant' });
  }, [r.location]);
  function claims() {
    return (
      <div className="tr-stack">
        {r.history
          .filter(e => e.loss_minor > 0 || e.loss_kind === 'TERM_LIFE')
          .map(e => (
            <article className="tr-tile" key={e.event_id}>
              <strong>
                第 {e.month} 月 · {e.title}
              </strong>
              <p>
                必要支出 {money(e.loss_minor)} ·{' '}
                {e.loss_kind === 'LIVING' ? '生活支出，不在本課程模擬保障內' : kinds[e.loss_kind]}
              </p>
              {r.claims.find(c => c.event_id === e.event_id) ? (
                <p className="tr-badge">
                  {r.claims.find(c => c.event_id === e.event_id)?.status === 'PAID'
                    ? '已入帳'
                    : '已核准，等待入帳'}
                </p>
              ) : (
                <div className="tr-actions">
                  {r.policies
                    .filter(
                      p =>
                        p.status === 'ACTIVE' &&
                        p.kind === e.loss_kind &&
                        p.issued_month + p.waiting_months <= e.month,
                    )
                    .map(p => (
                      <button
                        key={p.id}
                        onClick={() => void preview('CLAIM', { event_id: e.event_id, policy_id: p.id })}
                      >
                        申請：{p.name}
                      </button>
                    ))}
                  {!r.policies.some(
                    p =>
                      p.status === 'ACTIVE' &&
                      p.kind === e.loss_kind &&
                      p.issued_month + p.waiting_months <= e.month,
                  ) && <small>事件發生時沒有符合條件的有效模擬保障。</small>}
                </div>
              )}
            </article>
          ))}
        {!r.history.some(e => e.loss_minor > 0 || e.loss_kind === 'TERM_LIFE') && (
          <p>目前沒有可申請的支出事件。</p>
        )}
      </div>
    );
  }
  return (
    <div className="tr-play">
      <div className="tr-heading">
        <div>
          <p className="tr-eyebrow">LIFE REROLL · 情境課程</p>
          <h1>{r.course_title}</h1>
        </div>
        <button onClick={onExit}>{exitLabel}</button>
      </div>
      <section className="tr-hud" aria-label="訓練狀態">
        <div>
          <small>可用資金</small>
          <strong>{money(r.balances.liquidity_minor)}</strong>
        </div>
        <div>
          <small>淨資產</small>
          <strong>{money(r.balances.net_worth_minor)}</strong>
        </div>
        <div>
          <small>生活品質</small>
          <strong>{r.quality}／100</strong>
        </div>
        <div>
          <small>課程進度</small>
          <strong>
            第 {r.month}／{r.horizon_months} 月
          </strong>
        </div>
      </section>
      {r.status === 'ENDED' && r.report ? (
        <section className="tr-card">
          <p className="tr-eyebrow">LEARNING REVIEW</p>
          <h2>這一段人生，你學到了什麼？</h2>
          <p className="tr-score">
            {r.report.score}
            <small>
              {' '}
              分 · {r.report.correct}／{r.report.decisions} 次判斷
            </small>
          </p>
          <p>{r.report.notice}</p>
          <p>{r.report.selection_feedback}</p>
          <div className="tr-stack">
            {r.history.map((e, i) => (
              <details className="tr-tile" key={e.event_id} open={!e.correct}>
                <summary>
                  {i + 1}. {e.title} · {e.correct ? '已掌握' : '值得再看一次'}
                </summary>
                <p className="tr-badge">{topics[e.topic]}</p>
                <p>{e.explanation}</p>
                <SourceLinks ids={e.source_ids} sources={r.sources} />
              </details>
            ))}
          </div>
          <p>訓練結果已儲存，講師可以在班次成效中查看。</p>
        </section>
      ) : r.status === 'EVENT' ? (
        <section className="tr-card tr-event" aria-labelledby="lesson-title">
          <p className="tr-eyebrow">
            第 {r.month} 月 · {topics[r.event!.topic]}
          </p>
          <h2 id="lesson-title">{r.event!.title}</h2>
          <p className="tr-lesson">{r.event!.lesson}</p>
          <p>{r.event!.prompt}</p>
          <div className="tr-choices">
            {r.event!.choices.map(c => (
              <button key={c.id} onClick={() => void action('DECIDE', { choice_id: c.id })}>
                {c.label}
              </button>
            ))}
          </div>
          <SourceLinks ids={r.event!.source_ids} sources={r.sources} />
        </section>
      ) : r.status === 'RESULT' && result ? (
        <section className="tr-card tr-event">
          <p className="tr-eyebrow">選擇後的回饋</p>
          <h2>{result.correct ? '你抓到了重點' : '換個角度想想'}</h2>
          <p>{result.explanation}</p>
          {(result.loss_minor > 0 || result.loss_kind === 'TERM_LIFE') && (
            <>
              <p className="tr-warning">
                {result.loss_minor > 0
                  ? '本次必要支出 ' + money(result.loss_minor) + '。'
                  : '此為完全失能模擬事故，請核對有效保障與固定給付條件。'}
                {r.balances.unpaid_minor > 0 && '資金不足部分列為未付帳單。'}
              </p>
              {claims()}
            </>
          )}
          <SourceLinks ids={result.source_ids} sources={r.sources} />
          <button className="tr-primary" onClick={() => void action('ACK')}>
            繼續人生
          </button>
        </section>
      ) : (
        <>
          <nav className="tr-locations" aria-label="前往場域">
            {[
              ['HOME', '我的房間'],
              ['FINANCE', '金融大樓'],
              ['WORK', '工作場域'],
            ].map(([id, label]) => (
              <button
                key={id}
                className={r.location === id ? 'tr-selected' : ''}
                aria-pressed={r.location === id}
                onClick={() => move(id)}
              >
                {label}
              </button>
            ))}
          </nav>
          {r.location === 'HOME' ? (
            <>
              <section
                className="tr-scene"
                style={{
                  backgroundImage:
                    'linear-gradient(0deg,rgba(21,48,49,.86),transparent 90%),url(/scene-home.webp)',
                }}
              >
                <p className="tr-eyebrow">HOME · 回到自己的步調</p>
                <h2>下一個月，會遇到什麼？</h2>
                <p>工作收入與生活支出按月結算。先安排資產，再擲骰推進 1–6 個月，事件會中途停下。</p>
                <button className="tr-light" onClick={() => void action('ROLL')}>
                  ⚄ 擲骰，推進人生
                </button>
                <button className="tr-light" onClick={() => move('FINANCE')}>
                  前往金融大樓
                </button>
              </section>
              <section className="tr-card">
                <h2>選擇生活步調</h2>
                <p>
                  每月收入 {money(r.salary_minor)} · 目前固定支出 {money(r.living_minor)}
                </p>
                <div className="tr-actions">
                  {[
                    ['BASIC', '節省 · 品質逐月 −1'],
                    ['BALANCED', '平衡 · 品質持平'],
                    ['COMFORT', '舒適 · 品質逐月 +1'],
                  ].map(([id, label]) => (
                    <button
                      key={id}
                      aria-pressed={r.lifestyle === id}
                      className={r.lifestyle === id ? 'tr-selected' : ''}
                      onClick={() => void action('LIFESTYLE', { lifestyle: id })}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                <small>生活品質與學習判斷分開呈現；花得越少並不代表學得越好。</small>
              </section>
            </>
          ) : r.location === 'WORK' ? (
            <section
              className="tr-scene"
              style={{
                backgroundImage: 'linear-gradient(0deg,rgba(21,48,49,.9),transparent),url(/scene-work.webp)',
              }}
            >
              <p className="tr-eyebrow">WORK · 穩定收入</p>
              <h2>每份收入，都有下一步安排</h2>
              <p>
                每推進一個月，收入 {money(r.salary_minor)}{' '}
                自動入帳，也會支付生活費。重複點選工作不會額外領薪。
              </p>
              <button className="tr-light" onClick={() => move('HOME')}>
                回家，安排下一段人生
              </button>
            </section>
          ) : (
            <section className="tr-card">
              <p className="tr-eyebrow">FINANCIAL DISTRICT</p>
              <h2>讓資金與保障配合你的需求</h2>
              <p className="tr-warning">{r.market_notice}</p>
              <div className="tr-tabs" role="group" aria-label="金融服務">
                {[
                  ['products', '保障與投資保單'],
                  ['stocks', '股票市場'],
                  ['bank', '存款與借款'],
                  ['claims', '保單與理賠'],
                ].map(([id, label]) => (
                  <button
                    key={id}
                    aria-pressed={tab === id}
                    className={tab === id ? 'tr-selected' : ''}
                    onClick={() => setTab(id)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              {tab === 'products' ? (
                <>
                  <div className="tr-grid">
                    {r.products.map(p => (
                      <article className="tr-tile" key={p.id}>
                        <small>
                          {p.provider} · {kinds[p.kind]}
                        </small>
                        <h3>{p.name}</h3>
                        <ul>
                          {p.facts.map(f => (
                            <li key={f}>{f}</li>
                          ))}
                        </ul>
                        <SourceLinks ids={[p.source.id]} sources={r.sources} />
                        <p className="tr-warning">{p.simulation_notice}</p>
                        <p>
                          {p.kind === 'INVESTMENT_LIFE' || p.kind === 'ANNUITY'
                            ? '入帳費用 3%；每月成本 100 元；提領費 1%；股票連結 60%。'
                            : p.kind === 'TERM_LIFE'
                              ? '年保費 12,000 元，完全失能情境固定給付 100 萬元、限一次。'
                              : '年保費 12,000 元，單次給付上限 100 萬元；醫療等待 2 個月，其餘無等待。'}
                          均為本課程假設。
                        </p>
                        <button
                          onClick={() => {
                            setProductId(p.id);
                            document
                              .getElementById('tr-buy')
                              ?.scrollIntoView({ block: 'center', behavior: 'instant' });
                          }}
                        >
                          選擇這項模擬保單
                        </button>
                      </article>
                    ))}
                  </div>
                  <form
                    id="tr-buy"
                    className="tr-order"
                    onSubmit={e => {
                      e.preventDefault();
                      void preview('POLICY_BUY', { product_id: productId, amount_minor: value() });
                    }}
                  >
                    <h3>試算與確認</h3>
                    <label>
                      模擬商品
                      <select value={productId} onChange={e => setProductId(e.target.value)}>
                        {r.products.map(p => (
                          <option key={p.id} value={p.id}>
                            {p.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    {['INVESTMENT_LIFE', 'ANNUITY'].includes(
                      r.products.find(p => p.id === productId)!.kind,
                    ) ? (
                      <label>
                        投入金額（元）
                        <input
                          type="number"
                          required
                          min={1000}
                          max={1000000}
                          step="1"
                          value={amount}
                          onChange={e => setAmount(e.target.value)}
                        />
                      </label>
                    ) : (
                      <p>本課程固定年保費 12,000 元。</p>
                    )}
                    <button className="tr-primary">預覽費用與資金影響</button>
                  </form>
                </>
              ) : tab === 'stocks' ? (
                <>
                  <p>
                    20
                    檔均為虛構股票。前五檔是較不利的逆風組，排序不代表推薦。市場下跌同樣影響投資保單的股票連結部位。
                  </p>
                  <div className="tr-table-scroll" tabIndex={0} aria-label="20 檔股票報價">
                    <table>
                      <thead>
                        <tr>
                          <th>標的</th>
                          <th>類別</th>
                          <th>股價</th>
                          <th>持有</th>
                          <th>選擇</th>
                        </tr>
                      </thead>
                      <tbody>
                        {r.stocks.map((s, i) => (
                          <tr key={s.id}>
                            <td>
                              {i + 1}. {s.name}
                            </td>
                            <td>{i < 5 ? '逆風組' : '波動組'}</td>
                            <td>{money(s.price_minor)}</td>
                            <td>{r.holdings[s.id] ?? 0} 股</td>
                            <td>
                              <button
                                aria-label={'選擇' + s.name}
                                onClick={() => setStock(s.id)}
                                aria-pressed={stock === s.id}
                              >
                                選擇
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="tr-order">
                    <label>
                      交易標的
                      <select value={stock} onChange={e => setStock(e.target.value)}>
                        {r.stocks.map(s => (
                          <option key={s.id} value={s.id}>
                            {s.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      股數
                      <input
                        type="number"
                        min={1}
                        max={100000}
                        step={1}
                        value={qty}
                        onChange={e => setQty(e.target.value)}
                      />
                    </label>
                    <p>雙向手續費 0.3%，最低 1 元；不保證報酬。</p>
                    <div className="tr-actions">
                      <button
                        onClick={() => void preview('STOCK_BUY', { stock_id: stock, quantity: Number(qty) })}
                      >
                        預覽買進
                      </button>
                      <button
                        onClick={() => void preview('STOCK_SELL', { stock_id: stock, quantity: Number(qty) })}
                      >
                        預覽賣出
                      </button>
                    </div>
                  </div>
                </>
              ) : tab === 'bank' ? (
                <form
                  className="tr-order"
                  onSubmit={e => {
                    e.preventDefault();
                    void preview(bankAction, { amount_minor: value() });
                  }}
                >
                  <p>
                    現金 {money(r.balances.cash_minor)} · 活存 {money(r.balances.savings_minor)}
                  </p>
                  <p>
                    借款 {money(r.balances.debt_minor)} · 未付帳單 {money(r.balances.unpaid_minor)}
                  </p>
                  <small>活存年息 0.8%；借款年息 6%，上限六個月收入。均為遊戲設定。</small>
                  <label>
                    操作
                    <select value={bankAction} onChange={e => setBankAction(e.target.value)}>
                      {[
                        ['SAVE', '存入活存'],
                        ['WITHDRAW', '提領活存'],
                        ['BORROW', '申請借款'],
                        ['REPAY', '償還借款'],
                        ['PAY_BILL', '支付未付帳單'],
                      ].map(([id, label]) => (
                        <option value={id} key={id}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    金額（元）
                    <input
                      type="number"
                      required
                      min={1}
                      max={1000000}
                      value={amount}
                      onChange={e => setAmount(e.target.value)}
                    />
                  </label>
                  <button className="tr-primary">預覽操作</button>
                </form>
              ) : (
                <>
                  <h3>目前保單</h3>
                  {r.policies.length === 0 ? (
                    <p>目前沒有模擬保單。</p>
                  ) : (
                    <div className="tr-stack">
                      {r.policies.map(p => (
                        <article className="tr-tile" key={p.id}>
                          <strong>{p.name}</strong>
                          <p>
                            {p.status === 'ACTIVE'
                              ? '有效'
                              : p.status === 'SURRENDERED'
                                ? '已解約'
                                : p.status === 'CLAIM_PENDING'
                                  ? '給付已核准'
                                  : p.status === 'PAID_OUT'
                                    ? '已給付並終止'
                                    : '已失效'}{' '}
                            · 第 {p.issued_month} 月投保 · 等待 {p.waiting_months} 個月
                          </p>
                          {['INVESTMENT_LIFE', 'ANNUITY'].includes(p.kind) && (
                            <p>
                              帳戶 {money(p.account_minor)} · 已付費用 {money(p.fees_paid_minor)} · 股票連結{' '}
                              {p.equity_bps / 100}%
                            </p>
                          )}
                          {p.status === 'ACTIVE' && ['INVESTMENT_LIFE', 'ANNUITY'].includes(p.kind) && (
                            <button
                              onClick={() => {
                                setPolicyId(p.id);
                                setEquity(String(p.equity_bps / 100));
                              }}
                            >
                              管理投資帳戶
                            </button>
                          )}
                        </article>
                      ))}
                    </div>
                  )}
                  {policy && ['INVESTMENT_LIFE', 'ANNUITY'].includes(policy.kind) && (
                    <div className="tr-order">
                      <h3>{policy.name} · 帳戶管理</h3>
                      <label>
                        提領金額（元）
                        <input
                          type="number"
                          min={1}
                          value={amount}
                          onChange={e => setAmount(e.target.value)}
                        />
                      </label>
                      <div className="tr-actions">
                        <button
                          onClick={() =>
                            void preview('POLICY_WITHDRAW', { policy_id: policy.id, amount_minor: value() })
                          }
                        >
                          預覽提領
                        </button>
                        <button onClick={() => void preview('POLICY_SURRENDER', { policy_id: policy.id })}>
                          預覽解約
                        </button>
                      </div>
                      <label>
                        股票連結比例（%）
                        <input
                          type="number"
                          min={0}
                          max={100}
                          step={1}
                          value={equity}
                          onChange={e => setEquity(e.target.value)}
                        />
                      </label>
                      <button
                        onClick={() =>
                          void preview('POLICY_ALLOCATE', {
                            policy_id: policy.id,
                            equity_bps: Math.round(Number(equity) * 100),
                          })
                        }
                      >
                        預覽配置調整
                      </button>
                      <small>降低股票曝險仍須支付帳戶費用，不保證不虧損。</small>
                    </div>
                  )}
                  <h3>支出與理賠</h3>
                  {claims()}
                </>
              )}
            </section>
          )}
        </>
      )}
      <details className="tr-card">
        <summary>資產與收支明細</summary>
        <div className="tr-grid">
          <p>
            股票市值 {money(r.balances.stocks_minor)}
            <br />
            保單帳戶 {money(r.balances.policy_accounts_minor)}
          </p>
          <p>
            借款 {money(r.balances.debt_minor)}
            <br />
            未付帳單 {money(r.balances.unpaid_minor)}
            <br />
            待入帳理賠 {money(r.balances.receivables_minor)}
          </p>
        </div>
        <small>待入帳理賠尚不能支付開支；不列入目前淨資產。</small>
        <div className="tr-table-scroll">
          <table>
            <thead>
              <tr>
                <th>月份</th>
                <th>項目</th>
                <th>金額</th>
              </tr>
            </thead>
            <tbody>
              {r.ledger
                .slice(-80)
                .reverse()
                .map((e, i) => (
                  <tr key={i}>
                    <td>{e.month}</td>
                    <td>{e.description}</td>
                    <td>{money(e.amount_minor)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </details>
      <small>{r.scenario_notice}</small>
      {quote && (
        <ConfirmDialog onClose={() => setQuote(null)}>
          <h2 id="tr-quote-title">確認這次安排</h2>
          <p>
            <strong>
              {quoteLabels[quote.action]}
              {quote.params.stock_id
                ? ' · ' + r.stocks.find(s => s.id === quote.params.stock_id)?.name
                : quote.params.product_id
                  ? ' · ' + r.products.find(p => p.id === quote.params.product_id)?.name
                  : quote.params.policy_id
                    ? ' · ' + r.policies.find(p => p.id === quote.params.policy_id)?.name
                    : ''}
            </strong>
          </p>
          {quote.params.quantity !== undefined && <p>交易股數：{Number(quote.params.quantity)} 股</p>}
          {quote.params.equity_bps !== undefined && (
            <p>股票連結調整為 {Number(quote.params.equity_bps) / 100}%</p>
          )}
          <p>{quote.notice}</p>
          <dl>
            {(quote.result.amount_minor !== undefined || quote.result.gross_minor !== undefined) && (
              <>
                <dt>本次金額</dt>
                <dd>{money(Number(quote.result.gross_minor ?? quote.result.amount_minor))}</dd>
              </>
            )}
            <dt>操作後可用資金</dt>
            <dd>{money(quote.after.liquidity_minor)}</dd>
            <dt>操作後淨資產</dt>
            <dd>{money(quote.after.net_worth_minor)}</dd>
            <dt>本次費用</dt>
            <dd>{money(Number(quote.result.fees_minor ?? 0))}</dd>
            {quote.result.approved_minor !== undefined && (
              <>
                <dt>核准待入帳</dt>
                <dd>{money(Number(quote.result.approved_minor))}</dd>
              </>
            )}
          </dl>
          {Object.values(quote.result)
            .filter(v => typeof v === 'string')
            .map(v => (
              <p key={v}>{v}</p>
            ))}
          <div className="tr-actions">
            <button onClick={() => setQuote(null)}>返回修改</button>
            <button
              className="tr-primary"
              onClick={() =>
                void write<Run>(
                  plan('/runs/' + run.id + '/actions', {
                    expected_version: quote.run_version,
                    action: quote.action,
                    params: quote.params,
                    confirmed: true,
                  }),
                  v => {
                    setQuote(null);
                    onRun(v);
                  },
                )
              }
            >
              確認執行
            </button>
          </div>
        </ConfirmDialog>
      )}
    </div>
  );
}
