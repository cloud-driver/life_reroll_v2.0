'use client';
import {useState} from 'react';
import {useResource,type GameModel} from './use-game';
import type {Policy,Claim} from '@/lib/game-types';
import type {Page} from '@/lib/game-client';
import {money} from '@/lib/dashboard';
import {PagedList} from './paged-list';
export function InsurancePanel({game}:{game:GameModel}){
 const params={run_id:game.run!.id},policies=useResource<Policy[]>(game,'F03',params),claims=useResource<Page<Claim>>(game,'F09',params);
 const [tab,setTab]=useState('policies');
 return <><div className="play-actions compact-tabs"><button className={tab==='policies'?'':'secondary'} onClick={()=>setTab('policies')}>我的保單</button><button className={tab==='claims'?'':'secondary'} onClick={()=>setTab('claims')}>理賠進度</button></div>
 {[policies.error,claims.error].filter(Boolean).map(error=><p role="alert" key={error}>{error}</p>)}
 {(policies.loading||claims.loading)&&<p>正在整理保障紀錄…</p>}
 {tab==='policies'&&<>{policies.value?.length===0&&<p>目前沒有保單，可在金融大樓的人壽服務區了解保障。</p>}<PagedList items={policies.value??[]} pageSize={2} label="保單" render={policy=><div className="play-inline-note" key={policy.id}><strong>{policy.product_id} · {policy.status}</strong><p>保額 {money(policy.coverage_minor)} 元 · 保費 {money(policy.premium_minor)} 元</p><p>生效 {policy.coverage_from} · 下次繳費 {policy.next_premium_on??'無'}</p></div>}/></>}
 {tab==='claims'&&<>{claims.value?.items.length===0&&<p>尚無理賠紀錄。</p>}<PagedList items={(claims.value?.items??[]).toReversed()} pageSize={2} label="理賠" render={claim=><div className="play-inline-note" key={claim.id}><strong>{claim.benefit_code} · {({PAID:'已入帳',APPROVED:'核准未入帳',NEEDS_INFO:'待補件',REJECTED:'未核准',SUBMITTED:'審查中'} as Record<string,string>)[claim.status]??claim.status}</strong><p>核准 {money(claim.approved_minor)} 元 · 已入帳 {money(claim.paid_minor)} 元</p><p>{claim.explanation}</p></div>}/><p className="muted">在事件畫面核對保障並申請理賠；核准後的待入帳金額尚不可支付。</p></>}
 </>;
}
