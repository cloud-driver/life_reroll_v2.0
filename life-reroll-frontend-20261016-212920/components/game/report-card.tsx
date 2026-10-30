'use client';
import {useState} from 'react';
import type {RunReport} from '@/lib/game-types';
import {money} from '@/lib/dashboard';
import {PagedList} from './paged-list';
const labels:Record<string,string>={LIQUIDITY:'資金流動性',COVERAGE:'保障準備',PREMIUM_AFFORDABILITY:'保費負擔',DEBT_RESILIENCE:'債務韌性',LIFE_QUALITY:'生活品質'};
export function ReportCard({report}:{report:RunReport}){
 const [tab,setTab]=useState('summary');
 return <div className="report-card"><div className="play-actions compact-tabs">{[['summary','摘要'],['dimensions','評量'],['cashflow','收支'],['coverage','保障'],['timeline','時間軸']].map(([id,label])=><button key={id} className={tab===id?'':'secondary'} onClick={()=>setTab(id)}>{label}</button>)}</div>
 {tab==='summary'&&<><p>{report.from_date} → {report.to_date}</p><div className="report-numbers"><div><small>期初淨資產</small><strong>{money(report.opening_net_worth_minor)} 元</strong></div><div><small>期末淨資產</small><strong>{money(report.ending_net_worth_minor)} 元</strong></div></div><p>淨資產變化 {money(report.ending_net_worth_minor-report.opening_net_worth_minor)} 元</p></>}
 {tab==='dimensions'&&<PagedList items={report.dimensions} label="人生評量" render={d=><div className="resource-row" key={d.code}><div><strong>{labels[d.code]??d.code} {d.score??'—'}／100</strong><p>{d.explanation}</p></div></div>}/>}
 {tab==='cashflow'&&<PagedList items={report.categories} label="收支分類" render={category=><div className="resource-row" key={category.code}><strong>{category.label}</strong><span>{money(category.amount_minor)} 元</span></div>}/>}
 {tab==='coverage'&&<><PagedList items={report.coverage_effects} label="保障效果" pageSize={2} render={(effect,index)=><div key={index} className="play-inline-note"><p>{effect.explanation}</p><p>自付 {money(effect.out_of_pocket_minor)} 元 · 待入帳 {money(effect.claims_pending_minor)} 元</p></div>}/><p className="muted">家屬核准給付 {money(report.estate_benefits_approved_minor)} 元，不計入生前可用資金。</p></>}
 {tab==='timeline'&&<PagedList items={report.timeline} label="人生時間軸" render={item=><div className="resource-row" key={item.id}><span>{item.date}</span><strong>{item.title}</strong></div>}/>}
 </div>;
}
