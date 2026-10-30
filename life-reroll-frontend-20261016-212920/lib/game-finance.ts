import type {QuoteInput} from './game-types';
export type FinanceAction=QuoteInput['action'];
export const FINANCE_ACTIONS:Record<FinanceAction,string>={TRANSFER:'現金與活存轉帳',TERM_OPEN:'開立定存',TERM_CLOSE:'定存解約',STOCK_BUY:'買入股票',STOCK_SELL:'賣出股票',LOAN_BORROW:'申請借款',LOAN_REPAY:'償還借款',POLICY_BUY:'投保模擬保險',POLICY_SURRENDER:'保單解約',POLICY_REINSTATE:'保單復效',POLICY_PREMIUM_PAY:'補繳保費',BILL_PAY:'支付帳單'};
export function toMinor(value:string):number {
 if(!/^\d+(\.\d{1,2})?$/.test(value))throw Error('請輸入正數金額，最多兩位小數。');
 const [whole,dec='']=value.split('.');const minor=Number(whole)*100+Number(dec.padEnd(2,'0'));
 if(!Number.isSafeInteger(minor)||minor<=0||minor>100000000000)throw Error('金額超出可用範圍。');
 return minor;
}
export type FinanceForm={amount:string;quantity:string;product:string;stock:string;resource:string;term:number;direction:'CASH_TO_SAVINGS'|'SAVINGS_TO_CASH';source:'CASH'|'SAVINGS';coverage:number;beneficiary:string;autoRenew:boolean};
export function financeInput(action:FinanceAction,form:FinanceForm,version:number):QuoteInput {
 const required=(v:string)=>{if(!v)throw Error('請先選擇一筆有效的商品或資產。');return v;};
 const base={expected_version:version};
 switch(action){
 case 'TRANSFER':return {...base,action,params:{from_account:form.direction==='CASH_TO_SAVINGS'?'CASH':'SAVINGS',to_account:form.direction==='CASH_TO_SAVINGS'?'SAVINGS':'CASH',amount_minor:toMinor(form.amount)}};
 case 'TERM_OPEN':if(![6,12,24,36].includes(form.term))throw Error('定存期限不符商品。');return {...base,action,params:{product_id:required(form.product),amount_minor:toMinor(form.amount),term_months:form.term as 6|12|24|36,source_account:form.source,auto_renew:form.autoRenew}};
 case 'TERM_CLOSE':return {...base,action,params:{term_deposit_id:required(form.resource)}};
 case 'STOCK_BUY':case 'STOCK_SELL':{const quantity=Number(form.quantity);if(!/^\d+$/.test(form.quantity)||!Number.isSafeInteger(quantity)||quantity<1||quantity>1000000)throw Error('股票股數須為 1 至 1,000,000 的整數。');return {...base,action,params:{stock_id:required(form.stock),quantity}};}
 case 'LOAN_BORROW':return {...base,action,params:{product_id:required(form.product),amount_minor:toMinor(form.amount),term_months:form.term}};
 case 'LOAN_REPAY':return {...base,action,params:{loan_id:required(form.resource),amount_minor:toMinor(form.amount)}};
 case 'POLICY_BUY':if(!form.coverage)throw Error('請選擇保額。');return {...base,action,params:{product_id:required(form.product),coverage_minor:form.coverage,premium_period_months:12,beneficiary_label:form.beneficiary||'家人'}};
 case 'POLICY_SURRENDER':case 'POLICY_REINSTATE':case 'POLICY_PREMIUM_PAY':return {...base,action,params:{policy_id:required(form.resource)}};
 case 'BILL_PAY':return {...base,action,params:{bill_id:required(form.resource),amount_minor:toMinor(form.amount)}};
 }
}
