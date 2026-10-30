import { errorMessage } from '../../lib/game-client';
('use client');
import { useEffect, useState } from 'react';
import { allowed } from '@/lib/game-client';
import { money } from '@/lib/dashboard';
import { FINANCE_ACTIONS, financeInput, type FinanceAction, type FinanceForm } from '@/lib/game-finance';
import type {
  Portfolio,
  Stock,
  DepositProduct,
  LoanProduct,
  InsuranceProduct,
  Policy,
  Bill,
  Quote,
  CoverageReview,
  Transaction,
  MutationReceipt,
} from '@/lib/game-types';
import type { Page } from '@/lib/game-client';
import { useResource, type GameModel } from './use-game';
import { PagedList } from './paged-list';
import { FinanceReception, FinanceConversation, type FinanceSector } from './finance-reception';
const initial: FinanceForm = {
  amount: '10000',
  quantity: '1',
  product: '',
  stock: '',
  resource: '',
  term: 12,
  direction: 'CASH_TO_SAVINGS',
  source: 'CASH',
  coverage: 0,
  beneficiary: '家人',
  autoRenew: false,
};
export function FinancePanel({ game, funding = false }: { game: GameModel; funding?: boolean }) {
  const [sector, setSector] = useState<FinanceSector | null>(null);
  if (funding) return <FinanceService game={game} funding />;
  if (!sector) return <FinanceReception game={game} onSelect={setSector} />;
  return (
    <FinanceConversation sector={sector} onBack={() => setSector(null)} disabled={game.busy || !!game.retry}>
      <FinanceService key={sector} game={game} sector={sector} />
    </FinanceConversation>
  );
}
function FinanceService({
  game,
  funding = false,
  sector = 'bank',
}: {
  game: GameModel;
  funding?: boolean;
  sector?: FinanceSector;
}) {
  const r = game.run!,
    params = { run_id: r.id };
  const portfolio = useResource<Portfolio>(game, 'E01', params),
    stocks = useResource<Stock[]>(game, 'E02', params),
    deposits = useResource<DepositProduct[]>(game, 'E04', params),
    loans = useResource<LoanProduct[]>(game, 'E05', params),
    products = useResource<InsuranceProduct[]>(game, 'F01', params),
    policies = useResource<Policy[]>(game, 'F03', params),
    bills = useResource<Page<Bill>>(game, 'E13', params);
  const [action, setAction] = useState<FinanceAction>(
      funding ? 'LOAN_BORROW' : sector === 'life' ? 'POLICY_BUY' : 'TRANSFER',
    ),
    [form, setForm] = useState<FinanceForm>(initial),
    [quote, setQuote] = useState<Quote | null>(null),
    [confirmed, setConfirmed] = useState(false),
    [detail, setDetail] = useState<InsuranceProduct | null>(null),
    [coverage, setCoverage] = useState<CoverageReview | null>(null),
    [receipt, setReceipt] = useState<Transaction | null>(null),
    [policyDetail, setPolicyDetail] = useState<Policy | null>(null);
  const [recordTab, setRecordTab] = useState(sector === 'life' ? 'policies' : 'stocks');
  const [clock, setClock] = useState(Date.now()),
    [screen, setScreen] = useState<'choose' | 'form' | 'records'>('choose');
  useEffect(() => {
    if (!quote) return;
    setClock(Date.now());
    const timer = setInterval(() => setClock(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [quote?.id]);
  useEffect(() => {
    setQuote(null);
    setConfirmed(false);
  }, [r.id, r.version, action, form]);
  const policyProduct = products.value?.find(x => x.id === form.product),
    termProduct = deposits.value?.find(x => x.id === form.product);
  const resources =
    action === 'TERM_CLOSE'
      ? (portfolio.value?.term_deposits ?? [])
          .filter(t => t.status === 'ACTIVE')
          .map(t => ({ id: t.id, label: `定存 ${money(t.principal_minor)} 元 · ${t.matures_on}` }))
      : action === 'LOAN_REPAY'
        ? (portfolio.value?.loans ?? [])
            .filter(l => l.status !== 'PAID')
            .map(l => ({ id: l.id, label: `借款 ${money(l.outstanding_principal_minor)} 元` }))
        : action === 'BILL_PAY'
          ? (bills.value?.items ?? [])
              .filter(b => b.status !== 'PAID')
              .map(b => ({ id: b.id, label: `${b.explanation} · ${money(b.remaining_minor)} 元` }))
          : action.startsWith('POLICY_') && action !== 'POLICY_BUY'
            ? (policies.value ?? [])
                .filter(p =>
                  action === 'POLICY_REINSTATE'
                    ? p.reinstatement_available
                    : action === 'POLICY_PREMIUM_PAY'
                      ? p.status === 'GRACE'
                      : !['SURRENDERED', 'EXPIRED'].includes(p.status),
                )
                .map(p => ({
                  id: p.id,
                  label: `${products.value?.find(x => x.id === p.product_id)?.name ?? p.product_id} · ${p.status}`,
                }))
            : [];
  const availableActions = (Object.keys(FINANCE_ACTIONS) as FinanceAction[]).filter(a =>
    funding
      ? !['STOCK_BUY', 'TERM_OPEN', 'POLICY_BUY', 'POLICY_REINSTATE'].includes(a)
      : sector === 'life'
        ? a.startsWith('POLICY_')
        : !a.startsWith('POLICY_'),
  );
  const canOperate = game.online && allowed(r, 'QUOTE') && (r.scene_id === 'FINANCE' || funding);
  const dataReady = ![portfolio, stocks, deposits, loans, products, policies, bills].some(
    x => x.loading || x.error || !x.value,
  );
  const resourceRequired = [
    'TERM_CLOSE',
    'LOAN_REPAY',
    'POLICY_SURRENDER',
    'POLICY_REINSTATE',
    'POLICY_PREMIUM_PAY',
    'BILL_PAY',
  ].includes(action);
  const monetary = ['TRANSFER', 'TERM_OPEN', 'LOAN_BORROW', 'LOAN_REPAY', 'BILL_PAY'].includes(action);
  function change<K extends keyof FinanceForm>(key: K, value: FinanceForm[K]) {
    setForm(old => ({ ...old, [key]: value }));
  }
  const errors = [portfolio, stocks, deposits, loans, products, policies, bills]
    .map(x => x.error)
    .filter(Boolean);
  return (
    <section className="play-card">
      <div className="play-section-title">
        <span className="eyebrow">{funding ? 'FUNDING' : 'SERVICE'}</span>
        <h2>{funding ? '資產籌資操作' : sector === 'life' ? '保障服務' : '資產服務'}</h2>
        <p>股票、商品及費率為教學模擬。每筆操作先預覽，再確認。</p>
      </div>
      {errors.length > 0 && <p role="alert">資料無法讀取：{errors[0]}</p>}
      <div className="finance-screen-nav">
        <button
          className="quiet"
          disabled={game.busy}
          onClick={() => {
            setScreen('choose');
            setQuote(null);
            setDetail(null);
            setCoverage(null);
            setPolicyDetail(null);
          }}
        >
          ← 選擇服務
        </button>
        <button
          className="quiet"
          disabled={game.busy}
          onClick={() => {
            setScreen('records');
            setQuote(null);
          }}
        >
          我的紀錄
        </button>
      </div>
      {screen === 'choose' && !quote && (
        <div className="finance-service-options" role="group" aria-label="選擇服務">
          {availableActions.map((a, index) => (
            <button
              key={a}
              type="button"
              aria-pressed={action === a}
              disabled={game.busy || !!game.retry}
              className={action === a ? 'selected' : 'secondary'}
              onClick={() => {
                setAction(a);
                setForm({ ...initial });
                setReceipt(null);
                setDetail(null);
                setPolicyDetail(null);
                setScreen('form');
              }}
            >
              <span aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
              {FINANCE_ACTIONS[a]}
            </button>
          ))}
        </div>
      )}
      {screen === 'form' && !quote && (
        <>
          <h3 className="finance-form-title">{FINANCE_ACTIONS[action]}</h3>
          <div className="play-form-grid">
            {monetary && (
              <label>
                金額（元）
                <input
                  inputMode="decimal"
                  value={form.amount}
                  onChange={e => change('amount', e.target.value)}
                />
              </label>
            )}
            {action === 'TRANSFER' && (
              <label>
                轉帳方向
                <select
                  value={form.direction}
                  onChange={e => change('direction', e.target.value as FinanceForm['direction'])}
                >
                  <option value="CASH_TO_SAVINGS">現金轉入活存</option>
                  <option value="SAVINGS_TO_CASH">活存提領為現金</option>
                </select>
              </label>
            )}
            {['STOCK_BUY', 'STOCK_SELL'].includes(action) && (
              <>
                <p className="play-muted">股價可能連跌多年；買賣各收 0.3% 模擬交易費，最低 1 元。</p>
                <label>
                  股票
                  <select value={form.stock} onChange={e => change('stock', e.target.value)}>
                    <option value="">選擇股票</option>
                    {stocks.value?.map(s => (
                      <option key={s.id} value={s.id}>
                        {s.name} · 每股 {money(s.price_minor)} 元
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  股數
                  <input
                    inputMode="numeric"
                    value={form.quantity}
                    onChange={e => change('quantity', e.target.value)}
                  />
                </label>
              </>
            )}
            {action === 'TERM_OPEN' && (
              <>
                <label>
                  定存商品
                  <select
                    value={form.product}
                    onChange={e => {
                      const p = deposits.value?.find(x => x.id === e.target.value);
                      setForm({ ...form, product: e.target.value, term: p?.term_months ?? 12 });
                    }}
                  >
                    <option value="">選擇商品</option>
                    {deposits.value
                      ?.filter(p => p.kind === 'TERM')
                      .map(p => (
                        <option key={p.id} value={p.id}>
                          {p.name} · 年利率 {p.annual_rate_bps / 100}%
                        </option>
                      ))}
                  </select>
                </label>
                <label>
                  本金來源
                  <select
                    value={form.source}
                    onChange={e => change('source', e.target.value as FinanceForm['source'])}
                  >
                    <option value="CASH">現金</option>
                    <option value="SAVINGS">活存</option>
                  </select>
                </label>
                <label className="check-label">
                  <input
                    type="checkbox"
                    checked={form.autoRenew}
                    onChange={e => change('autoRenew', e.target.checked)}
                  />
                  到期自動續存
                </label>
                {termProduct && <p>{termProduct.early_exit_rule}</p>}
              </>
            )}
            {action === 'LOAN_BORROW' && (
              <>
                <label>
                  借款方案
                  <select value={form.product} onChange={e => change('product', e.target.value)}>
                    <option value="">選擇方案</option>
                    {loans.value?.map(p => (
                      <option key={p.id} value={p.id}>
                        {p.name} · 年息 {p.annual_rate_bps / 100}%
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  期限
                  <select value={form.term} onChange={e => change('term', Number(e.target.value))}>
                    {[12, 24, 36, 60].map(m => (
                      <option key={m} value={m}>
                        {m} 個月
                      </option>
                    ))}
                  </select>
                </label>
              </>
            )}
            {resourceRequired && (
              <label>
                選擇資產／帳單
                <select value={form.resource} onChange={e => change('resource', e.target.value)}>
                  <option value="">選擇一筆資料</option>
                  {resources.map(p => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </select>
                {resources.length === 0 && <small>目前沒有適用資料。</small>}
              </label>
            )}
            {action === 'POLICY_BUY' && (
              <>
                <label>
                  保險商品
                  <select
                    value={form.product}
                    onChange={e => {
                      setForm({ ...form, product: e.target.value, coverage: 0 });
                      setDetail(null);
                    }}
                  >
                    <option value="">選擇商品</option>
                    {products.value
                      ?.filter(p => p.enabled)
                      .map(p => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                  </select>
                </label>
                <label>
                  保額
                  <select value={form.coverage} onChange={e => change('coverage', Number(e.target.value))}>
                    <option value={0}>選擇保額</option>
                    {policyProduct?.coverage_options_minor.map(n => (
                      <option key={n} value={n}>
                        {money(n)} 元
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  受益人稱呼
                  <input
                    maxLength={40}
                    value={form.beneficiary}
                    onChange={e => change('beneficiary', e.target.value)}
                  />
                </label>
                {policyProduct && (
                  <div className="play-inline-note">
                    <p>{policyProduct.plain_summary}</p>
                    <p>等待期 {policyProduct.waiting_days} 天；本版採年繳，金額以確認單為準。</p>
                    <button
                      className="secondary"
                      disabled={game.busy}
                      onClick={() =>
                        void game.perform(async () =>
                          setDetail(
                            await game.api.call<InsuranceProduct>('F02', {
                              ...params,
                              product_id: policyProduct.id,
                            }),
                          ),
                        )
                      }
                    >
                      查看完整條款
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
          {detail && (
            <details className="play-details" open>
              <summary>
                {detail.name} · 商品版本 {detail.version}
              </summary>
              <p>{detail.eligibility_summary}</p>
              <p>{detail.premium_rule_summary}</p>
              {detail.benefits.map((b, i) => (
                <p key={i}>
                  {b.trigger_summary} · 最高 {money(b.limit_minor)} 元 · 等待 {b.waiting_days} 天；
                  {b.exclusions.join('、')}
                </p>
              ))}
              <p>{detail.renewal_summary}</p>
              <p>{detail.surrender_summary}</p>
              {detail.simulation_differences.map(t => (
                <p key={t}>{/^[A-Z][A-Z0-9_]+$/.test(t) ? errorMessage(t) : t}</p>
              ))}
            </details>
          )}
          <div className="play-actions">
            <button
              disabled={game.busy || !canOperate || !dataReady}
              onClick={() =>
                void game.perform(async () => {
                  setConfirmed(false);
                  setReceipt(null);
                  setQuote(await game.write<Quote>('E08', params, financeInput(action, form, r.version)));
                })
              }
            >
              預覽操作確認單
            </button>
            {(funding || sector === 'life') && (
              <button
                className="secondary"
                disabled={game.busy}
                onClick={() =>
                  void game.perform(async () =>
                    setCoverage(await game.api.call<CoverageReview>('F06', params)),
                  )
                }
              >
                檢視保障缺口
              </button>
            )}
          </div>
        </>
      )}
      {quote && (
        <div className="quote-panel">
          <h3>{FINANCE_ACTIONS[quote.action as FinanceAction]}確認單</h3>
          <p>{quote.summary}</p>
          <dl className="play-data-list">
            {quote.effects.map((e, i) => (
              <div key={i}>
                <dt>{e.description}</dt>
                <dd>
                  {e.delta_minor > 0 ? '+' : ''}
                  {money(e.delta_minor)} 元 · {e.available_on}
                </dd>
              </div>
            ))}
            <div>
              <dt>費用</dt>
              <dd>{money(quote.fees_minor)} 元</dd>
            </div>
          </dl>
          {[...quote.coverage_changes, ...quote.warnings, ...quote.denial_reasons].map(t => (
            <p key={t}>{/^[A-Z][A-Z0-9_]+$/.test(t) ? errorMessage(t) : t}</p>
          ))}
          <button
            className="secondary"
            disabled={game.busy}
            onClick={() =>
              void game.perform(async () =>
                setQuote(await game.api.call<Quote>('E09', { ...params, quote_id: quote.id })),
              )
            }
          >
            重新讀取確認單
          </button>
          <p>
            有效至 {new Date(quote.expires_at).toLocaleTimeString('zh-TW')} ·{' '}
            {clock >= Date.parse(quote.expires_at) ? '已過期' : quote.eligible ? '可執行' : '無法執行'}
          </p>
          <label className="check-label">
            <input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />
            我已確認費用與保障影響
          </label>
          <button
            disabled={
              game.busy ||
              !confirmed ||
              !quote.eligible ||
              quote.run_version !== r.version ||
              clock >= Date.parse(quote.expires_at)
            }
            onClick={() =>
              void game.perform(async () => {
                const result = await game.write<MutationReceipt>(
                  'E10',
                  params,
                  { quote_id: quote.id, confirmed: true },
                  true,
                );
                setQuote(null);
                setConfirmed(false);
                setScreen('choose');
                await game.refresh();
                const transactionId = result.resource?.href.match(/\/transactions\/([^/]+)$/)?.[1];
                if (transactionId)
                  setReceipt(
                    await game.api.call<Transaction>('E11', { ...params, transaction_id: transactionId }),
                  );
              }, '交易已完成')
            }
          >
            確認執行
          </button>
        </div>
      )}
      {receipt && (
        <p>
          交易回條：{receipt.id} · {receipt.status}
        </p>
      )}
      {coverage && (
        <div className="play-inline-note">
          <h3>目前保障缺口</h3>
          {coverage.needs.map(n => (
            <p key={n.topic}>
              {n.topic}：{money(n.gap_minor)} 元 · {n.explanation}
            </p>
          ))}
          <p>
            可用資金約 {coverage.liquidity_months} 個月；保費負擔比{' '}
            {coverage.premium_burden_ratio === null
              ? '—'
              : `${Math.round(coverage.premium_burden_ratio * 100)}%`}
            。
          </p>
        </div>
      )}
      {policyDetail && (
        <div className="play-inline-note">
          <h3>保單詳細</h3>
          <p>
            保額 {money(policyDetail.coverage_minor)} 元 · 每期保費 {money(policyDetail.premium_minor)} 元 ·{' '}
            {policyDetail.status}
          </p>
          <p>
            承保 {policyDetail.issued_on} · 生效 {policyDetail.coverage_from} · 終止{' '}
            {policyDetail.coverage_until ?? '尚未終止'}
          </p>
          <p>
            受益人：{policyDetail.beneficiary_label} · 保障條款版本 {policyDetail.product_version}
          </p>
        </div>
      )}
      {screen === 'records' && (
        <>
          <div className="play-actions compact-tabs">
            {(sector === 'life'
              ? [['policies', '保單']]
              : [
                  ['stocks', '持股'],
                  ['terms', '定存'],
                  ['bills', '帳單'],
                ]
            ).map(([id, label]) => (
              <button
                key={id}
                className={recordTab === id ? '' : 'secondary'}
                onClick={() => setRecordTab(id)}
              >
                {label}
              </button>
            ))}
          </div>
          {recordTab === 'stocks' && (
            <>
              <PagedList
                items={portfolio.value?.holdings ?? []}
                render={h => (
                  <p key={h.stock_id}>
                    {stocks.value?.find(s => s.id === h.stock_id)?.name ?? h.stock_id}：{h.quantity} 股 · 市值{' '}
                    {money(h.market_value_minor)} 元
                  </p>
                )}
              />
            </>
          )}
          {recordTab === 'terms' && (
            <>
              <PagedList
                items={portfolio.value?.term_deposits ?? []}
                render={t => (
                  <div className="resource-row" key={t.id}>
                    <span>
                      {money(t.principal_minor)} 元 · 到期 {t.matures_on} · {t.status}
                    </span>
                    <button
                      className="secondary"
                      disabled={game.busy || !canOperate || funding || t.status !== 'ACTIVE'}
                      onClick={() =>
                        void game.perform(async () => {
                          await game.write(
                            'E12',
                            { ...params, term_deposit_id: t.id },
                            { auto_renew: !t.auto_renew },
                            true,
                          );
                          await game.refresh();
                        }, '續存設定已更新')
                      }
                    >
                      {t.auto_renew ? '關閉' : '開啟'}自動續存
                    </button>
                  </div>
                )}
              />
            </>
          )}
          {recordTab === 'policies' && (
            <>
              {policies.value?.length === 0 && <p>尚未投保。</p>}
              <PagedList
                items={policies.value ?? []}
                render={p => (
                  <div className="resource-row" key={p.id}>
                    <div>
                      <strong>
                        {products.value?.find(x => x.id === p.product_id)?.name ?? p.product_id}
                      </strong>
                      <p>
                        保額 {money(p.coverage_minor)} 元 · {p.status} · 生效 {p.coverage_from}
                      </p>
                      <small>
                        下次保費 {p.next_premium_on ?? '—'} · 版本 {p.product_version}
                      </small>
                      <button
                        className="quiet"
                        disabled={game.busy}
                        onClick={() =>
                          void game.perform(async () =>
                            setPolicyDetail(
                              await game.api.call<Policy>('F04', { ...params, policy_id: p.id }),
                            ),
                          )
                        }
                      >
                        保單詳細
                      </button>
                    </div>
                    <button
                      className="secondary"
                      disabled={game.busy || !canOperate || funding}
                      onClick={() =>
                        void game.perform(async () => {
                          await game.write(
                            'F05',
                            { ...params, policy_id: p.id },
                            { auto_pay: !p.auto_pay },
                            true,
                          );
                          await game.refresh();
                        }, '繳費設定已更新')
                      }
                    >
                      {p.auto_pay ? '關閉' : '開啟'}自動繳費
                    </button>
                  </div>
                )}
              />
            </>
          )}
          {recordTab === 'bills' && (
            <>
              <PagedList
                items={bills.value?.items.filter(b => b.status !== 'PAID') ?? []}
                render={b => (
                  <p key={b.id}>
                    {b.explanation}：{money(b.remaining_minor)} 元 · {b.status}
                  </p>
                )}
              />
            </>
          )}
        </>
      )}
    </section>
  );
}
