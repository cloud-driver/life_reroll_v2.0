'use client';
import {useState} from 'react';
import {money} from '@/lib/dashboard';
import type {LedgerEntry,Event,PeriodSummary,PricePoint,Stock} from '@/lib/game-types';
import type {Page} from '@/lib/game-client';
import {useResource,type GameModel} from './use-game';
import {PagedList} from './paged-list';
export function HistoryPanel({game}:{game:GameModel}){
 const r=game.run!,params={run_id:r.id};
 const ledger=useResource<Page<LedgerEntry>>(game,'E06',params),events=useResource<Page<Event>>(game,'D04',params),stocks=useResource<Stock[]>(game,'E02',params);
 const [tab,setTab]=useState('ledger'),[from,setFrom]=useState('2026-01-01'),[to,setTo]=useState(r.sim_date),[summary,setSummary]=useState<PeriodSummary|null>(null),[past,setPast]=useState<Event|null>(null),[prices,setPrices]=useState<Page<PricePoint>|null>(null);
 return <section className="history-panel"><div className="play-actions compact-tabs">{[['ledger','收支'],['summary','期間摘要'],['events','事件'],['prices','股價']].map(([id,label])=><button key={id} className={tab===id?'':'secondary'} onClick={()=>{setTab(id);setPast(null);}}>{label}</button>)}</div>
 {[ledger.error,events.error,stocks.error].filter(Boolean).map(error=><p role="alert" key={error}>{error}</p>)}
 {tab==='ledger'&&<>{ledger.loading&&<p>讀取收支中…</p>}<PagedList items={(ledger.value?.items??[]).toReversed()} label="收支紀錄" render={entry=><div key={entry.id} className="resource-row"><div><strong>{entry.description}</strong><p>{entry.sim_date} · {({INCOME:'收入',EXPENSE:'支出',INTERNAL:'資產移轉',NONE:'其他'} as Record<string,string>)[entry.cashflow_class]}</p></div><span className={entry.amount_minor<0?'amount-negative':''}>{money(entry.amount_minor)} 元</span></div>}/></>}
 {tab==='summary'&&<><div className="play-form-grid"><label>開始日期<input type="date" max={r.sim_date} value={from} onChange={e=>setFrom(e.target.value)}/></label><label>結束日期<input type="date" max={r.sim_date} value={to} onChange={e=>setTo(e.target.value)}/></label></div><button disabled={game.busy||!from||!to||from>to||to>r.sim_date} onClick={()=>void game.perform(async()=>setSummary(await game.api.call<PeriodSummary>('E07',params,undefined,{from_date:from,to_date:to})))}>查看期間摘要</button>{summary&&<div className="play-inline-note"><p>收入 {money(summary.income_minor)} 元 · 支出 {money(summary.expense_minor)} 元</p><p>保費 {money(summary.premium_minor)} 元 · 理賠入帳 {money(summary.claims_paid_minor)} 元</p><p>淨資產變化 {money(summary.net_worth_change_minor)} 元</p></div>}</>}
 {tab==='events'&&(past?<><button className="quiet" onClick={()=>setPast(null)}>← 返回事件列表</button><h3>{past.title}</h3><p>{past.narrative}</p><p>{past.outcome?.summary}</p></>:<PagedList items={(events.value?.items??[]).toReversed()} label="事件紀錄" render={event=><button key={event.id} className="history-event" disabled={game.busy} onClick={()=>setPast(event)}>{event.occurred_on} · {event.title}</button>}/>)}
 {tab==='prices'&&<><div className="play-actions">{stocks.value?.map(stock=><button className="secondary" key={stock.id} disabled={game.busy} onClick={()=>void game.perform(async()=>setPrices(await game.api.call<Page<PricePoint>>('E03',{...params,stock_id:stock.id},undefined,{to_date:r.sim_date})))}>{stock.name}</button>)}</div>{prices&&<PagedList items={prices.items.toReversed()} pageSize={6} label="歷史股價" render={point=><p key={point.date}>{point.date}：{money(point.price_minor)} 元</p>}/>}</>}
 </section>;
}
