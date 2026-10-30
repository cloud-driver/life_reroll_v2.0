import { DESTINATIONS, type DestinationId, type Point } from './map-data';
// Illustration ground units, not metres. Undo the vertical projection for
// distances and curvature; keep each perspective sprite upright on the ground.
const ground=(p:Point):Point=>({x:p.x,y:p.y/.58});
const screen=(p:Point):Point=>({x:p.x,y:p.y*.58});
const lerp=(a:Point,b:Point,t:number):Point=>({x:a.x+(b.x-a.x)*t,y:a.y+(b.y-a.y)*t});
const distance=(a:Point,b:Point)=>Math.hypot(b.x-a.x,b.y-a.y);
type Sample={position:Point;heading:number;turning:boolean};
export type Trip={points:Point[];samples:Sample[];cumulative:number[];times:number[];speeds:number[];length:number;durationMs:number;milestones:number[]};
function bezier(controls:Point[],t:number):Point {
  let row=controls;
  while(row.length>1) row=row.slice(0,-1).map((p,i)=>lerp(p,row[i+1],t));
  return row[0];
}
export function buildTrip(destination:DestinationId,direction:'outbound'|'return'='outbound'):Trip {
  const data=DESTINATIONS[destination];
  const points=direction==='return'?[...data.route].reverse():[...data.route];
  const g=points.map(ground),samples:Sample[]=[];
  function add(p:Point,tangent:Point,turning:boolean) {
    const position=screen(p),v=screen(tangent);
    if(samples.length&&distance(samples.at(-1)!.position,position)<1e-7)return;
    samples.push({position,heading:Math.atan2(v.y,v.x)*180/Math.PI,turning});
  }
  function line(a:Point,b:Point) {
    const n=Math.max(1,Math.ceil(distance(a,b)/2));
    for(let i=0;i<=n;i++)add(lerp(a,b,i/n),{x:b.x-a.x,y:b.y-a.y},false);
  }
  let cursor=g[0];
  for(let i=1;i<g.length-1;i++) {
    const a=g[i-1],corner=g[i],b=g[i+1];
    // Three collinear controls at each end give zero curvature at both joins.
    // Short fillets stay inside the intersections rather than cutting corners.
    const trim=Math.min(22,distance(a,corner)*.22,distance(corner,b)*.22);
    const entry=lerp(corner,a,trim/distance(a,corner)),exit=lerp(corner,b,trim/distance(corner,b));
    line(cursor,entry);
    const controls=[entry,lerp(entry,corner,.45),lerp(entry,corner,.9),lerp(exit,corner,.9),lerp(exit,corner,.45),exit];
    const derivative=controls.slice(0,-1).map((p,j)=>({x:5*(controls[j+1].x-p.x),y:5*(controls[j+1].y-p.y)}));
    for(let j=1;j<=64;j++)add(bezier(controls,j/64),bezier(derivative,j/64),j<64);
    cursor=exit;
  }
  line(cursor,g.at(-1)!);
  const cumulative=[0];
  for(let i=1;i<samples.length;i++)cumulative.push(cumulative[i-1]+distance(ground(samples[i-1].position),ground(samples[i].position)));
  // Lateral acceleration caps bend speed; forward/backward passes limit
  // acceleration and braking, including a stopped start and destination.
  const speeds=samples.map((s,i)=>{
    if(i===0||i===samples.length-1)return 0;
    const a=ground(samples[i-1].position),b=ground(s.position),c=ground(samples[i+1].position);
    const ab=distance(a,b),bc=distance(b,c),ac=distance(a,c);
    const k=2*Math.abs((b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x))/Math.max(1e-9,ab*bc*ac);
    return Math.min(150,Math.sqrt(110/Math.max(k,1e-8)));
  });
  for(let i=1;i<speeds.length;i++)speeds[i]=Math.min(speeds[i],Math.sqrt(speeds[i-1]**2+170*(cumulative[i]-cumulative[i-1])));
  for(let i=speeds.length-2;i>=0;i--)speeds[i]=Math.min(speeds[i],Math.sqrt(speeds[i+1]**2+170*(cumulative[i+1]-cumulative[i])));
  const times=[0];
  for(let i=1;i<speeds.length;i++)times.push(times[i-1]+2*(cumulative[i]-cumulative[i-1])/Math.max(1e-6,speeds[i]+speeds[i-1]));
  const total=times.at(-1)!;
  return {points,samples,cumulative,times:times.map(t=>t/total),speeds,length:cumulative.at(-1)!,durationMs:Math.max(data.durationMs,total*1000),milestones:[.25,.5,.75]};
}
function interval(values:number[],value:number):number {
  let lo=1,hi=values.length-1;
  while(lo<hi){const mid=(lo+hi)>>1;if(values[mid]<value)lo=mid+1;else hi=mid;}
  return lo;
}
export function pointAtDistance(trip:Trip,distance:number):Sample {
  const d=Math.max(0,Math.min(distance,trip.length)),i=interval(trip.cumulative,d);
  const a=trip.samples[i-1],b=trip.samples[i],span=trip.cumulative[i]-trip.cumulative[i-1],t=span?(d-trip.cumulative[i-1])/span:0;
  const delta=((b.heading-a.heading+540)%360)-180;
  return {position:lerp(a.position,b.position,t),heading:a.heading+delta*t,turning:t===0?a.turning:a.turning||b.turning};
}
export function sampleAtTime(trip:Trip,fraction:number):Sample&{distance:number} {
  const f=Math.max(0,Math.min(fraction,1)),i=interval(trip.times,f);
  const t=(f-trip.times[i-1])/(trip.times[i]-trip.times[i-1]);
  const a=trip.speeds[i-1],b=trip.speeds[i];
  const travel=(2*a*t+(b-a)*t*t)/(a+b);
  const distance=trip.cumulative[i-1]+(trip.cumulative[i]-trip.cumulative[i-1])*travel;
  return {...pointAtDistance(trip,distance),distance};
}
