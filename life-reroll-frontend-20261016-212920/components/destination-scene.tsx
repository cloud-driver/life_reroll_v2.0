'use client';
import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, House } from 'lucide-react';
import { DESTINATIONS, type DestinationId } from '@/lib/map-data';

export function DestinationScene({destination}: {destination:DestinationId}) {
  const data=DESTINATIONS[destination];
  const imageRef=useRef<HTMLImageElement>(null);
  const [ready,setReady]=useState(false);
  const [choice,setChoice]=useState<string|null>(null);
  useEffect(()=>{
    // A cached image can finish before React attaches the onLoad handler.
    const image=imageRef.current;
    if(image?.complete && image.naturalWidth>0) setReady(true);
    // A failed image should never trap the player before the interaction menu.
    const fallback=window.setTimeout(()=>setReady(true),3000);
    return ()=>window.clearTimeout(fallback);
  },[destination]);
  useEffect(()=>{
    if(!ready) return;
    const delay=window.matchMedia('(prefers-reduced-motion: reduce)').matches?350:1500;
    const timer=window.setTimeout(()=>setChoice(''),delay);
    return ()=>window.clearTimeout(timer);
  },[ready]);
  const showChoices=choice!==null;
  return <main className={`scene-page ${showChoices?'scene-ready':''}`}>
    <img ref={imageRef} src={data.scene} alt={`${data.label}的場域景觀`} className="scene-image" onLoad={()=>setReady(true)} onError={()=>setReady(true)}/>
    <div className="scene-scrim" aria-hidden="true"/>
    <div className="scene-reveal"><span>Life Reroll / 抵達目的地</span><h1>{data.label}</h1></div>
    {showChoices&&<section className="scene-menu" aria-label={`${data.label}互動選項`}>
      <span className="scene-kicker">DESTINATION · {data.label}</span>
      <h2>想在這裡做什麼？</h2>
      <div className="scene-actions">{['A','B','C'].map(letter=><button key={letter} type="button" className={choice===letter?'chosen':''} onClick={()=>setChoice(letter)}><span>互動 {letter}</span><ArrowRight size={19}/></button>)}</div>
      {choice&&<p className="scene-feedback" role="status">已選擇互動 {choice}（目前為流程演示）</p>}
      <a className="scene-return" href={`/?return=${destination}`}><House size={18}/> 開車回家 <ArrowLeft size={16}/></a>
    </section>}
  </main>;
}
