'use client';
import './tutorial.css';
import { useEffect, useRef, useState } from 'react';
import { tutorialSeen, type TutorialStep } from '@/lib/tutorial';

export function useGuidedTour({
  ready,
  completed,
  storageKey,
  buildSteps,
}: {
  ready: boolean;
  completed: boolean | undefined;
  storageKey: string;
  buildSteps: () => TutorialStep[];
}) {
  const [session, setSession] = useState<{ key: string; steps: TutorialStep[]; index: number } | null>(null);
  const remembered = useRef(new Set<string>());
  const active = session?.key === storageKey;
  function start() {
    if (ready && storageKey) setSession({ key: storageKey, steps: buildSteps(), index: 0 });
  }
  useEffect(() => {
    if (!ready || completed === undefined || !storageKey || active || remembered.current.has(storageKey))
      return;
    let stored = false;
    try {
      stored = tutorialSeen(localStorage, storageKey);
    } catch {
      /* Server preference still works without browser storage. */
    }
    if (!completed && !stored) start();
  }, [ready, completed, storageKey, active, buildSteps]);
  function remember() {
    remembered.current.add(storageKey);
    try {
      localStorage.setItem(storageKey, 'done');
    } catch {
      /* Keep the completion for this session. */
    }
  }
  function stop() {
    remember();
    setSession(null);
  }
  function go(delta: number) {
    setSession(s =>
      s && s.key === storageKey
        ? { ...s, index: Math.max(0, Math.min(s.steps.length - 1, s.index + delta)) }
        : s,
    );
  }
  return {
    active,
    step: active ? session.steps[session.index] : undefined,
    index: active ? session.index : 0,
    total: active ? session.steps.length : 0,
    start,
    remember,
    stop,
    go,
  };
}
export function TutorialCoach({
  step,
  index,
  total,
  busy,
  onBack,
  onNext,
  onExit,
}: {
  step: TutorialStep;
  index: number;
  total: number;
  busy: boolean;
  onBack: () => void;
  onNext: () => void;
  onExit: () => void;
}) {
  const next = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    next.current?.focus();
  }, [step.id]);
  useEffect(() => {
    if (!step.target || busy) return;
    const target = document.querySelector(step.target);
    target?.classList.add('tutorial-highlight');
    return () => target?.classList.remove('tutorial-highlight');
  }, [step.target, busy]);
  return (
    <section className="tutorial-coach" aria-label="遊玩教學" aria-busy={busy}>
      <div className="tutorial-coach-top">
        <span>
          遊玩教學 · {index + 1} / {total}
        </span>
        <button className="quiet" disabled={busy} onClick={onExit}>
          略過教學
        </button>
      </div>
      <div className="tutorial-copy" aria-live="polite" aria-atomic="true">
        <h3>{step.title}</h3>
        <p>{busy ? '正在準備畫面，請稍候…' : step.text}</p>
      </div>
      <div className="tutorial-coach-actions">
        <button className="secondary" disabled={busy || index === 0} onClick={onBack}>
          上一步
        </button>
        <button ref={next} disabled={busy} onClick={onNext}>
          {index === total - 1 ? '完成教學' : '下一步'}
        </button>
      </div>
    </section>
  );
}
export function TutorialLaunch({
  onStart,
  disabled = false,
  demo = false,
}: {
  onStart: () => void;
  disabled?: boolean;
  demo?: boolean;
}) {
  return (
    <section className="tutorial-launch">
      <div>
        <h3>遊玩教學</h3>
        <p>{demo ? '跟著導覽，認識 Demo 的地圖、擲骰與結算。' : '跟著導覽，認識資產、保障、事件與結算。'}</p>
      </div>
      <button disabled={disabled} onClick={onStart}>
        重新觀看遊玩教學
      </button>
    </section>
  );
}
