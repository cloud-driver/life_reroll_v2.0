'use client';
import {useId} from 'react';
import {CITY_MAP,CITY_PANORAMA,CITY_REGIONS,cityMapCamera} from '@/lib/map-artwork';
export function CityMapArtwork({width=CITY_MAP.width,height=CITY_MAP.height}:{width?:number;height?:number}){
 const id=useId().replace(/:/g,''),camera=cityMapCamera(width,height);
 const font=Math.min(68,Math.max(29,12/Math.max(height/CITY_MAP.height,.01)));
 const left=(CITY_MAP.width-CITY_PANORAMA.width)/2;
 return <svg className="map-image city-map-artwork" viewBox={`${camera.x} 0 ${camera.width} ${camera.height}`} preserveAspectRatio="xMidYMid meet" role="img" aria-label="城市地圖：中央生活區（家）、右下工作區、左上金融區與右上休閒區">
  <title>Life Reroll 城市分區地圖</title>
  <defs><linearGradient id={`${id}-edge`}><stop offset="0" stopColor="white" stopOpacity="0"/><stop offset=".048" stopColor="white"/><stop offset=".952" stopColor="white"/><stop offset="1" stopColor="white" stopOpacity="0"/></linearGradient><mask id={`${id}-core`} maskUnits="userSpaceOnUse" x="0" y="0" width={CITY_MAP.width} height={CITY_MAP.height}><rect width={CITY_MAP.width} height={CITY_MAP.height} fill={`url(#${id}-edge)`}/></mask></defs>
  <image href="/life-reroll-city-panorama.webp" x={left} y="0" width={CITY_PANORAMA.width} height={CITY_MAP.height} preserveAspectRatio="none"/>
  {/* Keep all original roads under the car paths exact. Only the outer 80px blend. */}
  <image href="/life-reroll-city.webp" x="0" y="0" width={CITY_MAP.width} height={CITY_MAP.height} mask={`url(#${id}-core)`}/>
  {CITY_REGIONS.map(region=>{const badgeWidth=region.label.length*font+30,badgeHeight=font+22;return <g key={region.id} className="city-map-region" transform={`translate(${region.x} ${region.y})`}>
   <rect x={-badgeWidth/2} y={-badgeHeight/2+3} width={badgeWidth} height={badgeHeight} rx="10" fill="#25473c" opacity=".16"/>
   <rect x={-badgeWidth/2} y={-badgeHeight/2} width={badgeWidth} height={badgeHeight} rx="10" fill="#fffdf1" fillOpacity=".96" stroke="#c7ceb8" strokeWidth="1.5"/>
   <rect x={-badgeWidth/2+12} y={-badgeHeight/2+13} width="3" height={badgeHeight-26} rx="1.5" fill={region.accent}/>
   <text x="5" y="1" textAnchor="middle" dominantBaseline="central" fontSize={font} fill="#3e5b51" fontFamily="Microsoft JhengHei, PingFang TC, Noto Sans TC, sans-serif" fontWeight="600" letterSpacing="1">{region.label}</text>
  </g>;})}
 </svg>;
}
