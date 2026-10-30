'use client';
import { Brand } from '@/components/brand';
import { CityMapArtwork } from '@/components/city-map-artwork';
import { useCallback, useEffect, useRef, useState } from 'react';
import { BriefcaseBusiness, Cross, Landmark, Plane, RotateCcw } from 'lucide-react';
import { DESTINATIONS, HOME, type DestinationId, type Point } from '@/lib/map-data';
import { buildTrip, pointAtDistance, sampleAtTime } from '@/lib/travel';
import { LifeDashboard } from '@/components/life-dashboard';
import { travelEvents } from '@/lib/travel-events';
const ICONS = { work: BriefcaseBusiness, hospital: Cross, leisure: Plane, finance: Landmark };
type CarView = 'ne' | 'se' | 'sw' | 'nw';
function viewForHeading(angle: number): CarView {
  if (angle < -90) return 'nw';
  if (angle < 0) return 'ne';
  if (angle < 90) return 'se';
  return 'sw';
}

export default function HomePage() {
  const [position, setPosition] = useState<Point>(HOME);
  const [carView, setCarView] = useState<CarView>('ne');
  const [active, setActive] = useState<DestinationId | null>(null);
  const [direction, setDirection] = useState<'outbound' | 'return'>('outbound');
  const [arrived, setArrived] = useState<DestinationId | null>(null);
  const [progress, setProgress] = useState(0);
  const [turning, setTurning] = useState(false);
  const frame = useRef<number | null>(null),
    token = useRef(0);
  const carViewRef = useRef<CarView>('ne');
  const arrivalTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const startRef = useRef<(id: DestinationId) => void>(() => {});
  const returnRef = useRef<(id: DestinationId) => void>(() => {});
  const cancel = useCallback(() => {
    token.current++;
    if (frame.current !== null) cancelAnimationFrame(frame.current);
    frame.current = null;
    if (arrivalTimer.current) clearTimeout(arrivalTimer.current);
  }, []);
  useEffect(() => cancel, [cancel]);
  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get('return');
    if (requested && requested in DESTINATIONS) {
      returnRef.current(requested as DestinationId);
    }
  }, []);
  useEffect(() => {
    const context = (
      document as Document & {
        modelContext?: {
          registerTool: (tool: object, options: { signal: AbortSignal }) => void | Promise<void>;
        };
      }
    ).modelContext;
    if (!context?.registerTool) return;
    const lifecycle = new AbortController();
    void Promise.resolve(
      context.registerTool(
        {
          name: 'start_city_trip',
          title: '開始城市行程',
          description: '從家出發，開始前往工作、醫院、休閒區或金融大樓的可見車輛動畫。',
          inputSchema: {
            type: 'object',
            properties: { destination: { type: 'string', enum: ['work', 'hospital', 'leisure', 'finance'] } },
            required: ['destination'],
            additionalProperties: false,
          },
          annotations: { readOnlyHint: false, untrustedContentHint: false },
          execute: (input: unknown) => {
            const id = (input as { destination?: unknown })?.destination;
            if (typeof id !== 'string' || !(id in DESTINATIONS)) throw new Error('Unknown destination');
            startRef.current(id as DestinationId);
            return { status: 'started', destination: id };
          },
        },
        { signal: lifecycle.signal },
      ),
    ).catch(() => {});
    return () => lifecycle.abort();
  }, []);

  function start(id: DestinationId, tripDirection: 'outbound' | 'return' = 'outbound') {
    cancel();
    const currentToken = token.current,
      trip = buildTrip(id, tripDirection);
    const duration = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 700 : trip.durationMs;
    setPosition(trip.points[0]);
    setActive(id);
    setDirection(tripDirection);
    setArrived(null);
    setProgress(0);
    setTurning(false);
    const initialView = viewForHeading(pointAtDistance(trip, 0).heading);
    carViewRef.current = initialView;
    setCarView(initialView);
    travelEvents.emit({ type: 'trip:start', destination: id, direction: tripDirection });
    let startedAt: number | null = null,
      lastMilestone = -1;
    const tick = (now: number) => {
      if (token.current !== currentToken) return;
      startedAt ??= now;
      const fraction = Math.min((now - startedAt) / duration, 1);
      const sample = sampleAtTime(trip, fraction);
      const eased = sample.distance / trip.length;
      setPosition(sample.position);
      setProgress(fraction);
      const nextView = viewForHeading(sample.heading);
      if (nextView !== carViewRef.current) {
        carViewRef.current = nextView;
        setCarView(nextView);
      }
      setTurning(sample.turning && fraction < 1);
      const milestone = trip.milestones.findLastIndex(threshold => eased >= threshold);
      for (let i = lastMilestone + 1; i <= milestone; i++)
        travelEvents.emit({ type: 'trip:milestone', destination: id, direction: tripDirection, index: i });
      lastMilestone = Math.max(lastMilestone, milestone);
      if (fraction < 1) frame.current = requestAnimationFrame(tick);
      else {
        frame.current = null;
        setActive(null);
        setArrived(tripDirection === 'outbound' ? id : null);
        travelEvents.emit({ type: 'trip:arrive', destination: id, direction: tripDirection });
        if (tripDirection === 'outbound')
          arrivalTimer.current = setTimeout(() => window.location.assign(`/place/${id}`), 500);
        else window.history.replaceState(null, '', '/');
      }
    };
    frame.current = requestAnimationFrame(tick);
  }
  startRef.current = id => start(id);
  returnRef.current = id => start(id, 'return');
  function reset() {
    cancel();
    window.history.replaceState(null, '', '/');
    setPosition(HOME);
    carViewRef.current = 'ne';
    setCarView('ne');
    setTurning(false);
    setActive(null);
    setArrived(null);
    setProgress(0);
  }
  const status = active
    ? direction === 'return'
      ? `從${DESTINATIONS[active].label}返家途中`
      : `前往${DESTINATIONS[active].label}途中`
    : arrived
      ? `已抵達${DESTINATIONS[arrived].label}`
      : '車輛停在家門口';
  return (
    <main className="game-shell">
      <section className="map-column" aria-label="城市地圖">
        <div className="topline">
          <Brand />
          <span className="topline-rule" />
          <span className="topline-note">城市移動演示</span>
        </div>
        <LifeDashboard />
        <div className="map-frame">
          <div className="map-canvas">
            <CityMapArtwork />
            <svg
              className="map-overlay"
              viewBox="0 0 1672 941"
              preserveAspectRatio="xMidYMid meet"
              aria-hidden="true"
            >
              <g
                transform={`translate(${position.x} ${position.y})`}
                className={turning ? 'car-turning' : undefined}
              >
                <ellipse cx="0" cy="13" rx="24" ry="8" fill="#243d4d" opacity=".18" />
                {(['ne', 'se', 'sw', 'nw'] as CarView[]).map(view => (
                  <image
                    key={view}
                    href={`/car-${view}.png`}
                    x="-34"
                    y="-30"
                    width="68"
                    height="47"
                    className="car-view"
                    style={{ opacity: carView === view ? 1 : 0 }}
                  />
                ))}
              </g>
            </svg>
          </div>
        </div>
        <p className="map-caption">
          選擇目的地，觀看車輛沿城市道路移動。 <a href="/play">進入擲骰與移動展示版</a>
        </p>
      </section>
      <aside className="control-panel" aria-label="移動選項">
        <div className="panel-heading">
          <span className="eyebrow">DESTINATION</span>
          <h1>今天要去哪裡？</h1>
          <p>從家出發，選擇一個目的地。</p>
        </div>
        <div className="destinations">
          {(Object.keys(DESTINATIONS) as DestinationId[]).map((id, index) => {
            const destination = DESTINATIONS[id],
              Icon = ICONS[id];
            return (
              <button
                key={id}
                className={`destination ${active === id ? 'selected' : ''} ${arrived === id ? 'completed' : ''}`}
                onClick={() => start(id)}
                aria-label={`${destination.action}，從家出發`}
              >
                <span className="destination-index">0{index + 1}</span>
                <span className="destination-icon">
                  <Icon size={23} strokeWidth={1.8} />
                </span>
                <span className="destination-copy">
                  <strong>{destination.action}</strong>
                  <small>{destination.detail}</small>
                </span>
                <span className="destination-arrow">↗</span>
              </button>
            );
          })}
        </div>
        <div className="journey-card" aria-live="polite">
          <div className="journey-label">目前行程</div>
          <strong>{status}</strong>
          <div className="progress-track">
            <span style={{ width: `${progress * 100}%` }} />
          </div>
          <div className="journey-foot">
            <span>{active && direction === 'return' ? DESTINATIONS[active].label : '家'}</span>
            <span>
              {active && direction === 'return'
                ? '家'
                : active
                  ? DESTINATIONS[active].label
                  : arrived
                    ? DESTINATIONS[arrived].label
                    : '選擇目的地'}
            </span>
          </div>
        </div>
        <button className="reset-button" onClick={reset}>
          <RotateCcw size={16} />
          回到家門口
        </button>
      </aside>
    </main>
  );
}
