import React,{lazy,Suspense} from 'react';
import { createRoot } from 'react-dom/client';
const TrainingApp=lazy(()=>import('../components/training/training-app').then(m=>({default:m.TrainingApp})));
const GameApp=lazy(()=>import('../components/game/game-app').then(m=>({default:m.GameApp})));
const LegalPage=lazy(()=>import('../components/game/legal-page').then(m=>({default:m.LegalPage})));
const MinimalDemo=lazy(()=>import('../components/game/minimal-demo').then(m=>({default:m.MinimalDemo})));
const CityPage=lazy(()=>import('../app/city/page'));
const DestinationScene=lazy(()=>import('../components/destination-scene').then(m=>({default:m.DestinationScene})));
import type { DestinationId } from '../lib/map-data';
import '../app/globals.css';

const legalKind=window.location.pathname.replace(/\/$/,'')==='/terms'?'TERMS':window.location.pathname.replace(/\/$/,'')==='/privacy'?'PRIVACY':null;
const scene = window.location.pathname.match(/^\/place\/(work|hospital|leisure|finance)\/?$/)?.[1] as DestinationId | undefined;
createRoot(document.getElementById('root')!).render(
  <React.StrictMode><Suspense fallback={<p role="status" style={{padding:"24px"}}>正在載入人生讀檔…</p>}>{['/training','/teach'].includes(window.location.pathname.replace(/\/$/,''))?<TrainingApp teacher={window.location.pathname.startsWith('/teach')}/>:legalKind?<LegalPage kind={legalKind}/>:window.location.pathname.startsWith("/demo") ? <MinimalDemo/> : scene ? <DestinationScene destination={scene} /> : window.location.pathname.startsWith("/city") ? <CityPage/> : <GameApp/>}</Suspense></React.StrictMode>,
);
