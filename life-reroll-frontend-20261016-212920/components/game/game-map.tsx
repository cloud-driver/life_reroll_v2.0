'use client';
import {useEffect,useRef,useState} from 'react';
import {HOME,type DestinationId,type Point} from '@/lib/map-data';
import {buildTrip,sampleAtTime} from '@/lib/travel';
import {travelEvents} from '@/lib/travel-events';
import {fitMapViewport} from '@/lib/viewport-layout';
import {cityMapCamera} from '@/lib/map-artwork';
import {CityMapArtwork} from '@/components/city-map-artwork';
export type MapTrip={id:DestinationId;direction:'outbound'|'return';nonce:number};
type View='ne'|'se'|'sw'|'nw';
const view=(a:number):View=>a< -90?'nw':a<0?'ne':a<90?'se':'sw';
export function GameMap({trip,onArrive,parked,parkedHeading,reducedMotion}: {trip:MapTrip|null;onArrive:()=>void;parked?:Point;parkedHeading?:number;reducedMotion?:boolean}){
 const [car,setCar]=useState({position:parked??HOME,heading:-30,turning:false});
 const viewport=useRef<HTMLDivElement>(null),[size,setSize]=useState<{width:number;height:number}|null>(null);
 useEffect(()=>{
  const element=viewport.current!;
  const observer=new ResizeObserver(([entry])=>setSize(fitMapViewport(entry.contentRect.width,entry.contentRect.height)));
  observer.observe(element);return()=>observer.disconnect();
 },[]);
 const onArriveRef=useRef(onArrive);onArriveRef.current=onArrive;
 const contentWidth=size?Math.max(1,size.width-20):1672,contentHeight=size?Math.max(1,size.height-20):941;
 const camera=cityMapCamera(contentWidth,contentHeight);
 useEffect(()=>{for(const v of ['ne','se','sw','nw']){const image=new Image();image.src=`/car-${v}.webp`;}},[]);
 useEffect(()=>{
  if(!trip){if(parked)setCar({position:parked,heading:parkedHeading??car.heading,turning:false});return;}
  const path=buildTrip(trip.id,trip.direction);let raf=0,start:number|null=null,last=-1;
  const duration=reducedMotion||matchMedia('(prefers-reduced-motion: reduce)').matches?700:path.durationMs;
  travelEvents.emit({type:'trip:start',destination:trip.id,direction:trip.direction});
  function tick(now:number){start??=now;const f=Math.min((now-start)/duration,1),sample=sampleAtTime(path,f);setCar(sample);
   const index=path.milestones.findLastIndex(x=>sample.distance/path.length>=x);
   for(let i=last+1;i<=index;i++)travelEvents.emit({type:'trip:milestone',destination:trip!.id,direction:trip!.direction,index:i});last=index;
   if(f<1)raf=requestAnimationFrame(tick);else{setCar({...sample,turning:false});travelEvents.emit({type:'trip:arrive',destination:trip!.id,direction:trip!.direction});onArriveRef.current();}
  }
  raf=requestAnimationFrame(tick);return()=>cancelAnimationFrame(raf);
 },[trip,parked,parkedHeading,reducedMotion]);
 return <div className="map-fit" ref={viewport}><div className="map-frame" style={size??undefined}><div className="map-canvas"><CityMapArtwork width={contentWidth} height={contentHeight}/><svg className="map-overlay" viewBox={`${camera.x} 0 ${camera.width} ${camera.height}`} preserveAspectRatio="xMidYMid meet" aria-hidden="true"><g transform={`translate(${car.position.x} ${car.position.y})`} className={car.turning?'car-turning':undefined}><ellipse cx="0" cy="13" rx="24" ry="8" fill="#243d4d" opacity=".18"/>{(['ne','se','sw','nw'] as View[]).map(v=><image key={v} href={`/car-${v}.webp`} x="-34" y="-30" width="68" height="47" className="car-view" style={{opacity:view(car.heading)===v?1:0}}/>)}</g></svg></div></div></div>;
}
