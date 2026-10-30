import {useId} from 'react';
import './account-settings.css';
export function MotionSwitch({checked,disabled,onChange}:{checked:boolean;disabled?:boolean;onChange:(value:boolean)=>void}){
 const id=useId();
 return <div className="motion-preference"><div><strong id={id}>減少動畫</strong><small>切換即生效，並自動儲存</small></div><button type="button" className="motion-switch" role="switch" aria-checked={checked} aria-labelledby={id} disabled={disabled} onClick={()=>onChange(!checked)}><span aria-hidden="true" className="motion-switch-track"><span/></span><span className="motion-switch-state" aria-hidden="true">{checked?'開啟':'關閉'}</span></button></div>;
}
