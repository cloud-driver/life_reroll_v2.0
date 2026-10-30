'use client';
import {useState} from 'react';
import {useResource,type GameModel} from './use-game';
import type {Advance,Event,Claim,Portfolio} from '@/lib/game-types';
import type {Page} from '@/lib/game-client';
import {money} from '@/lib/dashboard';
import {AdvanceReview} from './advance-review';
import {SettlementSummary} from './settlement-summary';
import {EventMedia} from './event-media';
import {HistoryPanel} from './history-panel';
import {PagedList} from './paged-list';
export function AssetsPanel({game}:{game:GameModel}){
 const r=game.run!,portfolio=useResource<Portfolio>(game,'E01',{run_id:r.id});
 const [tab,setTab]=useState('assets');
 return <><div className="play-actions">{[['assets','資產'],['investments','投資'],['ledger','收支與帳單紀錄']].map(([id,label])=><button key={id} className={tab===id?'':'secondary'} onClick={()=>setTab(id)}>{label}</button>)}</div>{portfolio.error&&<p role="alert">{portfolio.error}</p>}{tab==='assets'&&<><dl className="play-data-list">{[['現金',r.balances.cash_minor],['活存',r.balances.savings_minor],['定存本金',r.balances.term_principal_minor],['投資市值',r.balances.stocks_market_value_minor],['應收未入帳',r.balances.receivables_minor],['負債',r.balances.liabilities_minor],['可用資金',r.balances.immediate_liquidity_minor],['淨資產',r.balances.net_worth_minor]].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{money(value as number)} 元</dd></div>)}</dl><p>可用資金為現金與活存；應收款尚不可支付。交易請前往金融大樓。</p></>}{tab==='investments'&&(portfolio.loading?<p>正在讀取投資組合…</p>:<>{portfolio.value?.holdings.map(h=><div className="play-inline-note" key={h.stock_id}><strong>{h.stock_id} · {h.quantity} 股</strong><p>成本 {money(h.cost_basis_minor)} 元 · 市值 {money(h.market_value_minor)} 元</p></div>)}<h3>定存</h3>{portfolio.value?.term_deposits.map(t=><p key={t.id}>{money(t.principal_minor)} 元 · {t.matures_on} 到期 · {t.status}</p>)}<h3>借款</h3>{portfolio.value?.loans.map(l=><p key={l.id}>未還本金 {money(l.outstanding_principal_minor)} 元 · {l.status}</p>)}</>)}{tab==='ledger'&&<HistoryPanel game={game}/>}</>;
}
export {InsurancePanel} from './insurance-panel';
export function SettlementPanel({game,onDone,onEvent}:{game:GameModel;onDone:()=>void;onEvent:()=>void}){
 const r=game.run!,p={run_id:r.id},advance=useResource<Advance>(game,'D02',{...p,advance_id:r.advance_id??''},!!r.advance_id),events=useResource<Page<Event>>(game,'D04',p),claims=useResource<Page<Claim>>(game,'F09',p);
 const [tab,setTab]=useState('summary'),[selected,setSelected]=useState('');
 const a=advance.value,event=events.value?.items.find(e=>e.id===selected),errors=[advance.error,events.error,claims.error].filter(Boolean);
 if(!r.advance_id)return <p>還沒有結算。在家完成初始配置後，就可以擲骰。</p>;
 if(errors.length)return <div role="alert"><p>{errors.join('；')}</p><button onClick={()=>{advance.reload();events.reload();claims.reload();}}>重新讀取結算</button></div>;
 if(!a||!events.value||!claims.value)return <p role="status">正在整理本次資產與事件…</p>;
 const waiting=r.status==='TURN_REVIEW';
 return <><div className="play-actions settlement-tabs">{[['summary','本次摘要'],['assets','資產變化'],['events','期間事件']].map(([id,label])=><button key={id} className={tab===id?'':'secondary'} onClick={()=>setTab(id)}>{label}</button>)}</div>{tab==='summary'&&<SettlementSummary key={a.id} advance={a}/>}{tab==='assets'&&<AdvanceReview advance={a} events={events.value.items} claims={claims.value.items} onEvent={id=>{setSelected(id);setTab('events');}} canRewind={false} showRewind={false}/ >}{tab==='events'&&<>{!event&&<PagedList items={events.value.items.filter(e=>a.summary?.event_ids.includes(e.id))} label="期間事件" render={e=><button key={e.id} className="history-event" onClick={()=>setSelected(e.id)}>{e.occurred_on} · {e.title}</button>}/>}{!a.summary?.event_ids.length&&<p>這段期間沒有事件。</p>}{event&&<><button className="quiet" onClick={()=>setSelected('')}>← 返回事件列表</button><EventMedia event={event} runId={r.id}/><h3>{event.title}</h3><p>{event.narrative}</p><p>{event.outcome?.summary??'事件尚待處理'}</p></>}</>}
 <div className="settlement-actions">{waiting?<button disabled={game.busy||!!game.retry} onClick={()=>void game.perform(async()=>{await game.write('D03',{...p,advance_id:a.id},{},true);await game.refresh();onDone();},'結算已確認')}>確認結算並回到地圖</button>:['EVENT_PENDING','EVENT_RESULT','FUNDING'].includes(r.status)?<button onClick={onEvent}>繼續處理本次事件</button>:<button onClick={onDone}>返回地圖</button>}</div></>;
}
