import type {Advance,AssetSnapshot,Balances,Event,Claim} from './game-types';
export type DemoState={format:1;age:number;year:number;rolls:number;cash:number;savings:number;holdings:{stock_id:string;quantity:number;price:number}[]};
export type DemoTurn={state:DemoState;advance:Advance;events:Event[];claims:Claim[]};
export const DEMO_SAVE_KEY='life-reroll:minimal-demo:v1';
export function initialDemo():DemoState{return {format:1,age:28,year:2026,rolls:0,cash:18000000,savings:30000000,holdings:[{stock_id:'STABLE',quantity:500,price:10000},{stock_id:'TECH',quantity:300,price:10000}]};}
export function demoSnapshot(state:DemoState):AssetSnapshot{
 const stocks=state.holdings.reduce((sum,h)=>sum+h.quantity*h.price,0);
 const balances:Balances={cash_minor:state.cash,savings_minor:state.savings,term_principal_minor:0,stocks_market_value_minor:stocks,policy_cash_value_minor:0,receivables_minor:0,liabilities_minor:0,immediate_liquidity_minor:state.cash+state.savings,net_worth_minor:state.cash+state.savings+stocks,negative_since:null,negative_years:0};
 return {as_of:`${state.year}-01-01`,balances,term_interest_minor:0,holdings:state.holdings.map(h=>({stock_id:h.stock_id,quantity:h.quantity,cost_basis_minor:h.quantity*10000,market_value_minor:h.quantity*h.price,unrealized_pnl_minor:h.quantity*(h.price-10000)})),active_policy_count:1,lapsed_policy_count:0,annual_premium_minor:1200000};
}
export function advanceDemo(before:DemoState,years:number):DemoTurn{
 if(!Number.isInteger(years)||years<1||years>6)throw Error('Invalid demo roll');
 const state:DemoState={...before,holdings:before.holdings.map(h=>({...h})),age:before.age+years,year:before.year+years,rolls:before.rolls+1};
 const opening=demoSnapshot(before);let interest=0;
 for(let year=0;year<years;year++){const accrued=Math.round(state.savings*80/10000);state.savings+=accrued;interest+=accrued;for(const h of state.holdings){const rate=before.rolls%3===2?-400:h.stock_id==='STABLE'?300:650;h.price=Math.max(100,Math.round(h.price*(10000+rate)/10000));}}
 const income=5000000*12*years+interest,premium=1200000*years,hasEvent=state.rolls%2===1,cost=hasEvent?7500000:0,paid=hasEvent?4500000:0,expense=3000000*12*years+premium+cost;
 // Salary and claims enter cash; savings interest has already entered savings.
 state.cash+=income-interest+paid-expense;
 const closing=demoSnapshot(state),eventId=`demo-event-${state.rolls}`,date=`${before.year+1}-01-01`;
 const events:Event[]=hasEvent?[{id:eventId,visual_key:'DEMO_ACCIDENT',kind:'ACCIDENT',title:'示範事件：通勤事故',narrative:'這是一筆用來展示事故圖片、支出與保險互動的固定範例。此次示範自動完成處理，不需選擇或送出理賠。',occurred_on:date,status:'ACKNOWLEDGED',choices:[],evidence:[],is_rebirth_anchor:false,learning_topic_ids:[],outcome:{choice_id:'demo-auto',summary:'範例支出 75,000 元、模擬理賠入帳 45,000 元，自付 30,000 元。',learning_message:'實際保單的保障與核付條件需依完整後端判定。',ledger_entry_ids:[],claim_ids:[`demo-claim-${state.rolls}`],is_terminal:false}}]:[];
 const claims:Claim[]=hasEvent?[{id:`demo-claim-${state.rolls}`,recipient:'PLAYER',event_id:eventId,policy_id:'demo-policy',benefit_code:'DEMO_ACCIDENT',status:'PAID',approved_minor:paid,paid_minor:paid,payable_on:date,reason_codes:[],explanation:'固定展示範例，非實際理賠結果。',required_evidence_ids:[],ledger_entry_ids:[]}]:[];
 const advance:Advance={id:`demo-turn-${state.rolls}`,run_id:'minimal-demo',roll_value:years,from_date:opening.as_of,target_date:closing.as_of,current_date:closing.as_of,remaining_days:0,status:'COMPLETED',blocking_event_id:null,opening_snapshot:opening,closing_snapshot:closing,summary:{from_date:opening.as_of,to_date:closing.as_of,income_minor:income+paid,expense_minor:expense,premium_minor:premium,claims_paid_minor:paid,net_worth_change_minor:closing.balances.net_worth_minor-opening.balances.net_worth_minor,event_ids:events.map(e=>e.id)}};
 return {state,advance,events,claims};
}
export function readDemoSave(raw:string|null):DemoState{
 try{const s=JSON.parse(raw??'null') as DemoState;if(s?.format!==1||![s.age,s.year,s.rolls,s.cash,s.savings].every(Number.isSafeInteger)||s.age<28||s.year<2026||s.rolls<0||s.cash<0||s.savings<0||!Array.isArray(s.holdings)||s.holdings.length!==2||!s.holdings.every(h=>typeof h.stock_id==='string'&&[h.quantity,h.price].every(Number.isSafeInteger)&&h.quantity>=0&&h.price>0))return initialDemo();return s;}catch{return initialDemo();}
}
