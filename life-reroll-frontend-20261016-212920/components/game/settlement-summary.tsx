'use client';
import {useEffect,useState} from 'react';
import type {Advance} from '@/lib/game-types';
import {money} from '@/lib/dashboard';

function AnimatedAmount({value,signed=false}:{value:number;signed?:boolean}){
 const [display,setDisplay]=useState(value);
 useEffect(()=>{
  const motion=window.matchMedia('(prefers-reduced-motion: reduce)');
  if(motion.matches)return;
  let frame=0,start:number|undefined;
  function tick(now:number){
   start??=now;
   const progress=Math.min((now-start)/720,1);
   setDisplay(Math.round(value*(1-Math.pow(1-progress,3))));
   if(progress<1)frame=requestAnimationFrame(tick);
  }
  function stop(){cancelAnimationFrame(frame);setDisplay(value);}
  motion.addEventListener('change',stop);
  frame=requestAnimationFrame(tick);
  return()=>{cancelAnimationFrame(frame);motion.removeEventListener('change',stop);};
 },[value]);
 const format=(amount:number)=>(signed&&amount>0?'+':'')+money(amount);
 return <><span className="sr-only">{format(value)} 元</span><span aria-hidden="true">{format(display)}<small> 元</small></span></>;
}

export function SettlementSummary({advance:a}:{advance:Advance}){
 const delta=a.summary?.net_worth_change_minor;
 return <section className="settlement-summary" aria-label="本次人生結算">
  <div className="settlement-heading"><span className="settlement-die" aria-hidden="true">{['','⚀','⚁','⚂','⚃','⚄','⚅'][a.roll_value]??'⚄'}</span><div><span className="eyebrow">LIFE ADVANCE</span><h2>走過 {a.roll_value} 年的人生</h2><p>{a.from_date}<span aria-hidden="true"> → </span><span className="sr-only"> 至 </span>{a.current_date}{a.status==='TERMINATED'?' · 人生提前結束':''}</p></div></div>
  <div className={`settlement-total ${delta!==undefined&&delta<0?'is-negative':''}`}><span>這段期間的淨資產變化</span><strong>{delta===undefined?'推進中':<AnimatedAmount value={delta} signed/>}</strong><div className="settlement-comparison">{a.opening_snapshot&&a.closing_snapshot?<><span>期初 {money(a.opening_snapshot.balances.net_worth_minor)} 元</span><span aria-hidden="true">→</span><span>期末 {money(a.closing_snapshot.balances.net_worth_minor)} 元</span></>:<span>完成結算後顯示完整資產快照</span>}</div></div>
  <div className="settlement-metrics"><div><span>期末可用資金</span><strong>{a.closing_snapshot?<AnimatedAmount value={a.closing_snapshot.balances.immediate_liquidity_minor}/>:'尚未取得'}</strong></div><div><span>期間事件</span><strong>{a.summary?.event_ids.length??0}<small> 件</small></strong></div><div><span>理賠已入帳</span><strong>{a.summary?<AnimatedAmount value={a.summary.claims_paid_minor}/>:'尚未取得'}</strong></div></div>
  <p className="settlement-footnote">收入已含理賠，支出已含保費。可切換「資產變化」查看完整明細。</p>
 </section>;
}
