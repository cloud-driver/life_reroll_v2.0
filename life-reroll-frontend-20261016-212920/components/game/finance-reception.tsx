'use client';
import {ArrowLeft,ArrowUpRight,Landmark,ShieldCheck} from 'lucide-react';
import {useEffect,useRef} from 'react';
import {money} from '@/lib/dashboard';
import type {ReactNode} from 'react';
import type {GameModel} from './use-game';
export type FinanceSector='bank'|'life';
export const financeSectors={
 bank:{name:'投資中心＆銀行',english:'INVESTMENT & BANKING',speaker:'資產服務專員',line:'讓每一筆資金，都有適合的去處。',description:'日常存提款、定存與股票交易，從這裡開始安排。',icon:Landmark},
 life:{name:'人壽服務',english:'LIFE & PROTECTION',speaker:'保障服務專員',line:'在變動的人生裡，為重要的事留一份安心。',description:'了解保障、檢視保單，為下一段人生做好準備。',icon:ShieldCheck},
};
export function FinanceReception({game,onSelect}:{game:GameModel;onSelect:(sector:FinanceSector)=>void}){
 return <section className="finance-reception" aria-label="金融大樓服務大廳">
  <div className="finance-lobby-scene"><img src="/scene-finance.webp" alt=""/><div className="finance-lobby-copy"><span className="eyebrow">LIFE REROLL · FINANCIAL DISTRICT</span><h2>下一段人生，<br/>從容安排。</h2><p>歡迎來到金融大樓。<br/>今天，想先聊聊資產，還是保障？</p></div><span className="finance-location">金融大樓 / 服務大廳</span></div>
  <div className="finance-lobby-services"><div className="finance-lobby-intro"><span className="eyebrow">RECEPTION</span><h3>選擇服務區域</h3><p>依照你的步調，一次安排一件事。</p></div>
  {(Object.keys(financeSectors) as FinanceSector[]).map((sector,index)=>{const data=financeSectors[sector],Icon=data.icon;return <button className={`finance-sector-card sector-${sector}`} key={sector} disabled={game.busy||!!game.retry} onClick={()=>onSelect(sector)}><span className="finance-sector-number">0{index+1}</span><Icon size={28} strokeWidth={1.3}/><span className="finance-sector-text"><small>{data.english}</small><strong>{data.name}</strong><span>{data.description}</span></span><ArrowUpRight size={20}/></button>;})}
  <div className="finance-lobby-balance"><span>目前可用資金</span><strong>{money(game.run!.balances.immediate_liquidity_minor)}<small> 元</small></strong></div><p className="finance-simulation-note">商品與費率皆為教育模擬。</p></div>
 </section>;
}
export function FinanceConversation({sector,onBack,disabled,children}:{sector:FinanceSector;onBack:()=>void;disabled:boolean;children:ReactNode}){
 const data=financeSectors[sector],Icon=data.icon,heading=useRef<HTMLHeadingElement>(null);
 useEffect(()=>{heading.current?.focus({preventScroll:true});},[sector]);
 return <section className={`finance-conversation sector-${sector}`}>
  <aside className="finance-advisor"><img src="/scene-finance.webp" alt=""/><div className="finance-advisor-top"><span className="eyebrow">{data.english}</span><span>私人會談 / 服務中</span></div><div className="finance-advisor-emblem" aria-hidden="true"><span/><Icon size={66} strokeWidth={1}/></div><div className="finance-dialogue"><span className="finance-speaker">{data.speaker}</span><h2 ref={heading} tabIndex={-1}>{data.name}</h2><p key={sector}>{data.line}</p><span className="finance-dialogue-rule" aria-hidden="true">◆</span><small>選擇右側服務，我們一起確認每個細節。</small></div></aside>
  <div className="finance-service-body"><button className="quiet finance-back" disabled={disabled} onClick={onBack}><ArrowLeft size={16}/>返回服務大廳</button>{children}</div>
 </section>;
}
