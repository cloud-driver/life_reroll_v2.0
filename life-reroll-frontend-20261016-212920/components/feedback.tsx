'use client';
import { Component, useEffect, useRef, useState, type ErrorInfo, type ReactNode } from 'react';
import './feedback.css';

const prefersReducedMotion = () =>
  typeof window !== 'undefined' &&
  (document.documentElement.dataset.reducedMotion === 'true' ||
    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true);

// Longer messages stay longer; nothing disappears faster than a slow reader needs.
export const toastDuration = (message: string) => Math.min(9000, Math.max(3800, message.length * 130));

/** Transient confirmation. It floats, so showing or clearing it never moves the layout. */
export function Toast({
  message,
  onClose,
  tone = 'success',
}: {
  message: string;
  onClose: () => void;
  tone?: 'success' | 'info';
}) {
  const [paused, setPaused] = useState(false);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    if (!message || paused) return;
    const timer = setTimeout(() => close.current(), toastDuration(message));
    return () => clearTimeout(timer);
  }, [message, paused]);
  if (!message) return null;
  return (
    <div
      className={`toast toast-${tone}`}
      role="status"
      onPointerEnter={() => setPaused(true)}
      onPointerLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
    >
      <span className="toast-mark" aria-hidden="true">
        {tone === 'success' ? '✓' : 'i'}
      </span>
      <span className="toast-text">{message}</span>
      <button type="button" className="quiet toast-close" aria-label="關閉提示" onClick={onClose}>
        ×
      </button>
    </div>
  );
}

const lineWidths = [92, 76, 84, 58, 70];

/** Placeholder with the rough shape of the content, so panels do not jump when data arrives. */
export function Skeleton({
  lines = 3,
  label = '正在讀取…',
  block = false,
}: {
  lines?: number;
  label?: string;
  block?: boolean;
}) {
  return (
    <div className="skeleton" role="status" aria-busy="true">
      {block && <span className="skeleton-block" aria-hidden="true" />}
      {Array.from({ length: lines }, (_, i) => (
        <span
          key={i}
          className="skeleton-line"
          aria-hidden="true"
          style={{ width: `${lineWidths[i % lineWidths.length]}%` }}
        />
      ))}
      <span className="skeleton-label">{label}</span>
    </div>
  );
}

/** Thin indeterminate bar. The CSS delays it slightly so instant responses do not flicker. */
export function BusyBar({ active }: { active: boolean }) {
  return <div className="busy-bar" data-active={active ? 'true' : 'false'} aria-hidden="true" />;
}

/** Counts from the previous amount to the new one and tints the direction of the change. */
export function AnimatedAmount({ minor, format }: { minor: number; format: (minor: number) => string }) {
  const [shown, setShown] = useState(minor),
    [trend, setTrend] = useState<'' | 'up' | 'down'>('');
  const current = useRef(minor);
  useEffect(() => {
    const start = current.current;
    if (start === minor || !Number.isFinite(start) || !Number.isFinite(minor)) {
      current.current = minor;
      setShown(minor);
      return;
    }
    setTrend(minor > start ? 'up' : 'down');
    const settle = setTimeout(() => setTrend(''), 1600);
    if (prefersReducedMotion()) {
      current.current = minor;
      setShown(minor);
      return () => clearTimeout(settle);
    }
    let frame = 0;
    const began = performance.now(),
      duration = 650;
    const tick = (now: number) => {
      const progress = Math.min(1, (now - began) / duration),
        eased = 1 - Math.pow(1 - progress, 3);
      // Whole units while moving keeps the digits from flickering through random cents.
      const value = progress < 1 ? Math.round((start + (minor - start) * eased) / 100) * 100 : minor;
      current.current = value;
      setShown(value);
      if (progress < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(frame);
      clearTimeout(settle);
      current.current = minor;
    };
  }, [minor]);
  return (
    <strong className={`amount-tween ${trend}`} aria-label={`${format(minor)} 元`}>
      {format(shown)} 元
    </strong>
  );
}

/** First paint while the app bundle or the saved session is still loading. */
export function AppSplash({ label = '正在載入人生讀檔…' }: { label?: string }) {
  return (
    <div className="app-splash" role="status">
      <span className="app-splash-mark" aria-hidden="true" />
      <p>{label}</p>
    </div>
  );
}

type BoundaryState = { failed: boolean };

/** Keeps a render error from blanking the page; progress lives on the server, so reloading is safe. */
export class ErrorBoundary extends Component<{ children: ReactNode }, BoundaryState> {
  state: BoundaryState = { failed: false };
  static getDerivedStateFromError(): BoundaryState {
    return { failed: true };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('畫面發生未預期的錯誤', error, info.componentStack);
  }
  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="app-fallback" role="alert">
        <h1>畫面暫時無法顯示</h1>
        <p>已儲存的進度保留在伺服器上，不會因為這個錯誤遺失。重新載入後即可從原進度繼續。</p>
        <div className="app-fallback-actions">
          <button type="button" onClick={() => window.location.reload()}>
            重新載入
          </button>
          <button type="button" className="secondary" onClick={() => this.setState({ failed: false })}>
            再試一次
          </button>
        </div>
      </div>
    );
  }
}
